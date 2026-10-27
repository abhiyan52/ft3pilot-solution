"""PostgreSQL access. The address comes from DATABASE_URL, which the runtime injects."""
import os
from pathlib import Path

import psycopg

# BUG-091: the migrations are package data beside this file, so a wheel from `pip install .` holds them.
MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # The ADK session service takes an asyncpg address. This module takes a plain one.
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def connect(url: str | None = None) -> psycopg.Connection:
    return psycopg.connect(url or database_url())


def migrate(url: str | None = None, directory: Path | None = None) -> set[str]:
    """Apply each migration file once, in name order. Give the names that this call applied.

    A folder with no migration file is a fault, not a clean run. The Solution always has migrations."""
    files = sorted((directory or MIGRATIONS).glob("*.sql"))
    if not files:
        raise RuntimeError(f"No migration files found in {directory or MIGRATIONS}; the package data is missing")
    applied: set[str] = set()
    with connect(url) as connection:
        connection.execute("SELECT pg_advisory_xact_lock(7355608)")
        connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                           "(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        done = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
        for path in files:
            if path.stem in done:
                continue
            connection.execute(path.read_text())
            connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
            applied.add(path.stem)
    return applied
