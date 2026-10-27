"""Durable key-value state in PostgreSQL. Each Component keeps its state under its own scope."""
from typing import Any

from solution import db


class StateStore:
    def __init__(self, scope: str, url: str | None = None) -> None:
        self.scope = scope
        self.url = url

    def get(self, key: str, default: Any = None) -> Any:
        with db.connect(self.url) as connection:
            row = connection.execute("SELECT value FROM solution_state WHERE scope = %s AND key = %s",
                                     (self.scope, key)).fetchone()
        return row[0] if row else default

    def put(self, key: str, value: Any) -> None:
        import json
        with db.connect(self.url) as connection:
            connection.execute(
                "INSERT INTO solution_state (scope, key, value) VALUES (%s, %s, %s::jsonb) "
                "ON CONFLICT (scope, key) DO UPDATE SET value = excluded.value, updated_at = now()",
                (self.scope, key, json.dumps(value)))
