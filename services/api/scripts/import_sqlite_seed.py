"""Idempotently import the checked-in synthetic SQLite seed into PostgreSQL.

Run from services/api after Alembic migrations:
    python scripts/import_sqlite_seed.py

The source SQLite file is read-only; this script never modifies it.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID, insert as pg_insert

from app.database.session import Base, engine
from app.models import entities as _entities  # noqa: F401 - register ORM tables


def convert_value(value: Any, column_type: Any) -> Any:
    if value is None or value == '':
        return None
    if isinstance(column_type, PGUUID):
        return value if isinstance(value, UUID) else UUID(str(value))
    if isinstance(column_type, JSONB):
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(value) if value else {}
    if isinstance(column_type, DateTime):
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if isinstance(column_type, Date):
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])
    if isinstance(column_type, Numeric):
        return Decimal(str(value))
    if isinstance(column_type, Boolean):
        return bool(value)
    return value


def import_seed(sqlite_path: Path) -> dict[str, int]:
    if not sqlite_path.is_file():
        raise FileNotFoundError(f"Synthetic SQLite seed not found: {sqlite_path}")
    source = sqlite3.connect(f"file:{sqlite_path.as_posix()}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    source_tables = {
        row["name"]
        for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    imported: dict[str, int] = {}
    try:
        with engine.begin() as target:
            for table in Base.metadata.sorted_tables:
                if table.name not in source_tables:
                    continue
                source_columns = {
                    row["name"] for row in source.execute(f'PRAGMA table_info("{table.name}")')
                }
                columns = [column for column in table.columns if column.name in source_columns]
                if not columns:
                    continue
                names = [column.name for column in columns]
                quoted = ", ".join(f'"{name}"' for name in names)
                rows = source.execute(f'SELECT {quoted} FROM "{table.name}"')
                batch: list[dict[str, Any]] = []
                count = 0
                statement = pg_insert(table).on_conflict_do_nothing()
                for row in rows:
                    values = {
                        column.name: convert_value(row[column.name], column.type)
                        for column in columns
                    }
                    batch.append(values)
                    if len(batch) >= 500:
                        result = target.execute(statement, batch)
                        count += result.rowcount or 0
                        batch.clear()
                if batch:
                    result = target.execute(statement, batch)
                    count += result.rowcount or 0
                imported[table.name] = count
    finally:
        source.close()
    return imported


if __name__ == "__main__":
    default_path = Path(__file__).resolve().parents[3] / "database" / "retail_connect.sqlite"
    # The database volume is mounted at /app/database in Docker. Local execution
    # from services/api resolves to the repository database folder above.
    sqlite_path = Path("./database/retail_connect.sqlite")
    if not sqlite_path.is_file():
        sqlite_path = default_path
    counts = import_seed(sqlite_path.resolve())
    print("Synthetic seed import complete (existing primary keys were left unchanged):")
    for table, count in counts.items():
        print(f"  {table}: {count} inserted")
