"""structlog configuration: pretty, colored, rich-traceback console logs in dev.

Every log line automatically carries whatever is bound via
structlog.contextvars (the request middleware binds request_id), which is
what makes grepping a single request's story possible.
"""

import logging

import anyio
import fastapi
import starlette
import structlog


def configure_logging(level: int = logging.INFO) -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
            # Rich tracebacks, but focused: frames from the web-framework
            # plumbing are suppressed so the app's own frames stand out.
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.RichTracebackFormatter(
                    show_locals=True,
                    suppress=[starlette, fastapi, anyio],
                    max_frames=20,
                ),
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
