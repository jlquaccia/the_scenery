"""Database engine + session plumbing shared by the REST API and the MCP server.

The engine is built lazily so that importing `app.services` (or a router) never
requires a live database — only actually opening a session does. `MYSQL_DSN` is
the same variable the ingestion jobs use (docker-compose sets it for the API).
"""

import os
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    dsn = os.environ.get("MYSQL_DSN", "")
    if not dsn:
        raise RuntimeError("MYSQL_DSN is required (mysql://user:pass@host:3306/scenery)")
    # pool_pre_ping: MySQL drops idle connections; the API is long-lived.
    return create_engine(dsn.replace("mysql://", "mysql+pymysql://", 1), pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one read-only-by-convention session per request."""
    with get_sessionmaker()() as session:
        yield session
