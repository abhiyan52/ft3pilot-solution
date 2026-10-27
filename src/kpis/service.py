"""KPI calculation, ingestion, alerting and the Playground KPI feed (C8).

Rung: Pilot. Every KPI is computed in Python from the supplied formulas. Each constant is copied from the Precord
(kpis.csv, thresholds, events.csv, kpi_views.csv) and cites its source_ref in KPIS and PROVENANCE.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Owed at the rung. Each row keeps the source_ref of kpis.csv and the supplied test_name.
KPIS = [{'alerting': 'above 15 percent',
  'category': '3 · Human–AI collaboration',
  'current_value': '',
  'depends_on': 'override_flag;override_reason;step_id',
  'emitted_by': 'human.review',
  'formula': 'count of reviews with override_flag set / count of agent decisions reviewed, split by '
             'direction',
  'grain': 'per step',
  'kpi_id': 'KPI_O8',
  'name': 'Override rate and direction',
  'owed_at': 'Pilot',
  'owner_on_breach': 'AI / ML engineer',
  'projected_value': '',
  'source_ref': 'kpi_board_definition@row:1',
  'source_system': 'platform',
  'unit': 'percent',
  'test_name': 'test_kpi_o8'},
 {'alerting': 'below 97 percent',
  'category': '4 · AI quality',
  'current_value': '',
  'depends_on': 'override_flag;confidence;step_id',
  'emitted_by': 'human.review',
  'formula': 'decisions found correct / decisions audited, with a Wilson 95 percent interval',
  'grain': 'per step',
  'kpi_id': 'KPI_O9',
  'name': 'Audited accuracy',
  'owed_at': 'Pilot',
  'owner_on_breach': 'Risk lead',
  'projected_value': '',
  'source_ref': 'kpi_board_definition@row:2',
  'source_system': 'platform',
  'unit': 'percent',
  'test_name': 'test_kpi_o9'},
 {'alerting': 'above 2 percent',
  'category': '5 · Agent behaviour',
  'current_value': '',
  'depends_on': 'status;agent_id',
  'emitted_by': 'agent.decision',
  'formula': 'runs ending in error / total runs x 100',
  'grain': 'per agent per hour',
  'kpi_id': 'KPI_O6',
  'name': 'Agent error rate',
  'owed_at': 'PoC',
  'owner_on_breach': 'AI / ML engineer',
  'projected_value': '',
  'source_ref': 'kpi_board_definition@row:3',
  'source_system': 'agent runtime',
  'unit': 'percent',
  'test_name': 'test_kpi_o6'},
 {'alerting': 'above 3 percent',
  'category': '5 · Agent behaviour',
  'current_value': '',
  'depends_on': 'status;agent_id;case_id',
  'emitted_by': 'tool.call',
  'formula': 'count of tool calls not ending ok / count of cases',
  'grain': 'per case',
  'kpi_id': 'KPI_O7',
  'name': 'Tool error and retry rate',
  'owed_at': 'PoC',
  'owner_on_breach': 'AI / ML engineer',
  'projected_value': '',
  'source_ref': 'kpi_board_definition@row:4',
  'source_system': 'agent runtime',
  'unit': 'percent',
  'test_name': 'test_kpi_o7'},
 {'alerting': 'budget burn above 90 percent of the monthly allocation',
  'category': '6 · Unit economics',
  'current_value': '',
  'depends_on': 'cost;actor_type;case_id',
  'emitted_by': 'agent.decision',
  'formula': 'sum of cost where actor_type = agent / count of cases closed',
  'grain': 'per case',
  'kpi_id': 'KPI_O4',
  'name': 'AI cost per case',
  'owed_at': 'PoC',
  'owner_on_breach': 'Product owner',
  'projected_value': '',
  'source_ref': 'kpi_board_definition@row:5',
  'source_system': 'platform',
  'unit': 'currency',
  'test_name': 'test_kpi_o4'},
 {'alerting': '',
  'category': '6 · Unit economics',
  'current_value': '',
  'depends_on': 'tokens_in;tokens_out;agent_id;case_id',
  'emitted_by': 'agent.decision',
  'formula': 'sum of tokens grouped by agent / count of cases closed',
  'grain': 'per agent per case',
  'kpi_id': 'KPI_O5',
  'name': 'Tokens per agent per case',
  'owed_at': 'PoC',
  'owner_on_breach': '',
  'projected_value': '',
  'source_ref': 'kpi_board_definition@row:6',
  'source_system': 'agent runtime',
  'unit': 'tokens',
  'test_name': 'test_kpi_o5'},
 {'alerting': '',
  'category': '6 · Unit economics',
  'current_value': '',
  'depends_on': 'tokens_in;tokens_out;case_id',
  'emitted_by': 'agent.decision',
  'formula': 'sum of prompt and completion tokens across all agents / count of cases closed',
  'grain': 'per case',
  'kpi_id': 'KPI_O3',
  'name': 'Tokens per case',
  'owed_at': 'PoC',
  'owner_on_breach': '',
  'projected_value': '',
  'source_ref': 'kpi_board_definition@row:7',
  'source_system': 'platform',
  'unit': 'tokens',
  'test_name': 'test_kpi_o3'},
 {'alerting': 'any PII event',
  'category': '8 · Risk and compliance',
  'current_value': '',
  'depends_on': 'guardrail_event;case_id',
  'emitted_by': 'guardrail.triggered',
  'formula': 'count of guardrail events by kind',
  'grain': 'per event',
  'kpi_id': 'KPI_O10',
  'name': 'Guardrail triggers',
  'owed_at': 'Pilot',
  'owner_on_breach': 'Risk lead',
  'projected_value': '',
  'source_ref': 'kpi_board_definition@row:11',
  'source_system': 'platform',
  'unit': 'count',
  'test_name': 'test_kpi_o10'},
 {'alerting': '',
  'category': '9 · Adoption',
  'current_value': '',
  'depends_on': 'case_id;ts_end',
  'emitted_by': 'step.completed',
  'formula': 'count of raw sources uploaded',
  'grain': 'per day',
  'kpi_id': 'KPI_O1',
  'name': 'Inputs uploaded',
  'owed_at': 'Pilot',
  'owner_on_breach': '',
  'projected_value': '',
  'source_ref': 'kpi_board_definition@row:12',
  'source_system': 'platform',
  'unit': 'count',
  'test_name': 'test_kpi_o1'},
 {'alerting': '',
  'category': '9 · Adoption',
  'current_value': '',
  'depends_on': 'case_id;status',
  'emitted_by': 'step.completed',
  'formula': 'count of artifact versions committed',
  'grain': 'per day',
  'kpi_id': 'KPI_O2',
  'name': 'Memory artifacts created',
  'owed_at': 'Pilot',
  'owner_on_breach': '',
  'projected_value': '',
  'source_ref': 'kpi_board_definition@row:13',
  'source_system': 'platform',
  'unit': 'count',
  'test_name': 'test_kpi_o2'}]

# Copied exactly from the context thresholds.
THRESHOLDS = [{'agent_id': '*',
  'comparator': '',
  'gate_tier': 'advisory',
  'grader_id': '',
  'level': '',
  'metric': 'override_rate_and_direction',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:1',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O8',
  'stage_applicability': '',
  'threshold': '15',
  'threshold_id': '',
  'tier_at_rung': 'advisory',
  'unit': 'percent'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'blocking',
  'grader_id': '',
  'level': '',
  'metric': 'audited_accuracy',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:2',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O9',
  'stage_applicability': '',
  'threshold': '97',
  'threshold_id': '',
  'tier_at_rung': 'advisory',
  'unit': 'percent'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'advisory',
  'grader_id': '',
  'level': '',
  'metric': 'agent_error_rate',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:3',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O6',
  'stage_applicability': '',
  'threshold': '2',
  'threshold_id': '',
  'tier_at_rung': 'advisory',
  'unit': 'percent'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'advisory',
  'grader_id': '',
  'level': '',
  'metric': 'tool_error_and_retry_rate',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:4',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O7',
  'stage_applicability': '',
  'threshold': '3',
  'threshold_id': '',
  'tier_at_rung': 'advisory',
  'unit': 'percent'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'blocking',
  'grader_id': '',
  'level': '',
  'metric': 'ai_cost_per_case',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:5',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O4',
  'stage_applicability': '',
  'threshold': '90',
  'threshold_id': '',
  'tier_at_rung': 'advisory',
  'unit': 'currency'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'monitor',
  'grader_id': '',
  'level': '',
  'metric': 'tokens_per_agent_per_case',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:6',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O5',
  'stage_applicability': '',
  'threshold': '10000',
  'threshold_id': '',
  'tier_at_rung': 'monitor',
  'unit': 'tokens'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'monitor',
  'grader_id': '',
  'level': '',
  'metric': 'tokens_per_case',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:7',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O3',
  'stage_applicability': '',
  'threshold': '10000000',
  'threshold_id': '',
  'tier_at_rung': 'monitor',
  'unit': 'tokens'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'monitor',
  'grader_id': '',
  'level': '',
  'metric': 'agents_live',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:8',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O12',
  'stage_applicability': '',
  'threshold': '2',
  'threshold_id': '',
  'tier_at_rung': 'monitor',
  'unit': 'count'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'monitor',
  'grader_id': '',
  'level': '',
  'metric': 'data_extraction_time',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:9',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O13',
  'stage_applicability': '',
  'threshold': '10',
  'threshold_id': '',
  'tier_at_rung': 'monitor',
  'unit': 'minutes'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'blocking',
  'grader_id': '',
  'level': '',
  'metric': 'verification_api_availability',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:10',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O11',
  'stage_applicability': '',
  'threshold': '99',
  'threshold_id': '',
  'tier_at_rung': 'advisory',
  'unit': 'percent'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'monitor',
  'grader_id': '',
  'level': '',
  'metric': 'guardrail_triggers',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:11',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O10',
  'stage_applicability': '',
  'threshold': '2',
  'threshold_id': '',
  'tier_at_rung': 'monitor',
  'unit': 'count'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'monitor',
  'grader_id': '',
  'level': '',
  'metric': 'inputs_uploaded',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:12',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O1',
  'stage_applicability': '',
  'threshold': '2',
  'threshold_id': '',
  'tier_at_rung': 'monitor',
  'unit': 'count'},
 {'agent_id': '*',
  'comparator': '',
  'gate_tier': 'monitor',
  'grader_id': '',
  'level': '',
  'metric': 'memory_artifacts_created',
  'min_sample': '',
  'provenance': 'kpi_board_definition@row:13',
  'source_artifact': 'kpi_board_definition',
  'source_row': 'KPI_O2',
  'stage_applicability': '',
  'threshold': '2',
  'threshold_id': '',
  'tier_at_rung': 'monitor',
  'unit': 'count'}]

PROVENANCE = {k["kpi_id"]: {"source_ref": k["source_ref"], "test_name": k["test_name"]} for k in KPIS}

# KPIs above the rung map to the rung they are owed from.
NOT_OWED = {"KPI_O11": "MVP", "KPI_O12": "MVP", "KPI_O13": "MVP"}

EVENT_SCHEMA = {
    "$id": "event.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "description": "The event every agent, tool call and checkpoint emits, from which spec/kpis.csv is computed. Derived from spec/events.csv.",
    "properties": {
        "actor_id": {"description": "Who or what acted, for audit rather than for measurement.", "type": "string"},
        "actor_type": {"description": "agent, human or system — the split every collaboration metric rests on.", "type": "string", "x-emitted-on": ["KPI_O4"]},
        "agent_id": {"description": "Which agent acted; the grain of every per-agent metric.", "type": "string", "x-emitted-on": ["KPI_O6", "KPI_O7", "KPI_O5", "KPI_O12"]},
        "agent_version": {"description": "As prompt_version, for the agent definition.", "type": "string"},
        "case_id": {"description": "The unit of work every metric is normalised against.", "type": "string", "x-emitted-on": ["KPI_O7", "KPI_O4", "KPI_O5", "KPI_O3", "KPI_O10", "KPI_O1", "KPI_O2"]},
        "confidence": {"description": "The agent's own confidence, for routing and calibration.", "type": "number", "x-emitted-on": ["KPI_O9"]},
        "cost": {"description": "Chargeable cost of the call, in the engagement's currency.", "type": "number", "x-emitted-on": ["KPI_O4"]},
        "event_type": {"description": "One of the six event types.", "type": "string"},
        "guardrail_event": {"description": "The guardrail that fired, by kind.", "type": "string", "x-emitted-on": ["KPI_O10"]},
        "model": {"description": "Model id, so quality can be read per release.", "type": "string"},
        "override_flag": {"description": "Set where a human overturned the agent.", "type": "boolean", "x-emitted-on": ["KPI_O8", "KPI_O9"]},
        "override_reason": {"description": "Why — required for the audit sample to be readable.", "type": "string", "x-emitted-on": ["KPI_O8"]},
        "prompt_version": {"description": "Annotates every time series at the release boundary.", "type": "string"},
        "status": {"description": "ok or the error kind; every error and retry rate reads this.", "type": "string", "x-emitted-on": ["KPI_O6", "KPI_O7", "KPI_O12", "KPI_O11", "KPI_O2"]},
        "step_id": {"description": "Ties the event to the process step table, so a benchmark and a live value are computed on the same axis.", "type": "string", "x-emitted-on": ["KPI_O8", "KPI_O9", "KPI_O13"]},
        "tokens_in": {"description": "Prompt tokens, for unit economics.", "type": "integer", "x-emitted-on": ["KPI_O5", "KPI_O3"]},
        "tokens_out": {"description": "Completion tokens, for unit economics.", "type": "integer", "x-emitted-on": ["KPI_O5", "KPI_O3"]},
        "ts_end": {"description": "End of the span.", "format": "date-time", "type": "string", "x-emitted-on": ["KPI_O13", "KPI_O11", "KPI_O1"]},
        "ts_start": {"description": "Start of the span; every duration is the difference of these.", "format": "date-time", "type": "string", "x-emitted-on": ["KPI_O13", "KPI_O11"]},
    },
    "required": ["case_id", "step_id", "agent_id", "event_type", "actor_type", "actor_id", "ts_start", "ts_end", "model", "prompt_version", "agent_version", "tokens_in", "tokens_out", "cost", "status", "confidence", "override_flag", "override_reason", "guardrail_event"],
    "title": "Solution event",
    "type": "object",
}

# Each reason names the event that no file of the Precord declares (readiness code PRECORD_UNDECLARED_EVENT).
DEGRADED = {
    "KPI_O1": "the event step.completed is not declared by any file in the Precord (readiness code PRECORD_UNDECLARED_EVENT)",
    "KPI_O10": "the event guardrail.triggered is not declared by any file in the Precord (readiness code PRECORD_UNDECLARED_EVENT)",
    "KPI_O2": "the event step.completed is not declared by any file in the Precord (readiness code PRECORD_UNDECLARED_EVENT)",
    "KPI_O3": "the event agent.decision is not declared by any file in the Precord (readiness code PRECORD_UNDECLARED_EVENT)",
    "KPI_O4": "the event agent.decision is not declared by any file in the Precord (readiness code PRECORD_UNDECLARED_EVENT)",
    "KPI_O5": "the event agent.decision is not declared by any file in the Precord (readiness code PRECORD_UNDECLARED_EVENT)",
    "KPI_O6": "the event agent.decision is not declared by any file in the Precord (readiness code PRECORD_UNDECLARED_EVENT)",
    "KPI_O7": "the event tool.call is not declared by any file in the Precord (readiness code PRECORD_UNDECLARED_EVENT)",
    "KPI_O8": "the event human.review is not declared by any file in the Precord (readiness code PRECORD_UNDECLARED_EVENT)",
    "KPI_O9": "the event human.review is not declared by any file in the Precord (readiness code PRECORD_UNDECLARED_EVENT)",
}

# A rule with limit None is prose. It raises nothing (see the gaps in the report).
ALERT_RULES = {
    "KPI_O10": {"alerting": "any PII event", "direction": None, "limit": None, "owner": "Risk lead"},
    "KPI_O4": {"alerting": "budget burn above 90 percent of the monthly allocation", "direction": None, "limit": None, "owner": "Product owner"},
    "KPI_O6": {"alerting": "above 2 percent", "direction": "above", "limit": 2.0, "owner": "AI / ML engineer"},
    "KPI_O7": {"alerting": "above 3 percent", "direction": "above", "limit": 3.0, "owner": "AI / ML engineer"},
    "KPI_O8": {"alerting": "above 15 percent", "direction": "above", "limit": 15.0, "owner": "AI / ML engineer"},
    "KPI_O9": {"alerting": "below 97 percent", "direction": "below", "limit": 97.0, "owner": "Risk lead"},
}

TIERS = {
    "KPI_O1": "monitor", "KPI_O10": "monitor", "KPI_O2": "monitor", "KPI_O3": "monitor", "KPI_O4": "advisory",
    "KPI_O5": "monitor", "KPI_O6": "advisory", "KPI_O7": "advisory", "KPI_O8": "advisory", "KPI_O9": "advisory",
}

# The Precord declares no group field. The harness chose this split from the category words.
GROUPS = {
    "business": ["KPI_O8", "KPI_O9", "KPI_O4", "KPI_O5", "KPI_O3", "KPI_O10", "KPI_O1", "KPI_O2"],
    "technical": ["KPI_O6", "KPI_O7"],
}

LOG_SINK = "The platform's own OpenTelemetry collector, until client IT names theirs"

_RUNG = "Pilot"
_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool}
_BY_ID = {k["kpi_id"]: k for k in KPIS}


def validate_event(event: Any) -> None:
    """Raise ValueError when a required field is absent or has the wrong type."""
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    for field in EVENT_SCHEMA["required"]:
        if field not in event:
            raise ValueError(f"required field absent: {field}")
    for field, rule in EVENT_SCHEMA["properties"].items():
        if field not in event:
            continue
        value, kind = event[field], rule["type"]
        ok = isinstance(value, _TYPES[kind])
        if kind in ("integer", "number") and isinstance(value, bool):
            ok = False
        if not ok:
            raise ValueError(f"field {field} must be {kind}")


def display(kpi_id: str, value: Any) -> dict[str, Any]:
    if kpi_id in NOT_OWED:
        return {"label": f"measured from {NOT_OWED[kpi_id]}", "value": None}
    return {"label": _BY_ID[kpi_id]["name"], "value": value}


def _num(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _of(events: list[dict], event_type: str) -> list[dict]:
    return [e for e in events if e.get("event_type") == event_type]


def _cases(events: list[dict]) -> int:
    """Cases in the window. The Precord declares no case-closed signal; see the gaps in the report."""
    return len({e["case_id"] for e in events if isinstance(e.get("case_id"), str)})


def _ratio(top: float, bottom: float) -> float | None:
    return top / bottom if bottom else None


def wilson_interval(correct: int, audited: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson 95 percent interval of a proportion, in percent."""
    if not audited:
        return None
    p = correct / audited
    denominator = 1 + z * z / audited
    centre = (p + z * z / (2 * audited)) / denominator
    margin = z * math.sqrt(p * (1 - p) / audited + z * z / (4 * audited * audited)) / denominator
    return (100 * max(0.0, centre - margin), 100 * min(1.0, centre + margin))


