# The Scenery — Debugging Cheat Sheet

Every tool below is set up by roadmap item 1.2. Frontend items marked (2.x) land with the
Angular workspace.

## The stack itself

```bash
colima start                       # boot the Docker VM (after reboot)
docker compose up -d               # MySQL → Liquibase → API → Adminer
docker compose ps                  # statuses; mysql must say "(healthy)"
docker compose logs -f backend     # follow API logs
docker compose down                # stop (data kept) · down -v wipes DB + re-runs user init
```

Gotcha learned the hard way: if DB logins mysteriously fail, check **what's actually on
port 3306** — `lsof -nP -i :3306`. A stray Homebrew MySQL (`brew services list`) binds
127.0.0.1:3306 and shadows the container. Fix: `brew services stop mysql@8.4`.

## Logs (structlog)

- Pretty, colored console logs with **rich tracebacks** (source context + locals).
- Every request gets a `request_id`, bound to all its log lines and echoed as the
  `X-Request-ID` response header — grep the id from a failing response to get that
  request's full story. Later this same id becomes the OTel/LangSmith correlation id (6.1).
- Unhandled errors are logged **once**, with framework frames collapsed — only app frames get
  source + locals. The 500 body also carries the id:
  `{"error": "internal_server_error", "request_id": "…"}`.
- Demo: `curl -i localhost:8000/debug/boom` → 500 + header; `docker compose logs backend`
  shows the annotated traceback. (`/debug/*` exists only when `DEBUG_ENDPOINTS=1` — set in
  compose for dev, never in prod.)

## Breakpoints in the container (debugpy)

```bash
DEBUGPY=1 docker compose up -d backend   # API listens for a debugger on :5678
```

VS Code → Run & Debug → **"Attach to API in Docker (debugpy)"** (config committed in
`.vscode/launch.json`, path-mapped `backend/ ↔ /srv`). Set breakpoints in `app/…`, hit an
endpoint. Detach any time; `docker compose up -d backend` (without the var) turns it off.

## Database: Adminer (browser) & clients

- **Adminer:** http://localhost:8080 — server `mysql` (pre-filled), user `scenery_app` /
  password from `.env`, database `scenery`. Use `scenery_migrator` when you need DDL.
  (An "access denied … Events" note under the app user is expected — least privilege.)
- **MySQL Workbench / CLI:** host `127.0.0.1:3306`, same credentials. Root exists for
  emergencies only; nothing in the stack uses it.

## REST API (from 1.7)

- **Interactive docs:** http://localhost:8000/docs — every endpoint with its schema, runnable
  from the browser. `/openapi.json` is the same contract for the frontend (2.x).
- Quick checks:

```bash
curl -s "localhost:8000/api/scenes?genre=thrash+metal&level=city&limit=5" | jq
curl -s localhost:8000/api/genres | jq
curl -s "localhost:8000/api/scenes/$ID" | jq          # detail: signals + location path
```

Take `$ID` from a `/api/scenes` response — rollup scenes (metro/state/country) are created by
the scoring job, so their ids are stable within a database but not across a `down -v` rebuild.

Reading results: `score` is normalized 0–100 **within a (genre, level)**, so 100 just means
"top of its tier" — never compare a `city` score to a `metro` one. Empty list with a 200 means
the genre resolved but has no scenes at that level; unknown genres are a 404. Scores come from
the last `ingestion.compute_scores` run (`score_updated_at` in the detail payload) — if a
ranking looks stale, re-run that job before debugging the API.

## LangGraph Studio (agent step-through, real from 3.1)

```bash
cd backend && source .venv/bin/activate
langgraph dev        # serves the graph from langgraph.json; opens Studio in the browser
```

Studio shows each node's inputs/outputs and lets you replay/edit state. Until 3.1 the graph
is a placeholder (`app/orchestrator/graph.py`). Smoke test: `curl localhost:2024/ok`.

## scene-db MCP server + Inspector (from 1.8)

The server runs as its own compose service (same image as the API, different entry point)
on **http://localhost:8001/mcp** — streamable-HTTP. Tools: `resolve_genre`, `list_genres`,
`query_scenes`, `get_scene_detail`, `compare_scenes`.

```bash
docker compose logs -f mcp                 # it logs each tool call
```

