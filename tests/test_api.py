"""HTTP tests of the Solution API through a FastAPI TestClient (C7).

The case database is an external boundary: CaseStore and StateStore are replaced by narrow in-memory doubles.
Fixtures are SYNTHETIC; the Precord has no sample_data rows.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from integrations import inbound_api
from solution import case_routes
from solution import wiring
from solution.api import app


class FakeCaseStore:
    """In-memory double of solution.cases.CaseStore. SYNTHETIC rows."""

    rows = []

    def list_cases(self, limit=100, offset=0):
        return list(self.rows)[offset:offset + limit]


class MemoryCases:
    def __init__(self):
        self.created = []

    def read_case(self, case_id):
        if case_id not in self.created:
            raise LookupError(case_id)
        return {}

    def create_case(self, case_id):
        if case_id not in self.created:
            self.created.append(case_id)
        return {"case_id": case_id}


class MemoryState:
    data = {}

    def __init__(self, scope, url=None):
        self.scope = scope

    def get(self, key, default=None):
        return self.data.get((self.scope, key), default)

    def put(self, key, value):
        self.data[(self.scope, key)] = value


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        env = patch.dict(os.environ, {"PREVIEW_DATA_DIR": folder.name})
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(app)


class HealthAndTriggerTests(ApiTestCase):
    # TRIGGER-BLK_01
    def test_trigger_blk_01_is_listed_with_its_declared_cue(self):
        response = self.client.get("/v1/triggers")
        self.assertEqual(response.status_code, 200)
        by_agent = {row["agent_id"]: row["cue"] for row in response.json()}
        self.assertEqual(by_agent["BLK_01"], "Incoming prospect registration submission")
        self.assertEqual(by_agent["BLK_02"], "Document upload completion")

    # TRIGGER-BLK_01
    def test_trigger_blk_01_inbound_case_enters_through_the_inbound_trigger_kind(self):
        self.assertEqual(inbound_api.TRIGGER_KIND, "Inbound channel message")
        seen = {}

        async def enter(agent_id, payload, *, correlation_id, trigger_kind=None, **_):
            seen.update(agent_id=agent_id, trigger=trigger_kind, correlation_id=correlation_id)
            return {"output": {}, "entry": {"route": ["BLK_01"]}}

        MemoryState.data = {}
        with patch.object(inbound_api, "case_store", return_value=MemoryCases()), \
                patch("solution.state.StateStore", MemoryState), \
                patch("solution.agent_runtime.enter_case", enter):
            response = self.client.post("/v1/cases", json={"case_reference": "SYN-1"},
                                        headers={"Idempotency-Key": "syn-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen["agent_id"], "")  # a process-level case; no named agent
        self.assertEqual(seen["trigger"], "Inbound channel message")
        self.assertEqual(response.json()["case_id"], "c-syn-1")


class InboundIdempotencyTests(ApiTestCase):
    # TRIGGER-BLK_01
    def test_a_replayed_submission_returns_the_same_case_and_runs_once(self):
        calls = []

        async def enter(agent_id, payload, *, correlation_id, trigger_kind=None, **_):
            calls.append(correlation_id)
            return {"output": {}, "entry": {"route": []}}

        MemoryState.data = {}
        cases = MemoryCases()
        with patch.object(inbound_api, "case_store", return_value=cases), \
                patch("solution.state.StateStore", MemoryState), \
                patch("solution.agent_runtime.enter_case", enter):
            first = self.client.post("/v1/cases", json={"case_reference": "SYN-2"}, headers={"Idempotency-Key": "k2"})
            second = self.client.post("/v1/cases", json={"case_reference": "SYN-2"}, headers={"Idempotency-Key": "k2"})
            other = self.client.post("/v1/cases", json={"case_reference": "SYN-3"}, headers={"Idempotency-Key": "k3"})
        self.assertEqual(first.json(), second.json())
        self.assertEqual(calls, ["c-k2", "c-k3"])
        self.assertNotEqual(first.json()["case_id"], other.json()["case_id"])

    def test_a_submission_without_a_key_or_a_json_object_is_refused_with_422(self):
        missing = self.client.post("/v1/cases", json={"case_reference": "SYN-4"})
        self.assertEqual(missing.status_code, 422)
        self.assertIn("Idempotency-Key", missing.json()["detail"])
        self.assertEqual(missing.json()["action"], "Reject with validation report")
        with patch.object(inbound_api, "case_store", return_value=MemoryCases()):
            listed = self.client.post("/v1/cases", content=json.dumps([1]), headers={"Idempotency-Key": "k4"})
        self.assertEqual(listed.status_code, 422)

    def test_a_failed_run_is_reported_and_not_recorded_as_an_entry(self):
        async def enter(*args, **kwargs):
            raise RuntimeError("model unavailable")

        MemoryState.data = {}
        with patch.object(inbound_api, "case_store", return_value=MemoryCases()), \
                patch("solution.state.StateStore", MemoryState), \
                patch("solution.agent_runtime.enter_case", enter):
            response = self.client.post("/v1/cases", json={}, headers={"Idempotency-Key": "k5"})
        self.assertEqual(response.status_code, 500)
        self.assertIn("model unavailable", response.json()["detail"])
        self.assertEqual(MemoryState.data, {})


class ScreenTests(ApiTestCase):
    # SCREEN-CASES
    def test_screen_cases_lists_each_case_with_status_step_assignee_and_last_action(self):
        FakeCaseStore.rows = [
            {"case_id": "c-syn-1", "created_at": "2026-01-01T00:00:00+00:00", "fields": 0, "updated_at": None,
             "status": None, "step": None, "assignee": None, "last_action": None},
            {"case_id": "c-syn-2", "created_at": "2026-01-02T00:00:00+00:00", "fields": 1,
             "updated_at": "2026-01-02T00:00:01+00:00", "status": "open", "step": "S1", "assignee": "syn-user",
             "last_action": {"field": "status", "author": "api", "source": "api", "at": "2026-01-02T00:00:01+00:00"}},
        ]
        with patch.object(case_routes, "CaseStore", FakeCaseStore):
            response = self.client.get("/cases")
        self.assertEqual(response.status_code, 200)
        cases = response.json()["cases"]
        self.assertEqual([case["case_id"] for case in cases], ["c-syn-1", "c-syn-2"])
        for case in cases:
            for key in ("status", "step", "assignee", "last_action"):
                self.assertIn(key, case)

    # SCREEN-CASES
    def test_screen_cases_shows_open_reviews_from_the_pending_route(self):
        response = self.client.get("/playground/reviews/pending")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    # SCREEN-KPIS
    def test_screen_kpis_gives_no_value_for_any_kpi(self):
        response = self.client.get("/playground/kpis")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(body["dashboard"]["kind"], ("not_built", "url"))
        kpis = body.get("kpis") or []
        for kpi in (kpis.values() if isinstance(kpis, dict) else kpis):
            self.assertIn(kpi.get("value") if isinstance(kpi, dict) else kpi, (None, ""))
        self.assertNotIn("value", body)
        self.assertEqual(body["casesWalked"], 0)

    # SCREEN-DEMO
    def test_screen_demo_serves_the_built_playground_at_root_and_keeps_json_routes_ahead(self):
        with tempfile.TemporaryDirectory() as dist, tempfile.TemporaryDirectory() as data:
            Path(dist, "index.html").write_text("<html><body>synthetic playground</body></html>")
            with patch.dict(os.environ, {"SOLUTION_PLAYGROUND_DIST": dist, "PREVIEW_DATA_DIR": data}):
                demo = FastAPI()
                wiring.register(demo)
                client = TestClient(demo)
                root = client.get("/")
                kpis = client.get("/playground/kpis")
        self.assertEqual(root.status_code, 200)
        self.assertIn("synthetic playground", root.text)
        self.assertIn("no-cache", root.headers["Cache-Control"])
        self.assertEqual(kpis.status_code, 200)
        self.assertIn("dashboard", kpis.json())

    # SCREEN-DEMO
    def test_screen_demo_without_a_built_folder_does_not_serve_root(self):
        with tempfile.TemporaryDirectory() as empty, tempfile.TemporaryDirectory() as data:
            with patch.dict(os.environ, {"SOLUTION_PLAYGROUND_DIST": empty, "PREVIEW_DATA_DIR": data}):
                demo = FastAPI()
                wiring.register(demo)
                response = TestClient(demo).get("/")
        self.assertEqual(response.status_code, 404)


class CaseRouteTests(ApiTestCase):
    def test_health_reports_ok(self):
        body = self.client.get("/health").json()
        self.assertEqual(body["status"], "ok")

    def test_an_unknown_playground_route_is_404_not_an_empty_answer(self):
        response = self.client.get("/playground/no-such-route")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
