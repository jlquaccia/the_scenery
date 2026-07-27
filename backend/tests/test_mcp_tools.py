"""scene-db MCP tool contract (roadmap 1.8).

Uses FastMCP's in-memory client — the real server object, no network, no container —
so these run in CI without the MCP service being up. The tools open their own database
sessions from MYSQL_DSN (set in conftest), which is why nothing here writes.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mcp_servers.scene_db.server import mcp

TOOL_NAMES = {"resolve_genre", "list_genres", "query_scenes", "get_scene_detail", "compare_scenes"}


@pytest_asyncio.fixture
async def mcp_client() -> AsyncIterator[Client]:
    async with Client(mcp) as client:
        yield client


async def scene_id_for(client: Client, genre: str, location: str, level: str) -> int:
    result = await client.call_tool(
        "query_scenes", {"genre": genre, "location": location, "level": level, "limit": 1}
    )
    assert result.data, f"no {genre} scene at {location}"
    return int(result.data[0].scene_id)


async def test_every_tool_is_exposed(mcp_client: Client) -> None:
    assert {t.name for t in await mcp_client.list_tools()} == TOOL_NAMES


async def test_query_scenes_returns_ranked_scenes_with_coordinates(mcp_client: Client) -> None:
    result = await mcp_client.call_tool(
        "query_scenes", {"genre": "thrash metal", "level": "metro", "limit": 3}
    )
    assert result.data[0].location == "San Francisco Bay Area"
    assert all(s.lat is not None and s.lng is not None for s in result.data)


async def test_resolve_genre_handles_a_nickname(mcp_client: Client) -> None:
    result = await mcp_client.call_tool("resolve_genre", {"name": "thrash"})
    assert result.data.name == "thrash metal"


async def test_unknown_genre_lists_the_known_ones(mcp_client: Client) -> None:
    """The error is the model's only chance to recover — it has to name the options."""
    with pytest.raises(ToolError, match="thrash metal"):
        await mcp_client.call_tool("resolve_genre", {"name": "polka"})


async def test_scene_detail_carries_its_evidence(mcp_client: Client) -> None:
    scene_id = await scene_id_for(mcp_client, "thrash metal", "San Francisco Bay Area", "metro")
    result = await mcp_client.call_tool("get_scene_detail", {"scene_id": scene_id})
    assert result.data.signal_count > 0
    assert result.data.location_path[-1] == "San Francisco Bay Area"


async def test_unknown_scene_id_is_a_tool_error(mcp_client: Client) -> None:
    with pytest.raises(ToolError, match="999999"):
        await mcp_client.call_tool("get_scene_detail", {"scene_id": 999999})


async def test_compare_flags_incomparable_scores(mcp_client: Client) -> None:
    metro = await scene_id_for(mcp_client, "thrash metal", "San Francisco Bay Area", "metro")
    country = await scene_id_for(mcp_client, "thrash metal", "Germany", "country")
    result = await mcp_client.call_tool("compare_scenes", {"scene_ids": [metro, country]})
    assert result.data.comparable is False
    assert result.data.caveat


async def test_compare_needs_two_scenes(mcp_client: Client) -> None:
    metro = await scene_id_for(mcp_client, "thrash metal", "San Francisco Bay Area", "metro")
    with pytest.raises(ToolError, match="at least two"):
        await mcp_client.call_tool("compare_scenes", {"scene_ids": [metro]})
