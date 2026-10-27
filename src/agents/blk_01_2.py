"""BLK_01.2 Bank Details Validation, a sub-agent of BLK_01 (Intake & Verification Agent Block).

Validates and verifies bank account details and IFSC codes for commission payouts through TOOL_01.
The parent BLK_01 owns ACT_01 to ACT_04 and the rules that bind them; this module owns no action.
Sources: agent_specifications@row:1, tacit_knowledge@row:3, not_automated_register@row:1,
not_automated_register@row:2, integration_point_inventory@row:4.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

REQUIREMENT_REFS = (
    "BLK_01.2",
    "BLK_01",
    "agent_specifications@row:1",
    "tacit_knowledge@row:3",
    "not_automated_register@row:1",
    "not_automated_register@row:2",
    "HR-201:BLK_01:TOOL_01",
)

AGENT_ID = "BLK_01.2"
PARENT_AGENT_ID = "BLK_01"
AGENT_NAME = "Bank Details Validation"
ADK_NAME = "blk_01_2"

# agents.yaml declares no value for these on BLK_01.2; the values are those of its parent BLK_01.
MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.0
TIMEOUT_S = 30
MAX_RETRIES = 3
MAX_OUTPUT_TOKENS = 1024
AUTONOMY = "act_with_review"
DECISION_TYPE = "hybrid"
MEMORY_MODE = "Session state"
GROUNDING_MODE = "Full-context injection"

SERVES_STEPS = ("S1", "S2", "S3", "S4")
PERSON_STEPS = ("S6", "S8")
FORBIDDEN_STEPS = PERSON_STEPS

TOOLS = ["TOOL_01"]
TOOL_BINDINGS = {"validate_bank_details": "TOOL_01"}

# agents.yaml declares no audit_events for BLK_01.2 (only its parent BLK_01 does).
AUDIT_EVENTS: tuple[str, ...] = ()

FAILURE_BEHAVIOUR = {
    "text": "Halt automatic progression, log failure trace, and flag case for human review with specific error context."
}

# BLK_01.2 declares no action, exception or interaction of its own.
ACTIONS: dict[str, dict[str, Any]] = {}
EXCEPTIONS: dict[str, dict[str, Any]] = {}
INTERACTIONS: dict[str, dict[str, Any]] = {}
COMPLETION_CONDITIONS: list[str] = []

# H-xx choices of BLK_01.2 owed at the Pilot rung or below. Not-applicable rows are left out.
HARNESS = {
    "H-01": "Single agent",
    "H-02": "Code tool",
    "H-03": "Multimodal / vision",
    "H-04": "OCR / IDP · Docling + multimodal LLM",
    "H-05": "Full-context injection",
    "H-06": "Session state",
    "H-07": "Direct",
    "H-08": "Enforced response schema",
    "H-09": "Allowlist",
    "H-10": "Inbound channel message",
    "H-12": "Per-field extraction score",
    "H-13": "Full (input · output · action)",
    "H-14": "Degrade to human",
    "H-15": "Latency target",
    "H-16": "Few-shot examples",
    "H-19": "Document",
    "H-21": "Tracing on · version IDs on every event",
}

GUARDRAILS = {
    "GR-01": {"status": "enforced", "enforced_by": "enforce_gr_01"},
    "GR-02": {"status": "enforced", "enforced_by": "enforce_gr_02"},
    "GR-03": {"status": "enforced", "enforced_by": "enforce_gr_03"},
    "GR-04": {"status": "enforced", "enforced_by": "enforce_gr_04"},
}
_GUARDRAIL_TEXT = {
    "GR-01": "refuse to write outside the tools declared in spec/tools.yaml",
    "GR-02": "no automation of any step listed in spec/not_automated.csv",
    "GR-03": "enforce every blocking rule in spec/rules.csv before an agent's output is written",
    "GR-04": "escalate rather than decide when a required field is in spec/open_items.csv",
}
# Guardrails that bind every agent, in the order run_case enforces them.
_ALL_AGENT_GUARDRAILS = ("enforce_gr_01", "enforce_gr_02", "enforce_gr_03", "enforce_gr_04")

# Fields this agent's tool carries (the reads and writes of ACT_04 on TOOL_01).
BANK_FIELDS = (
    "IFSC Code",
    "Bank Account Number",
    "Name As In Bank Account",
    "Bank Name",
    "Bank City",
    "Branch Name",
    "Bank verification status",
)

INPUT_SCHEMA = {
    "$id": "BLK_01.in.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "_provenance": {},
    "description": "No surface with a matching action is mapped to S1, S2, S3, S4, so nothing is known about what BLK_01 reads at it. That is an absence in the surface registers, not a statement that the agent touches nothing.",
    "properties": {},
    "required": [],
    "title": "BLK_01 input",
    "type": "object",
}

OUTPUT_SCHEMA = {
    "$id": "BLK_01.out.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "_provenance": {},
    "description": "No surface with a matching action is mapped to S1, S2, S3, S4, so nothing is known about what BLK_01 writes at it. That is an absence in the surface registers, not a statement that the agent touches nothing.",
    "properties": {},
    "required": [],
    "title": "BLK_01 output",
    "type": "object",
}


class GuardrailRefusal(Exception):
    """A blocking rule refused the write it guards."""

    def __init__(self, rule_id: str, message: str):
        super().__init__(message)
        self.rule_id = rule_id
        self.message = message


def allowed_step(step: Any) -> bool:
    """True only for a step this agent serves. A person step is never allowed."""
    if step in PERSON_STEPS:
        return False
    return step in SERVES_STEPS


def enforce_gr_01(case: Any = None, *, tool_ids: Any = (), **_: Any) -> None:
    """GR-01: refuse a write through a tool that this agent does not declare."""
    for tool_id in tool_ids:
        if tool_id not in TOOLS:
            raise GuardrailRefusal("GR-01", f"GR-01: {_GUARDRAIL_TEXT['GR-01']} ({tool_id})")


def enforce_gr_02(case: Any = None, *, step_id: Any = None, **_: Any) -> None:
    """GR-02: refuse to automate a step that a person owns or that this agent does not serve."""
    if step_id is not None and not allowed_step(step_id):
        raise GuardrailRefusal("GR-02", f"GR-02: {_GUARDRAIL_TEXT['GR-02']} ({step_id})")


def enforce_gr_03(case: Any = None, *, failed_rules: Any = (), **_: Any) -> None:
    """GR-03: refuse to write the output while a blocking rule has refused."""
    if failed_rules:
        raise GuardrailRefusal("GR-03", f"GR-03: {_GUARDRAIL_TEXT['GR-03']} ({', '.join(map(str, failed_rules))})")


def enforce_gr_04(case: Any = None, *, open_fields: Any = (), **_: Any) -> None:
    """GR-04: escalate, never decide, when a field this agent needs is an open item."""
    needed = [f for f in open_fields if f in BANK_FIELDS]
    if needed:
        raise GuardrailRefusal("GR-04", f"GR-04: {_GUARDRAIL_TEXT['GR-04']} ({', '.join(needed)})")


def handle_failure(case_id: str, error: Any) -> dict[str, Any]:
    """Halt automatic progression and flag the case for human review with the error context."""
    return {
        "status_tag": "halted_for_human_review",
        "alert": True,
        "case_id": case_id,
        "error": f"{type(error).__name__}: {error}",
        "route": "human_review",
        "behaviour": FAILURE_BEHAVIOUR["text"],
    }


def handle_exception(exception_id: str, case_id: str, error: Any) -> dict[str, Any]:
    """Route a named exception. BLK_01.2 declares none, so an unknown ID degrades to human review."""
    spec = EXCEPTIONS.get(exception_id)
    result = handle_failure(case_id, error)
    result["status_tag"] = "exception_" + str(exception_id).lower()
    result["escalation_route"] = spec["escalation_route"] if spec else "human_review"
    result["resume_from"] = spec["resume_from"] if spec else None
    return result


def emit_event(event_name: str, case_id: str, **fields: Any) -> dict[str, Any]:
    """Build one event with every required field of event.schema.json and feed it to the KPI store."""
    now = datetime.now(timezone.utc).isoformat()
    event: dict[str, Any] = {
        "case_id": case_id,
        "step_id": "",
        "agent_id": AGENT_ID,
        "event_type": event_name,
        "actor_type": "agent",
        "actor_id": AGENT_ID,
        "ts_start": now,
        "ts_end": now,
        "model": MODEL,
        "prompt_version": "prompts/BLK_01.md",
        "agent_version": "1",
        "tokens_in": 0,
        "tokens_out": 0,
        "cost": 0.0,
        "status": "ok",
        "confidence": 1.0,
        "override_flag": False,
        "override_reason": "",
        "guardrail_event": "",
    }
    event.update(fields)
    event["event_type"] = event_name
    event["case_id"] = case_id
    try:
        from kpis.service import feed_events
    except ModuleNotFoundError as exc:
        if exc.name not in ("kpis", "kpis.service"):
            raise
        return event
    feed_events([event])
    return event


def _routed(case_id: str, case: dict[str, Any], trace: list[str], exc_id: Any, error: Exception) -> dict[str, Any]:
    route = handle_exception(exc_id, case_id, error) if exc_id else handle_failure(case_id, error)
    return {"case": dict(case), "trace": trace, "outcome": "routed", "next": None, "route": route}


def _guard(case: dict[str, Any], spec: dict[str, Any]) -> None:
    """Run every universal guardrail, looked up by name at call time."""
    for name in _ALL_AGENT_GUARDRAILS:
        globals()[name](case, tool_ids=spec.get("tool_ids", ()), step_id=spec.get("step_id"))


def run_case(case_id: str, case: dict[str, Any]) -> dict[str, Any]:
    """Run the declared actions in order. BLK_01.2 declares none, so only the guardrails run."""
    current = dict(case)
    trace: list[str] = []
    next_action = next(iter(ACTIONS), None)
    if next_action is None:
        try:
            _guard(current, {})
        except Exception as error:
            return _routed(case_id, case, trace, None, error)
    last_next = None
    while next_action is not None:
        spec = ACTIONS[next_action]
        try:
            _guard(current, spec)
            writes = globals()[spec["function"]](current)
        except Exception as error:
            return _routed(case_id, case, trace, spec.get("on_failure"), error)
        current = {**current, **writes}
        trace.append(next_action)
        emit_event("step.completed", case_id, step_id=spec["step_id"])
        last_next = spec.get("on_success")
        next_action = last_next if last_next in ACTIONS else None
    return {"case": current, "trace": trace, "outcome": "completed", "next": last_next, "route": None}


def validate_input(data: Any) -> None:
    """Validate agent input against INPUT_SCHEMA."""
    import jsonschema

    jsonschema.validate(data, INPUT_SCHEMA)


def validate_output(data: Any) -> None:
    """Validate agent output against OUTPUT_SCHEMA."""
    import jsonschema

    jsonschema.validate(data, OUTPUT_SCHEMA)


_JSON_TYPES = {"string": str, "integer": int, "number": float, "boolean": bool, "object": dict, "array": list}


def _output_model() -> Any:
    from pydantic import create_model

    fields = {}
    for name, spec in OUTPUT_SCHEMA["properties"].items():
        py_type = _JSON_TYPES.get(spec.get("type"), Any)
        fields[name] = (py_type, ... if name in OUTPUT_SCHEMA["required"] else None)
    return create_model("BLK_01Output", **fields)


def _instruction() -> str:
    keys = list(OUTPUT_SCHEMA["properties"])
    required = list(OUTPUT_SCHEMA["required"])
    return (
        "You are the Bank Details Validation agent, a sub-agent of the Intake & Verification Agent Block. "
        "You validate and verify bank account details and IFSC codes for commission payouts. "
        "You work on the case you were given, only through validate_bank_details (TOOL_01). "
        "Pass the IFSC Code, Bank Account Number and Name As In Bank Account to the tool and report what it returns. "
        "A field you cannot fill is reported as unknown, never inferred. "
        "Never execute manual overrides or bypass a verification failure. "
        "When the tool fails or verification does not pass, halt automatic progression, log the failure trace, "
        "and flag the case for human review with the specific error context. "
        "Never automate step S6 (consent and declaration) or step S8 (training and exam): a person does them. "
        "Answer with one JSON object whose keys are only these output fields: "
        + (", ".join(keys) if keys else "(none: the output schema declares no field)")
        + ". Required fields: "
        + (", ".join(required) if required else "(none)")
        + ". Copy the input value of a required field when this step does not change it. "
        "No other input field goes in the answer."
    )


def validate_bank_details(payload: dict, correlation_id: str) -> dict:
    """Validate bank details and resolve the IFSC code through TOOL_01. Returns the tool response."""
    from integrations.tool_01 import invoke

    return invoke(payload, correlation_id)


def make_agent() -> Any:
    """Build the ADK agent of BLK_01.2."""
    from google.adk.agents import Agent

    from solution.adk_model import generate_adk_config, resolve_adk_model

    model = resolve_adk_model(MODEL, max_retries=MAX_RETRIES)
    config = generate_adk_config(
        model,
        MAX_RETRIES,
        temperature=TEMPERATURE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    return Agent(
        name=ADK_NAME,
        model=model,
        instruction=_instruction(),
        tools=[validate_bank_details],
        output_schema=_output_model(),
        generate_content_config=config,
    )
