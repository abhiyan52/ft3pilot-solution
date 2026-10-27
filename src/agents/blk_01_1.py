"""BLK_01.1 Prospect Intake and Verification, a sub-agent of BLK_01.

Captures initial profile details and performs external KYC and duplicate checks through
TOOL_01 and TOOL_02. The parent BLK_01 owns the actions, their rules and the hand-offs; this
module holds the model, the tools and the guardrails that bind every agent.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Optional

REQUIREMENT_REFS = (
    "BLK_01.1",
    "BLK_01",
    "agent_specifications@row:1",
    "tacit_knowledge@row:3",
    "not_automated_register@row:1",
    "not_automated_register@row:2",
)

AGENT_ID = "BLK_01.1"
PARENT_AGENT_ID = "BLK_01"
AGENT_NAME = "Prospect Intake and Verification"
AGENT_IDENTIFIER = "blk_01_1"

# agents.yaml gives the sub-agent no value for these; each is the value of the parent BLK_01.
MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.0
TIMEOUT_S = 30
MAX_RETRIES = 3
MAX_OUTPUT_TOKENS = 1024
AUTONOMY = "act_with_review"

DECISION_TYPE = "hybrid"
MEMORY_MODE = "Session state"
GROUNDING_MODE = "Full-context injection"
COMPLETION_CONDITIONS = []
PROMPT_VERSION = "prompts/BLK_01.md"
AGENT_VERSION = "1"

# The sub-agent declares no serves_steps; it takes those of BLK_01.
SERVES_STEPS = ("S1", "S2", "S3", "S4")
FORBIDDEN_STEPS = ("S6", "S8")

TOOLS = ["TOOL_01", "TOOL_02"]
TOOL_BINDINGS = {"tool_01": "TOOL_01", "tool_02": "TOOL_02"}

AUDIT_EVENTS = ()
ACTIONS = {}
EXCEPTIONS = {}
INTERACTIONS = {}
OPEN_ITEM_FIELDS = ()

FAILURE_BEHAVIOUR = {
    "text": "Halt automatic progression, log failure trace, and flag case for human review with specific error context.",
}
_ESCALATION_ROUTE = "FLS User / Employee queue"

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

GUARDRAILS = {
    "GR-01": {"status": "enforced", "enforced_by": "enforce_gr_01"},
    "GR-02": {"status": "enforced", "enforced_by": "enforce_gr_02"},
    "GR-03": {"status": "enforced", "enforced_by": "enforce_gr_03"},
    "GR-04": {"status": "enforced", "enforced_by": "enforce_gr_04"},
}
_GUARDRAIL_MESSAGES = {
    "GR-01": "GR-01 refuses: write outside the tools declared in spec/tools.yaml",
    "GR-02": "GR-02 refuses: automation of a step listed in spec/not_automated.csv",
    "GR-03": "GR-03 refuses: a blocking rule in spec/rules.csv is not met",
    "GR-04": "GR-04 refuses: a required field is in spec/open_items.csv; escalate rather than decide",
}

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

INSTRUCTION = """You are the Prospect Intake and Verification agent, a sub-agent of the Intake & Verification Agent Block (BLK_01). You serve the intake and verification steps S1, S2, S3 and S4 of the prospect registration.

Rules for every agent:
- Work only on the case you were given, and only through your declared tools TOOL_01 and TOOL_02.
- Write only the fields your output schema names. A field you cannot fill is reported as unknown, never inferred.
- All arithmetic is deterministic code, never your own.
- Where a value you need is an open item, stop and ask. Do not guess.
- Say what you could not read. A gap reported is a case handled; a gap filled in is a defect nobody can see.

Your work:
- Capture initial profile details: full name, mobile number, email, and the optional Relationship Manager Business Code. Run duplicate checks on email and mobile through TOOL_01.
- Run identity verification by querying the external KYC service with the PAN, Aadhaar and CKYC numbers through TOOL_02.
- Combine user input with pre-filled KYC data to update the agent profile with address and demographic details through TOOL_01.
- You must not execute manual overrides for duplicate records or bypass verification failures without explicit operational approval.
- When an external verification service is unavailable or returns an error, including a Service Temporarily Unavailable banner, halt automatic progression, do not proceed and do not skip the check, log the failure trace, and flag the case for human review through the escalation route to the FLS User / Employee queue.

