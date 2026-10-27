"""Behavioural tests of the KPI service (C8). Events derive from the SYNTHETIC events of the context."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kpis import service


def synthetic(event_type, case_id="synthetic-1", **fields):
    """A SYNTHETIC event: every field is labelled synthetic or 1, then overridden by the test."""
    event = {
        "actor_id": "synthetic", "actor_type": "synthetic", "agent_id": "synthetic", "agent_version": "synthetic",
        "case_id": case_id, "confidence": 1, "cost": 1, "event_type": event_type, "guardrail_event": "synthetic",
        "model": "synthetic", "override_flag": False, "override_reason": "synthetic", "prompt_version": "synthetic",
        "status": "synthetic", "step_id": "synthetic", "tokens_in": 1, "tokens_out": 1, "ts_end": "synthetic",
        "ts_start": "synthetic",
    }
    event.update(fields)
    return event


class KpiTestCase(unittest.TestCase):
    def check_degraded(self, kpi_id, event_name):
        self.assertIn(kpi_id, service.DEGRADED)
        self.assertIn(event_name, service.DEGRADED[kpi_id])
        self.assertIsNone(service.calculate([synthetic(event_name)])[kpi_id])

    def live(self, events):
        """Calculate with the degraded map emptied, to test the formula itself."""
        with patch.object(service, "DEGRADED", {}):
            return service.calculate(events)


class KpiFormulaTests(KpiTestCase):
    def test_kpi_o1(self):
        self.check_degraded("KPI_O1", "step.completed")
        events = [synthetic("step.completed"), synthetic("step.completed", "synthetic-2"), synthetic("tool.call")]
        self.assertEqual(self.live(events)["KPI_O1"], 2)

    def test_kpi_o2(self):
        self.check_degraded("KPI_O2", "step.completed")
        events = [synthetic("step.completed", status="ok"), synthetic("step.completed", status="error")]
        self.assertEqual(self.live(events)["KPI_O2"], 1)

    def test_kpi_o3(self):
        self.check_degraded("KPI_O3", "agent.decision")
        events = [synthetic("agent.decision", tokens_in=10, tokens_out=5),
                  synthetic("agent.decision", "synthetic-2", tokens_in=20, tokens_out=5)]
        self.assertEqual(self.live(events)["KPI_O3"], 20)

    def test_kpi_o4(self):
        self.check_degraded("KPI_O4", "agent.decision")
        events = [synthetic("agent.decision", actor_type="agent", cost=3),
                  synthetic("agent.decision", actor_type="human", cost=100),
                  synthetic("agent.decision", "synthetic-2", actor_type="agent", cost=1)]
        self.assertEqual(self.live(events)["KPI_O4"], 2)

    def test_kpi_o5(self):
        self.check_degraded("KPI_O5", "agent.decision")
        events = [synthetic("agent.decision", agent_id="a", tokens_in=4, tokens_out=4),
                  synthetic("agent.decision", "synthetic-2", agent_id="b", tokens_in=1, tokens_out=1)]
        self.assertEqual(self.live(events)["KPI_O5"], {"a": 4, "b": 1})

    def test_kpi_o6(self):
        self.check_degraded("KPI_O6", "agent.decision")
        events = [synthetic("agent.decision", status="ok"), synthetic("agent.decision", status="error"),
                  synthetic("agent.decision", status="ok"), synthetic("agent.decision", status="ok")]
        self.assertEqual(self.live(events)["KPI_O6"], 25)

    def test_kpi_o7(self):
        self.check_degraded("KPI_O7", "tool.call")
        events = [synthetic("tool.call", status="ok"), synthetic("tool.call", status="timeout"),
                  synthetic("tool.call", "synthetic-2", status="ok")]
        self.assertEqual(self.live(events)["KPI_O7"], 50)

    def test_kpi_o8(self):
        self.check_degraded("KPI_O8", "human.review")
        events = [synthetic("human.review", override_flag=True), synthetic("human.review", override_flag=False)]
        self.assertEqual(self.live(events)["KPI_O8"], 50)

    def test_kpi_o9(self):
        self.check_degraded("KPI_O9", "human.review")
        events = [synthetic("human.review", override_flag=False)] * 3 + [synthetic("human.review", override_flag=True)]
        self.assertEqual(self.live(events)["KPI_O9"], 75)
        low, high = service.wilson_interval(3, 4)
        self.assertLess(low, 75)
        self.assertGreater(high, 75)

    def test_kpi_o10(self):
        self.check_degraded("KPI_O10", "guardrail.triggered")
        events = [synthetic("guardrail.triggered", guardrail_event="pii"),
                  synthetic("guardrail.triggered", "synthetic-2", guardrail_event="pii"),
                  synthetic("guardrail.triggered", guardrail_event="length")]
        self.assertEqual(self.live(events)["KPI_O10"], {"length": 1, "pii": 2})


class CalculationTests(KpiTestCase):
    def test_one_key_per_owed_kpi_and_no_events_is_none(self):
        result = service.calculate([])
        self.assertEqual(set(result), {k["kpi_id"] for k in service.KPIS})
        self.assertTrue(all(v is None for v in result.values()))
        self.assertTrue(all(v is None for v in self.live([]).values()))

    def test_missing_denominator_is_none_not_zero(self):
        self.assertIsNone(self.live([synthetic("agent.decision", case_id=None)])["KPI_O3"])
        self.assertIsNone(self.live([synthetic("tool.call")])["KPI_O8"])

    def test_validate_event(self):
        self.assertIsNone(service.validate_event(synthetic("agent.decision")))
        missing = synthetic("agent.decision")
        del missing["cost"]
        with self.assertRaises(ValueError):
            service.validate_event(missing)
        with self.assertRaises(ValueError):
            service.validate_event(synthetic("agent.decision", tokens_in="1"))
        with self.assertRaises(ValueError):
            service.validate_event(synthetic("agent.decision", tokens_in=True))

    def test_display(self):
        self.assertEqual(service.display("KPI_O11", 5), {"label": "measured from MVP", "value": None})
        self.assertEqual(service.display("KPI_O6", 5), {"label": "Agent error rate", "value": 5})

    def test_backfill_groups_by_utc_day(self):
        events = [synthetic("tool.call", at="2026-01-01T23:30:00-02:00"),
                  synthetic("tool.call", at="2026-01-02T01:00:00+00:00"),
                  synthetic("tool.call", at="2025-12-31T10:00:00Z")]
        days = service.backfill(events)
        self.assertEqual(list(days), ["2025-12-31", "2026-01-02"])
        self.assertEqual(set(days["2026-01-02"]), set(service.calculate([])))

    def test_constants_cite_the_precord(self):
        self.assertEqual(set(service.PROVENANCE), {k["kpi_id"] for k in service.KPIS})
        for kpi in service.KPIS:
            self.assertEqual(service.PROVENANCE[kpi["kpi_id"]]["test_name"], "test_" + kpi["kpi_id"].lower())
            self.assertTrue(hasattr(KpiFormulaTests, kpi["test_name"]))
        self.assertEqual(service.NOT_OWED, {"KPI_O11": "MVP", "KPI_O12": "MVP", "KPI_O13": "MVP"})


class AlertTests(unittest.TestCase):
    def test_alerts_use_alert_rules_only(self):
        raised = service.alerts({"KPI_O6": 2.5, "KPI_O7": 3.0, "KPI_O9": 90, "KPI_O8": None, "KPI_O3": 10 ** 12})
        self.assertEqual([a["kpi_id"] for a in raised], ["KPI_O6", "KPI_O9"])
        self.assertEqual(raised[0], {"kpi_id": "KPI_O6", "value": 2.5, "threshold": 2.0, "condition": "above",
                                     "owner": "AI / ML engineer"})
        self.assertEqual(raised[1]["condition"], "below")
        self.assertEqual(raised[1]["owner"], "Risk lead")

    def test_prose_rule_raises_nothing(self):
        self.assertEqual(service.alerts({"KPI_O10": {"pii": 3}, "KPI_O4": 500}), [])

    def test_count_rule_raises_above_zero(self):
        rules = {"KPI_X": {"alerting": "any PII event", "event": "pii", "direction": "above", "limit": 0, "owner": "Risk lead"}}
        with patch.object(service, "ALERT_RULES", rules):
            self.assertEqual(len(service.alerts({"KPI_X": 1})), 1)
            self.assertEqual(service.alerts({"KPI_X": 0}), [])

    def test_deliver_needs_the_sink_variable(self):
        alert = {"kpi_id": "KPI_O6", "value": 3, "threshold": 2.0, "condition": "above", "owner": "x"}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SOLUTION_ALERT_SINK", None)
            self.assertFalse(service.deliver(alert))
            sink = Path(folder) / "alerts.jsonl"
            with patch.dict(os.environ, {"SOLUTION_ALERT_SINK": str(sink)}):
                self.assertTrue(service.deliver(alert))
                self.assertTrue(service.deliver(alert))
            lines = sink.read_text().splitlines()
            self.assertEqual([json.loads(line) for line in lines], [alert, alert])


class StoreTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("DATABASE_URL", None)

    def test_ingest_is_idempotent(self):
        store = service.KpiEventStore()
        event = synthetic("agent.decision")
        store.ingest(event)
        store.ingest(dict(event))
        self.assertEqual(store.events(), [event])

    def test_event_id_repeat_with_other_content_raises(self):
        store = service.KpiEventStore()
        store.ingest(synthetic("agent.decision", event_id="e1"))
        store.ingest(synthetic("agent.decision", event_id="e1"))
        with self.assertRaises(ValueError):
            store.ingest(synthetic("agent.decision", event_id="e1", cost=2))
        self.assertEqual(len(store.events()), 1)

    def test_store_path_and_feed(self):
        with tempfile.TemporaryDirectory() as folder:
            os.environ["PREVIEW_DATA_DIR"] = str(Path(folder) / "data")
            self.assertEqual(service.kpi_store_path(), Path(folder) / "data" / "kpis.sqlite")
            self.assertEqual(service.feed_events([synthetic("tool.call"), synthetic("tool.call")]), 1)
            self.assertEqual(service.feed_events([synthetic("tool.call", "synthetic-2")]), 2)
            reopened = service.KpiEventStore(service.kpi_store_path())
            self.assertEqual(len(reopened.events()), 2)
            reopened.close()

    def test_payload_empty_and_degraded(self):
        payload = service.playground_kpis_payload(service.KpiEventStore())["kpis"]
        self.assertEqual(set(payload), {k["kpi_id"] for k in service.KPIS})
        for entry in payload.values():
            self.assertIsNone(entry["value"])
            self.assertEqual(entry["status"], "unmeasured")
            self.assertEqual(set(entry), {"value", "unit", "status", "source_ref", "source_system", "visualization"})

    def test_payload_measured_when_not_degraded(self):
        store = service.KpiEventStore()
        store.ingest(synthetic("tool.call", status="ok"))
        with patch.object(service, "DEGRADED", {}):
            payload = service.playground_kpis_payload(store)["kpis"]
        self.assertEqual(payload["KPI_O7"]["status"], "measured")
        self.assertEqual(payload["KPI_O7"]["value"], 0)


if __name__ == "__main__":
    unittest.main()
