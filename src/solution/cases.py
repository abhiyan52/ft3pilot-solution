"""Cases and their field history (C1-3, C1-9, C5-1).

Every write adds one history row with its author, time, and source. The case schema decides which
fields exist and what each value may be. A caller that holds the version it read can ask for a
conflict instead of an overwrite."""
import json
from pathlib import Path
from typing import Any

import jsonschema
import psycopg

from solution import db

SCHEMA = json.loads((Path(__file__).with_name("case_schema.json")).read_text())


class VersionConflict(Exception):
    """The field changed after the caller read it."""


class UnknownCase(LookupError):
    """No such case."""


def check_value(field: str, value: Any) -> None:
    """C1-9: the database takes only what the case schema allows."""
    properties = SCHEMA.get("properties", {})
    if field not in properties:
        raise ValueError(f"{field} is not in the case schema")
    try:
        jsonschema.Draft202012Validator(properties[field]).validate(value)
    except jsonschema.ValidationError as error:
        raise ValueError(f"The value of {field} does not fit the case schema: {error.message}") from error


class CaseStore:
    def __init__(self, url: str | None = None) -> None:
        self.url = url

    def connect(self) -> psycopg.Connection:
        return db.connect(self.url)

    def create_case(self, case_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            connection.execute("INSERT INTO cases (case_id) VALUES (%s) ON CONFLICT DO NOTHING", (case_id,))
        return {"case_id": case_id}

    def current_version(self, connection: psycopg.Connection, case_id: str, field: str) -> int:
        row = connection.execute("SELECT coalesce(max(version), 0) FROM case_field_history "
                                 "WHERE case_id = %s AND field = %s", (case_id, field)).fetchone()
        return int(row[0]) if row else 0

    def write_field(self, case_id: str, field: str, value: Any, *, author: str, source: str,
                    expected_version: int | None = None) -> dict[str, Any]:
        """Add one version of a field. Give the row that was written."""
        check_value(field, value)
        for _ in range(5):
            try:
                with self.connect() as connection:
                    if not connection.execute("SELECT 1 FROM cases WHERE case_id = %s", (case_id,)).fetchone():
                        raise UnknownCase(case_id)
                    current = self.current_version(connection, case_id, field)
                    if expected_version is not None and expected_version != current:
                        raise VersionConflict(f"{field} is at version {current}, not {expected_version}")
                    row = connection.execute(
                        "INSERT INTO case_field_history (case_id, field, value, version, author, source) "
                        "VALUES (%s, %s, %s::jsonb, %s, %s, %s) RETURNING version, written_at",
                        (case_id, field, json.dumps(value), current + 1, author, source)).fetchone()
                assert row is not None
                return {"case_id": case_id, "field": field, "value": value, "version": row[0],
                        "author": author, "source": source, "written_at": row[1].isoformat()}
            except psycopg.errors.UniqueViolation:
                if expected_version is not None:
                    raise VersionConflict(f"{field} changed while it was written") from None
        raise VersionConflict(f"{field} kept changing while it was written")

    def list_cases(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """List cases, newest first (C6-1). Each has its status, step, assignee, last action and field count.

        status, step and assignee are the current values of the case fields of those names. A case schema
        without such a field gives null. Nothing is invented."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT c.case_id, c.created_at, count(f.field), max(f.written_at) FROM cases c "
                "LEFT JOIN case_fields f ON f.case_id = c.case_id GROUP BY c.case_id, c.created_at "
                "ORDER BY c.created_at DESC, c.case_id LIMIT %s OFFSET %s", (limit, offset)).fetchall()
            ids = [row[0] for row in rows]
            current = connection.execute(
                "SELECT case_id, field, value FROM case_fields WHERE case_id = ANY(%s) "
                "AND field IN ('status', 'step', 'assignee')", (ids,)).fetchall()
            last = connection.execute(
                "SELECT DISTINCT ON (case_id) case_id, field, author, source, written_at FROM case_field_history "
                "WHERE case_id = ANY(%s) ORDER BY case_id, written_at DESC, id DESC", (ids,)).fetchall()
        named: dict[str, dict[str, Any]] = {}
        for case, field, value in current:
            named.setdefault(case, {})[field] = value if isinstance(value, str) else json.dumps(value)
        action = {case: {"field": field, "author": author, "source": source, "at": at.isoformat()}
                  for case, field, author, source, at in last}
        return [{"case_id": case, "created_at": created.isoformat(), "fields": count,
                 "updated_at": updated.isoformat() if updated else None,
                 "status": named.get(case, {}).get("status"), "step": named.get(case, {}).get("step"),
                 "assignee": named.get(case, {}).get("assignee"), "last_action": action.get(case)}
                for case, created, count, updated in rows]

    def read_case(self, case_id: str) -> dict[str, Any]:
        with self.connect() as connection:
            if not connection.execute("SELECT 1 FROM cases WHERE case_id = %s", (case_id,)).fetchone():
                raise UnknownCase(case_id)
            rows = connection.execute("SELECT field, value FROM case_fields WHERE case_id = %s", (case_id,)).fetchall()
        return {field: value for field, value in rows}

    def history(self, case_id: str, field: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as connection:
            # Two complete statements. No query text is built from input.
            if field is None:
                rows = connection.execute(
                    "SELECT field, value, version, author, source, written_at FROM case_field_history "
                    "WHERE case_id = %s ORDER BY written_at, id", (case_id,)).fetchall()
            else:
                rows = connection.execute(
                    "SELECT field, value, version, author, source, written_at FROM case_field_history "
                    "WHERE case_id = %s AND field = %s ORDER BY written_at, id", (case_id, field)).fetchall()
        return [{"field": f, "value": v, "version": n, "author": a, "source": s, "written_at": t.isoformat()}
                for f, v, n, a, s, t in rows]
