"""Copy a consistent SQLite snapshot into an EMPTY PostgreSQL application schema.

Never overwrites or deletes target data. Secrets are read from a private file, not CLI args.
Run only after freezing the local instance at cutover. A failed copy rolls back as one unit.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL

from infrastructure.database import models  # noqa: F401
from infrastructure.database.base import Base
from infrastructure.database.session import build_engine

ROOT = Path(__file__).resolve().parents[2]


def copy_state(source_file: Path, target_url: str, schema: str = "visao", *, check_only=False):
    if not source_file.is_file():
        raise ValueError("Source snapshot does not exist")
    source = create_engine(
        URL.create(
            "sqlite", database=f"file:{source_file.resolve()}", query={"mode": "ro", "uri": "true"}
        )
    )
    target = build_engine(target_url, schema)
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    try:
        with target.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        tables = Base.metadata.sorted_tables
        counts = {}
        with source.connect() as old, target.begin() as new:
            if new.exec_driver_sql("SELECT current_schema()").scalar_one() != schema:
                raise ValueError("Target schema mismatch")
            for table in tables:
                if new.scalar(select(func.count()).select_from(table)):
                    raise ValueError(f"Target is not empty: {table.name}; no data was overwritten")
            for table in tables:
                # Typed SQLAlchemy selects decode UUID/JSON/Decimal values from SQLite.
                rows = [dict(row) for row in old.execute(select(table)).mappings()]
                for row in rows:
                    for key, value in row.items():
                        if isinstance(value, datetime) and value.tzinfo is None:
                            row[key] = value.replace(tzinfo=UTC)
                # Self-referencing notebook entries are inserted in chronological order.
                if table.name == "study_entries":
                    rows.sort(key=lambda row: row["created_at"])
                if rows and not check_only:
                    new.execute(table.insert(), rows)
                counts[table.name] = len(rows)
            if not check_only:
                for table in tables:
                    actual = new.scalar(select(func.count()).select_from(table))
                    if actual != counts[table.name]:
                        raise ValueError(f"Row count mismatch: {table.name}")
        return counts
    finally:
        source.dispose()
        target.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-snapshot", type=Path, required=True)
    parser.add_argument("--credentials-file", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    creds = json.loads(args.credentials_file.read_text())
    counts = copy_state(args.source_snapshot, creds["url"], check_only=args.check_only)
    print(json.dumps({"check_only": args.check_only, "rows": counts}))
