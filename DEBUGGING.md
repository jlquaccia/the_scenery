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

## LangGraph Studio (agent step-through, real from 3.1)

```bash
cd backend && source .venv/bin/activate
langgraph dev        # serves the graph from langgraph.json; opens Studio in the browser
```

Studio shows each node's inputs/outputs and lets you replay/edit state. Until 3.1 the graph
is a placeholder (`app/orchestrator/graph.py`). Smoke test: `curl localhost:2024/ok`.

## MCP Inspector (scene-db tools, from 1.8)

```bash
npx @modelcontextprotocol/inspector
```

Point it at the scene-db MCP server URL; gives an interactive console for `query_scenes`
etc. — the fastest way to test tool contracts without an agent in the loop.

## Linters / type checking

```bash
cd backend
.venv/bin/ruff check . && .venv/bin/ruff format --check .   # lint + format
.venv/bin/mypy app ingestion                                 # strict typing
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