def _o1(events):
    rows = _of(events, "step.completed")
    return len(rows) or None


def _o2(events):
    rows = _of(events, "step.completed")
    return sum(1 for e in rows if e.get("status") == "ok") if rows else None


def _tokens(rows):
    return sum(e["tokens_in"] + e["tokens_out"] for e in rows if _num(e.get("tokens_in")) and _num(e.get("tokens_out")))


def _o3(events):
    rows = _of(events, "agent.decision")
    return _ratio(_tokens(rows), _cases(events)) if rows else None


def _o4(events):
    rows = [e for e in _of(events, "agent.decision") if e.get("actor_type") == "agent" and _num(e.get("cost"))]
    return _ratio(sum(e["cost"] for e in rows), _cases(events)) if rows else None


def _o5(events):
    rows = _of(events, "agent.decision")
    cases = _cases(events)
    agents = sorted({e["agent_id"] for e in rows if isinstance(e.get("agent_id"), str)})
    if not cases or not agents:
        return None
    return {a: _tokens([e for e in rows if e.get("agent_id") == a]) / cases for a in agents}


def _o6(events):
    rows = _of(events, "agent.decision")
    bad = sum(1 for e in rows if e.get("status") != "ok")
    return _ratio(100.0 * bad, len(rows))


def _o7(events):
    rows = _of(events, "tool.call")
    bad = sum(1 for e in rows if e.get("status") != "ok")
    return _ratio(100.0 * bad, _cases(events)) if rows else None


