"""Shared fixtures.

These are integration tests by design: they run against the compose MySQL, because
the Liquibase changelog is the schema's source of truth and an SQLite stand-in would
be testing a schema Liquibase never produced. Bring the stack up first:

    docker compose up -d

Every test gets a session inside a transaction that is rolled back afterwards, so a
test that writes can't leak into the next one.
"""

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.db import dev_dsn

# Set before anything imports app.db's engine: the MCP server builds its own
# sessions from this variable, so it has to be in place at import time.
os.environ.setdefault("MYSQL_DSN", dev_dsn())


@pytest.fixture(scope="session")
def engine() -> Engine:
    dsn = os.environ.get("MYSQL_DSN", "")
    if not dsn:
        pytest.fail("MYSQL_DSN is unset and .env has no app credentials to build one from")
    engine = create_engine(dsn.replace("mysql://", "mysql+pymysql://", 1), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            scenes = connection.execute(text("SELECT COUNT(*) FROM scenes")).scalar_one()
    except Exception as exc:  # noqa: BLE001 — one clear message beats a raw driver error
        pytest.fail(
            f"can't reach the database at {dsn.split('@')[-1]} — `docker compose up -d`?\n{exc}"
        )
    if not scenes:
        pytest.fail("the scenes table is empty — run `python -m ingestion.compute_scores`")
    return engine


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session whose work is always rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    with Session(bind=connection) as session:
        yield session
    transaction.rollback()
    connection.close()


@pytest.fixture
def api(session: Session) -> Iterator[TestClient]:
    """The REST app, wired to the rolled-back test session."""
    from app.db import get_session
    from app.main import app

    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
