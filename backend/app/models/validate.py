"""Diff SQLAlchemy metadata against the migrated MySQL schema.

The Liquibase changelog is the source of truth; this check fails when the
models in app.models drift from it. Run (host, stack up):

    MYSQL_DSN=mysql://scenery_app:...@localhost:3306/scenery \
        .venv/bin/python -m app.models.validate

Intended as a CI step right after `liquibase update`.
"""

import os
import re
import sys

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import mysql

from app.db import dev_dsn
from app.models import Base

# Tables owned by other tools (never modeled): Liquibase + LangGraph checkpointer.
IGNORED_TABLE_PREFIXES = ("DATABASECHANGELOG", "checkpoint")


def normalize(type_sql: str) -> str:
    """Normalize a compiled/reflected column type for comparison."""
    t = type_sql.upper().replace(" ", "")
    t = re.sub(r"INTEGER", "INT", t)
    t = re.sub(r"INT\(\d+\)", "INT", t)  # display widths (deprecated in MySQL 8)
    t = t.replace("FLOAT", "DECIMAL")  # not used; belt & braces
    return t


def main() -> int:
    dsn = os.environ.get("MYSQL_DSN", "") or dev_dsn()
    if not dsn:
        print("MYSQL_DSN is required (e.g. mysql://user:pass@localhost:3306/scenery)")
        return 2
    engine = create_engine(dsn.replace("mysql://", "mysql+pymysql://", 1))
    inspector = inspect(engine)
    dialect = mysql.dialect()

    db_tables = {t for t in inspector.get_table_names() if not t.startswith(IGNORED_TABLE_PREFIXES)}
    model_tables = set(Base.metadata.tables)

    problems: list[str] = []
    for missing in sorted(model_tables - db_tables):
        problems.append(f"table {missing!r} is modeled but missing from the database")
    for extra in sorted(db_tables - model_tables):
        problems.append(f"table {extra!r} exists in the database but is not modeled")

    for name in sorted(model_tables & db_tables):
        model_cols = Base.metadata.tables[name].columns
        db_cols = {c["name"]: c for c in inspector.get_columns(name)}

        for col in model_cols:
            if col.name not in db_cols:
                problems.append(f"{name}.{col.name}: modeled but missing from the database")
                continue
            db_col = db_cols[col.name]
            if bool(col.nullable) != bool(db_col["nullable"]):
                problems.append(
                    f"{name}.{col.name}: nullable mismatch "
                    f"(model={col.nullable}, db={db_col['nullable']})"
                )
            model_type = normalize(col.type.compile(dialect=dialect))
            try:
                db_type = normalize(db_col["type"].compile(dialect=dialect))
            except Exception:  # noqa: BLE001 — reflected type may not compile
                db_type = normalize(str(db_col["type"]))
            if model_type != db_type:
                problems.append(
                    f"{name}.{col.name}: type mismatch (model={model_type}, db={db_type})"
                )
        for db_name in db_cols:
            if db_name not in model_cols:
                problems.append(f"{name}.{db_name}: in the database but not modeled")

    if problems:
        print(f"SCHEMA DRIFT — {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"schema OK — {len(model_tables)} tables match the migrated database")
    return 0


if __name__ == "__main__":
    sys.exit(main())