def _o8(events):
    rows = _of(events, "human.review")
    return _ratio(100.0 * sum(1 for e in rows if e.get("override_flag") is True), len(rows))


def _o9(events):
    rows = [e for e in _of(events, "human.review") if isinstance(e.get("override_flag"), bool)]
    return _ratio(100.0 * sum(1 for e in rows if not e["override_flag"]), len(rows))


def _o10(events):
    rows = _of(events, "guardrail.triggered")
    if not rows:
        return None
    counts: dict[str, int] = {}
    for e in rows:
        kind = str(e.get("guardrail_event"))
        counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


_CALC = {"KPI_O1": _o1, "KPI_O2": _o2, "KPI_O3": _o3, "KPI_O4": _o4, "KPI_O5": _o5, "KPI_O6": _o6, "KPI_O7": _o7,
         "KPI_O8": _o8, "KPI_O9": _o9, "KPI_O10": _o10}


def calculate(events: list[dict]) -> dict[str, Any]:
    """One key for each owed KPI. None for a degraded KPI, a missing denominator or no events."""
    events = list(events or [])
    result: dict[str, Any] = {}
    for kpi in KPIS:
        kpi_id = kpi["kpi_id"]
        result[kpi_id] = None if (not events or kpi_id in DEGRADED) else _CALC[kpi_id](events)
    return result