Interactive console in the browser — the fastest way to test tool contracts with no agent
in the loop (paste the URL above, transport "Streamable HTTP"):

```bash
npx @modelcontextprotocol/inspector
```

Same thing scriptable, which is what CI and quick checks want:

```bash
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8001/mcp --transport http --method tools/list
```

```bash
npx @modelcontextprotocol/inspector --cli http://127.0.0.1:8001/mcp --transport http --method tools/call --tool-name query_scenes --tool-arg genre="thrash metal" --tool-arg level=metro
```

To run it outside Docker (breakpoints, fast edit loop) — needs `MYSQL_DSN` pointed at
127.0.0.1, and stop the compose `mcp` service first so the port is free:

```bash
cd backend && MYSQL_DSN="mysql://scenery_app:PASSWORD@127.0.0.1:3306/scenery" .venv/bin/python -m mcp_servers.scene_db.server
```

**Connecting a desktop MCP client.** Claude Desktop's *custom connector* requires an
`https` URL, so it can't reach the local http server. Run the same tools over **stdio**
instead — add this to `~/Library/Application Support/Claude/claude_desktop_config.json`
(absolute paths required, password from `.env`) and restart the app:

```json
{
  "mcpServers": {
    "scene-db": {
      "command": "/Users/jasonquaccia/code/the_scenery/backend/.venv/bin/python",
      "args": ["-m", "mcp_servers.scene_db.server"],
      "env": {
        "MCP_TRANSPORT": "stdio",
        "PYTHONPATH": "/Users/jasonquaccia/code/the_scenery/backend",
        "MYSQL_DSN": "mysql://scenery_app:PASSWORD@127.0.0.1:3306/scenery"
      }
    }
  }
}
```

MySQL still has to be up (`docker compose up -d mysql`), but the compose `mcp` service
doesn't — the client launches its own copy. Anything that writes to stdout in stdio mode
corrupts the protocol, which is why the banner is suppressed there.

Python-side smoke test without any network hop — `Client(mcp)` talks to the server object
in-process, which is the cheapest way to exercise a tool change:

```python
from fastmcp import Client
from mcp_servers.scene_db.server import mcp
async with Client(mcp) as c:
    result = await c.call_tool("query_scenes", {"genre": "thrash", "level": "metro"})
    print(result.data)          # typed objects · result.structured_content for plain dicts
```

## Tests

```bash
cd backend && .venv/bin/python -m pytest          # ~1s, needs the stack up
.venv/bin/python -m pytest -q tests/test_mcp_tools.py -x   # one file, stop on first failure
```

Integration by design: they run against the compose MySQL (`docker compose up -d` first),
because the Liquibase changelog is the schema's source of truth and an SQLite stand-in
would test a schema Liquibase never produced. Each test gets a session inside a
transaction that's rolled back afterwards. `conftest.py` builds the DSN from the repo
`.env`, so no env vars needed; if the DB is down or unseeded the failure message says
which. The MCP tests use FastMCP's in-memory client, so the `mcp` service needn't be up.

Tests never hardcode a `scene_id` — they look scenes up by (genre, location), because
rollup ids are assigned by the scoring job and change on a database rebuild.

## Linters / type checking

```bash
cd backend
.venv/bin/ruff check . && .venv/bin/ruff format --check .   # lint + format
.venv/bin/mypy app ingestion mcp_servers                     # strict typing
```

VS Code runs Ruff on save (`.vscode/settings.json`); install prompts come from
`.vscode/extensions.json`. Frontend (2.1+): angular-eslint + Prettier, ESLint fix-on-save.

## Frontend debug tooling (built at 2.2–2.3)

- **Angular DevTools** browser extension — component tree, signals, change-detection profiler.
- **AG-UI/A2UI event inspector** (dev-only service): logs every AG-UI event + A2UI message,
  keeps the last N streams replayable/exportable as fixtures for the 2.6 harness, and exposes
  `window.__scenery` (renderer + surfaces handle) so you never have to spelunk via
  `ng.getComponent` like spike S1 did.
- Client quirks to remember (spike S2): accumulate `event.delta` (not `textMessageBuffer`)
  during streaming; ignore the duplicate CUSTOM event named `manually_emit_message`.
