"""C1-9: start the Solution and prove it works. Run from the Solution folder: python deploy/smoke.py.

It checks /health and a no-op model call. With SMOKE_DATABASE_URL set it also migrates that database,
creates a case, and reads the field history back. The history of a case cannot be deleted, so point
SMOKE_DATABASE_URL only at a scratch database. DATABASE_URL alone never starts the database step."""
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("SOLUTION_TEST_MODE", "true")


def main() -> int:
    scratch = os.environ.get("SMOKE_DATABASE_URL", "")
    if scratch:
        os.environ["DATABASE_URL"] = scratch
    from fastapi.testclient import TestClient

    from solution.api import app
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    print("health ok")
    from solution.model_routing import call_with_fallback, routes
    if routes():
        agent = next(iter(routes()))
        assert call_with_fallback(agent, lambda model: "ok") == "ok"
        print("no-op model call ok")
    else:
        print("gap: runtime.yaml declares no model route; the model step is skipped")
    if not scratch:
        print("database step skipped: set SMOKE_DATABASE_URL to a scratch database to test it")
    else:
        from solution import db
        from solution.cases import SCHEMA, CaseStore
        db.migrate()
        store = CaseStore()
        case = f"smoke-{uuid.uuid4().hex[:8]}"
        store.create_case(case)
        field = next(iter(SCHEMA["properties"]))
        store.write_field(case, field, _sample(SCHEMA["properties"][field]), author="smoke", source="deploy/smoke.py")
        assert len(store.history(case, field)) == 1
        print("database ok")
    return 0


def _sample(schema: dict) -> object:
    kind = schema.get("type")
    return {"number": 1, "integer": 1, "boolean": True, "array": [], "object": {}}.get(kind, "smoke")


if __name__ == "__main__":
    raise SystemExit(main())