def _day(event: dict) -> str:
    at = event.get("at")
    if not isinstance(at, str):
        raise ValueError("event has no `at` ISO time")
    try:
        moment = datetime.fromisoformat(at)
    except ValueError as error:
        raise ValueError(f"`at` is not an ISO time: {at}") from error
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).date().isoformat()


def backfill(events: list[dict]) -> dict[str, dict[str, Any]]:
    days: dict[str, list[dict]] = {}
    for event in events or []:
        days.setdefault(_day(event), []).append(event)
    return {day: calculate(days[day]) for day in sorted(days)}


def alerts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Raise from ALERT_RULES only. A rule with limit None is prose and raises nothing."""
    raised = []
    for kpi_id, rule in ALERT_RULES.items():
        value = (snapshot or {}).get(kpi_id)
        if not _num(value):
            continue
        if "event" in rule:
            limit, direction = 0, "above"
        else:
            limit, direction = rule.get("limit"), rule.get("direction")
        if limit is None or direction not in ("above", "below"):
            continue
        if (direction == "above" and value > limit) or (direction == "below" and value < limit):
            raised.append({"kpi_id": kpi_id, "value": value, "threshold": limit, "condition": direction,
                           "owner": rule["owner"]})
    return raised


def deliver(alert: dict[str, Any]) -> bool:
    """Append the alert as one JSON line to SOLUTION_ALERT_SINK. LOG_SINK is the declared destination."""
    sink = os.environ.get("SOLUTION_ALERT_SINK")
    if not sink:
        return False
    with open(sink, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(alert, sort_keys=True) + "\n")
    return True


def _canonical(event: dict) -> str:
    return json.dumps(event, sort_keys=True)


def _event_id(event: dict) -> str:
    if event.get("event_id") is not None:
        return str(event["event_id"])
    return hashlib.sha256(_canonical(event).encode()).hexdigest()


class KpiEventStore:
    """One row for each event ID. SQLite by default; StateStore('kpi-events') when DATABASE_URL is set."""

    _INDEX = "~index"

    def __init__(self, path: Any = None) -> None:
        self._lock = threading.RLock()
        self._durable = None
        self._db = None
        if os.environ.get("DATABASE_URL"):
            from solution.state import StateStore  # imported here: it needs the database driver

            self._durable = StateStore("kpi-events")
            return
        self._db = sqlite3.connect(str(path) if path else ":memory:", check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, "
                         "event_id TEXT UNIQUE NOT NULL, body TEXT NOT NULL)")
        self._db.commit()

    def ingest(self, event: dict) -> None:
        event_id, body = _event_id(event), _canonical(event)
        with self._lock:
            if self._durable is not None:
                known = self._durable.get(event_id)
                if known is None:
                    self._durable.put(event_id, event)
                    self._durable.put(self._INDEX, list(self._durable.get(self._INDEX, [])) + [event_id])
                elif _canonical(known) != body:
                    raise ValueError(f"event {event_id} repeats with other content")
                return
            row = self._db.execute("SELECT body FROM events WHERE event_id=?", (event_id,)).fetchone()
            if row is None:
                self._db.execute("INSERT INTO events (event_id, body) VALUES (?, ?)", (event_id, body))
                self._db.commit()
            elif row[0] != body:
                raise ValueError(f"event {event_id} repeats with other content")

    def events(self) -> list[dict]:
        with self._lock:
            if self._durable is not None:
                ids = self._durable.get(self._INDEX, [])
                return [self._durable.get(i) for i in ids]
            return [json.loads(b) for (b,) in self._db.execute("SELECT body FROM events ORDER BY seq")]

    def close(self) -> None:
        if self._db is not None:
            self._db.close()


def kpi_store_path() -> Path:
    base = os.environ.get("PREVIEW_DATA_DIR")
    folder = Path(base) if base else Path(__file__).resolve().parents[2] / ".preview-data"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "kpis.sqlite"


def feed_events(events: list[dict]) -> int:
    store = KpiEventStore(kpi_store_path())
    try:
        for event in events:
            store.ingest(event)
        return len(store.events())
    finally:
        store.close()


def playground_kpis_payload(store: KpiEventStore) -> dict[str, Any]:
    values = calculate(store.events())
    entries = {}
    for kpi in KPIS:
        kpi_id = kpi["kpi_id"]
        value = values[kpi_id]
        entries[kpi_id] = {
            "value": value,
            "unit": kpi["unit"],
            "status": "measured" if value is not None and kpi_id not in DEGRADED else "unmeasured",
            "source_ref": kpi["source_ref"],
            "source_system": kpi["source_system"],
            "visualization": kpi.get("visualization"),  # kpis.csv has no visualization column; see the gaps
        }
    return {"kpis": entries}
