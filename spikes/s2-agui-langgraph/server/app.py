"""Spike S2: trivial LangGraph graph exposed as an AG-UI endpoint on FastAPI.

Deliberately LLM-free: the node emits a text message and a custom event
carrying a fake A2UI payload, which is all the spike needs to verify the
protocol glue (tokens + custom events reaching @ag-ui/client).
"""

from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint

FAKE_A2UI_MESSAGES = [
    {
        "version": "v0.9",
        "updateDataModel": {
            "surfaceId": "map",
            "path": "/map/viewport",
            "value": {"lat": 37.77, "lng": -122.42, "zoom": 8, "label": "San Francisco Bay Area"},
        },
    }
]


async def respond(state: MessagesState) -> dict:
    """Emit a chat answer plus an A2UI payload — no LLM involved."""
    answer = (
        "The Bay Area remains the historical heart of thrash — "
        "flying the map there now."
    )
    message_id = str(uuid4())

    # → TEXT_MESSAGE_START / CONTENT / END on the AG-UI wire
    await adispatch_custom_event(
        "manually_emit_message", {"message_id": message_id, "message": answer}
    )
    # → CUSTOM event on the AG-UI wire, carrying the A2UI messages
    await adispatch_custom_event("a2ui_messages", FAKE_A2UI_MESSAGES)

    return {"messages": [AIMessage(content=answer, id=message_id)]}


graph = StateGraph(MessagesState)
graph.add_node("respond", respond)
graph.add_edge(START, "respond")
graph.add_edge("respond", END)
# ag-ui-langgraph calls graph.aget_state(), so a checkpointer is mandatory
# (spike finding — InMemorySaver here, MySQL saver in M5).
compiled = graph.compile(checkpointer=InMemorySaver())

app = FastAPI(title="Spike S2 — AG-UI ↔ LangGraph")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

add_langgraph_fastapi_endpoint(
    app,
    LangGraphAgent(
        name="spike_s2",
        description="Deterministic hello-world graph for protocol verification",
        graph=compiled,
    ),
    "/agui",
)
