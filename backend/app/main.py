"""The Scenery — FastAPI application entry point."""

import os
from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.api import genres, scenes
from app.logging_config import configure_logging

configure_logging()
log = structlog.get_logger()

if os.environ.get("DEBUGPY") == "1":
    import debugpy

    debugpy.listen(("0.0.0.0", 5678))
    log.info("debugpy.listening", port=5678)

app = FastAPI(title="The Scenery API")


@app.middleware("http")
async def request_context(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Bind a request_id to every log line of a request; echo it as a header.

    The same id later becomes the correlation id across OTel + LangSmith (6.1).
    """
    request_id = request.headers.get("x-request-id") or uuid4().hex[:12]
    structlog.contextvars.bind_contextvars(request_id=request_id)
    log.info("request.start", method=request.method, path=request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        # Log once (rich traceback) and answer 500 ourselves — returning a
        # response here keeps uvicorn from printing a second, plain traceback.
        log.exception("request.failed")
        response = JSONResponse(
            {"error": "internal_server_error", "request_id": request_id},
            status_code=500,
        )
    else:
        log.info("request.end", status=response.status_code)
    finally:
        structlog.contextvars.clear_contextvars()
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "the-scenery-api"}


app.include_router(scenes.router)
app.include_router(genres.router)


if os.environ.get("DEBUG_ENDPOINTS") == "1":

    @app.get("/debug/boom")
    def boom() -> dict[str, int]:
        """Force an exception to demo the rich, request-correlated traceback."""
        scenes: dict[str, int] = {"bay-area": 1}
        return {"scene": scenes["gotham"]}  # KeyError, on purpose