Never automate these steps:
- S6, Consent and Declaration (regulatory): it needs explicit human legal agreement, active review of terms and conditions, and a secondary OTP verification.
- S8, Post-Approval Training and Exam (relationship): the prospective agent must complete it directly.

Answer with one JSON object whose keys are only these output fields: (none, the output schema declares no property). No field is required. No other input field goes in the answer. Answer with {}."""


class GuardrailRefusal(Exception):
    """A blocking rule refuses the write it guards."""

    def __init__(self, rule_id, message=""):
        self.rule_id = rule_id
        self.message = message or _GUARDRAIL_MESSAGES.get(rule_id, rule_id)
        super().__init__(self.message)


def allowed_step(step):
    """Tell whether this agent may work on the step."""
    if step in FORBIDDEN_STEPS:
        return False
    return step in SERVES_STEPS


def _context_value(case, context, key):
    if key in context:
        return context[key]
    return case.get(key) if isinstance(case, dict) else None


def enforce_gr_01(case=None, **context):
    """GR-01: refuse a write through a tool that is not declared for this agent."""
    tool_ids = _context_value(case, context, "tool_ids")
    tool_id = _context_value(case, context, "tool_id")
    used = list(tool_ids or ([tool_id] if tool_id else []))
    for used_id in used:
        if used_id not in TOOLS:
            raise GuardrailRefusal("GR-01", f"{_GUARDRAIL_MESSAGES['GR-01']} ({used_id})")


def enforce_gr_02(case=None, **context):
    """GR-02: refuse to automate a step that a person does."""
    step = _context_value(case, context, "step_id")
    steps = _context_value(case, context, "step_ids")
    for candidate in ([step] if step else []) + list(steps or []):
        if candidate in FORBIDDEN_STEPS:
            raise GuardrailRefusal("GR-02", f"{_GUARDRAIL_MESSAGES['GR-02']} ({candidate})")


def enforce_gr_03(case=None, **context):
    """GR-03: refuse an output while a blocking rule of spec/rules.csv is unmet."""
    violations = _context_value(case, context, "rule_violations")
    if violations:
        names = ", ".join(str(item) for item in (violations if not isinstance(violations, str) else [violations]))
        raise GuardrailRefusal("GR-03", f"{_GUARDRAIL_MESSAGES['GR-03']} ({names})")


def enforce_gr_04(case=None, **context):
    """GR-04: refuse to decide when a required field is an open item."""
    unresolved = [*(_context_value(case, context, "open_item_fields") or ()), *OPEN_ITEM_FIELDS]
    required = _context_value(case, context, "required_fields")
    blocked = sorted({str(name) for name in unresolved if required is None or name in required})
    if blocked:
        raise GuardrailRefusal("GR-04", f"{_GUARDRAIL_MESSAGES['GR-04']} ({', '.join(blocked)})")


_UNIVERSAL_ENFORCERS = tuple(item["enforced_by"] for item in GUARDRAILS.values())


def _validator(schema):
    from jsonschema import Draft202012Validator

    return Draft202012Validator(schema)


def validate_input(case):
    """Raise ValueError when the case does not satisfy INPUT_SCHEMA."""
    errors = sorted(_validator(INPUT_SCHEMA).iter_errors(case), key=lambda item: list(item.path))
    if errors:
        raise ValueError("input does not satisfy INPUT_SCHEMA: " + "; ".join(error.message for error in errors))
    return case


def validate_output(answer):
    """Raise ValueError when the answer does not satisfy OUTPUT_SCHEMA."""
    errors = sorted(_validator(OUTPUT_SCHEMA).iter_errors(answer), key=lambda item: list(item.path))
    if errors:
        raise ValueError("output does not satisfy OUTPUT_SCHEMA: " + "; ".join(error.message for error in errors))
    return answer


def emit_event(event_name, case_id, **fields):
    """Build one event of schemas/event.schema.json and feed it to the KPI store."""
    now = datetime.now(timezone.utc).isoformat()
    event = {
        "case_id": case_id,
        "step_id": "",
        "agent_id": AGENT_ID,
        "event_type": event_name,
        "actor_type": "agent",
        "actor_id": AGENT_ID,
        "ts_start": now,
        "ts_end": now,
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "agent_version": AGENT_VERSION,
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
    except ModuleNotFoundError as error:
        if error.name not in ("kpis", "kpis.service"):
            raise
        return event
    feed_events([event])
    return event


def handle_exception(exception_id, case_id, error):
    """Route a declared exception to a person. This agent declares none; the parent BLK_01 owns EXC_01 and EXC_02."""
    declared = EXCEPTIONS.get(exception_id, {})
    return {
        "case_id": case_id,
        "exception_id": exception_id,
        "escalation_route": declared.get("escalation_route", _ESCALATION_ROUTE),
        "resume_from": declared.get("resume_from"),
        "status_tag": "exception_" + str(exception_id).lower(),
        "alert": True,
        "error": str(error),
    }


def handle_failure(case_id, error):
    """Halt automatic progression, keep the failure trace and flag the case for human review."""
    return {
        "case_id": case_id,
        "status_tag": "halted_for_human_review",
        "alert": True,
        "escalation_route": _ESCALATION_ROUTE,
        "error": f"{type(error).__name__}: {error}",
        "behaviour": FAILURE_BEHAVIOUR["text"],
    }


def run_case(case_id, case):
    """Run the declared actions in order. This agent declares none, so only the guardrails run."""
    working = copy.deepcopy(case)
    trace = []
    next_action = None
    try:
        validate_input(working)
        if not ACTIONS:
            for name in _UNIVERSAL_ENFORCERS:
                globals()[name](working)
        for action_id, spec in ACTIONS.items():
            for name in _UNIVERSAL_ENFORCERS:
                globals()[name](working)
            writes = globals()[spec["function"]](working)
            working = {**working, **writes}
            trace.append(action_id)
            next_action = spec.get("on_success")
            if "step.completed" in AUDIT_EVENTS:
                emit_event("step.completed", case_id, step_id=spec["step_id"])
    except GuardrailRefusal as error:
        return {"case": working, "trace": trace, "outcome": "routed", "next": None, "route": handle_failure(case_id, error)}
    except Exception as error:
        failed = ACTIONS.get(trace[-1] if trace else "", {})
        route = handle_exception(failed["on_failure"], case_id, error) if failed.get("on_failure") else handle_failure(case_id, error)
        return {"case": working, "trace": trace, "outcome": "routed", "next": None, "route": route}
    return {"case": working, "trace": trace, "outcome": "completed", "next": next_action, "route": None}


def _call_tool(tool_id, module_name, payload, correlation_id):
    enforce_gr_01(None, tool_id=tool_id)
    from importlib import import_module

    invoke = import_module(f"integrations.{module_name}").invoke
    return invoke(payload, correlation_id)


def tool_01(payload: dict, correlation_id: str) -> dict:
    """TOOL_01: read and write the prospect record, profile and bank details. Pass the case ID as correlation_id."""
    return _call_tool("TOOL_01", "tool_01", payload, correlation_id)


def tool_02(payload: dict, correlation_id: str) -> dict:
    """TOOL_02: query the external KYC service with PAN, Aadhaar and CKYC numbers. Pass the case ID as correlation_id."""
    return _call_tool("TOOL_02", "tool_02", payload, correlation_id)


_JSON_TYPES = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list, "object": dict}


def _output_model():
    from pydantic import create_model

    required = set(OUTPUT_SCHEMA.get("required", []))
    fields = {}
    for name, spec in OUTPUT_SCHEMA.get("properties", {}).items():
        python_type = _JSON_TYPES.get(spec.get("type"), object)
        fields[name] = (python_type, ...) if name in required else (Optional[python_type], None)
    return create_model("BLK_01_1_Output", **fields)


def make_agent():
    """Build the ADK agent of this sub-agent. The parent BLK_01 composes it."""
    from google.adk.agents import Agent

    from solution.adk_model import generate_adk_config, resolve_adk_model

    model = resolve_adk_model(MODEL, max_retries=MAX_RETRIES)
    config = generate_adk_config(model, MAX_RETRIES, temperature=TEMPERATURE, max_output_tokens=MAX_OUTPUT_TOKENS)
    return Agent(
        name=AGENT_IDENTIFIER,
        model=model,
        instruction=INSTRUCTION,
        tools=[tool_01, tool_02],
        output_schema=_output_model(),
        generate_content_config=config,
    )
