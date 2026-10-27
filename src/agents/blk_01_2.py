"""BLK_01.2 · Bank Details Validation, a sub-agent of BLK_01 (Intake & Verification Agent Block).

Purpose (agents.yaml BLK_01.2): validates and verifies bank account details and IFSC codes for commission payouts.

The parent BLK_01 composes this agent with google.adk.agents.SequentialAgent. This module never calls another agent.
The block actions (ACT_01..ACT_04), their rules (BR-ACT_*), exceptions (EXC_*) and interaction (INT_01) belong to
the parent, which enforces them in its own run_case. This sub-agent declares none of its own, so ACTIONS, EXCEPTIONS
and INTERACTIONS are empty and run_case finishes with no action.

agents.yaml declares no model, temperature, timeout, retries, autonomy, failure behaviour, schemas, prompt or served
steps for BLK_01.2. Each of those is taken from the parent BLK_01 and noted as an assumption below. It declares no
audit events either; AUDIT_EVENTS stays empty and the parent emits its own.
TOOL_01 is a labelled mock (open item HR-201:BLK_01:TOOL_01) and blocks promotion.
"""
from __future__ import annotations

import copy
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

REQUIREMENT_REFS = (
    "BLK_01.2",
    "agents.yaml#BLK_01.2",
    "agents.yaml#BLK_01",
    "agent_specifications@row:1",
    "tacit_knowledge@row:2",
    "tacit_knowledge@row:3",
    "not_automated_register@row:1",
    "not_automated_register@row:2",
    "instrumentation_contract@row:1",
    "standard/runtime.defaults.yaml#guardrails[1]",
    "standard/runtime.defaults.yaml#guardrails[2]",
    "standard/runtime.defaults.yaml#guardrails[3]",
    "standard/runtime.defaults.yaml#guardrails[4]",
    "open_items@HR-201:BLK_01:TOOL_01",
)

AGENT_ID = "BLK_01.2"
AGENT_NAME = "blk_01_2"
PARENT_AGENT_ID = "BLK_01"
DISPLAY_NAME = "Bank Details Validation"
PURPOSE = "Validates and verifies bank account details and IFSC codes for commission payouts."

# Assumption: BLK_01.2 declares none of these; the values are those of its parent BLK_01 in agents.yaml.
MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.0
TIMEOUT_S = 30
MAX_RETRIES = 3
AUTONOMY = "act_with_review"
# The instructions name the parent value for a sub-agent that declares none.
MAX_OUTPUT_TOKENS = 1024

DECISION_TYPE = "hybrid"
MEMORY_MODE = "Session state"
GROUNDING_MODE = "Full-context injection"
BUDGETS = {"max_latency_ms": 30000, "max_tokens_per_case": 4096}
FEW_SHOT: tuple[dict[str, Any], ...] = ()

# Assumption: the parent's serves_steps; BLK_01.2 declares none.
SERVES_STEPS = ("S1", "S2", "S3", "S4")
# context person_steps; also spec/not_automated.csv (EX_01, EX_02).
FORBIDDEN_STEPS = ("S6", "S8")
CHECKPOINTS = ("CHK_01",)

TOOLS = ("TOOL_01",)
TOOL_BINDINGS = {"tool_01": "TOOL_01"}

# agents.yaml declares no audit_events for BLK_01.2 (a gap). The parent BLK_01 emits its own.
AUDIT_EVENTS: tuple[str, ...] = ()

FAILURE_BEHAVIOUR = {
    "text": "Halt automatic progression, log failure trace, and flag case for human review with specific error context."
}
# The BLK_01 prompt names this route for failures and unavailable verification services.
FAILURE_ROUTE = "FLS User / Employee queue"

# Precord v2 action graph. The sub-agent owns no action; the parent BLK_01 runs ACT_01..ACT_04.
ACTIONS: dict[str, dict[str, Any]] = {}
FIRST_ACTION: str | None = next(iter(ACTIONS), None)
EXCEPTIONS: dict[str, dict[str, str]] = {}
INTERACTIONS: dict[str, dict[str, str]] = {}

# Rows owed at or below Pilot, less "Not applicable" (H-11, H-18). H-17 and H-20 are owed at MVP.
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

# Assumption: BLK_01.2 has no schema file; these are schemas/BLK_01.in.schema.json and BLK_01.out.schema.json.
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
EVENT_SCHEMA_REQUIRED = (
    "case_id", "step_id", "agent_id", "event_type", "actor_type", "actor_id", "ts_start", "ts_end", "model",
    "prompt_version", "agent_version", "tokens_in", "tokens_out", "cost", "status", "confidence", "override_flag",
    "override_reason", "guardrail_event",
)

# Open items that touch this agent (spec/open_items.csv). GR-04 escalates on an unanswered one that blocks.
OPEN_ITEMS = {
    "HR-201:BLK_01:TOOL_01": {
        "status": "open", "answer": "", "blocking": "false", "detail": "BLK_01",
        "default_assumption": "Stub the tool on sample data until it exists",
    },
}

INSTRUCTION = """\
# BLK_01.2 · Bank Details Validation

## 1 · Platform frame — shared

You are one agent in a specified process. The specification is the repository you were built from, and it is the authority — where it and your judgement disagree, the specification wins and you say so.

- Work only on the case you were given, and only through your declared tools.
- Write only the fields your output schema names. A field you cannot fill is reported as unknown, never inferred.
- Use the canonical names in `context/glossary.csv` for everything you write.
- All arithmetic is deterministic code, never your own. Ask for the number.
- Apply every rule in `spec/rules.csv` that names you, a step you serve, or a field you write.
- Where a value you need is in `spec/open_items.csv`, stop and ask. Do not guess.
- Say what you could not read. A gap reported is a case handled; a gap filled in is a defect nobody can see.

## 2 · Agent instruction

You are the Bank Details Validation sub-agent of the Intake & Verification Agent Block (BLK_01).
You validate and verify bank account details and IFSC codes for commission payouts.
Your only tool is tool_01 (TOOL_01). Pass it a payload whose "action_id" is the block action you serve and whose other keys are that action's reads. Report what it returns; do not fill in a field it leaves empty.
You must not execute manual overrides for duplicate records or bypass verification failures without explicit operational approval.
When a verification service is unavailable or an error occurs, halt, say so, and leave the case for human review in the FLS User / Employee queue.

### Never automate these

- S6 (regulatory): Consent and declaration require explicit human legal agreement, active review of terms and conditions, and a secondary OTP verification step bound by regulatory compliance rules.
- S8 (relationship): Post-approval training modules and the POSP certification exam must be completed directly by the prospective agent to satisfy regulatory competency standards.

## 3 · Domain pack — shared vocabulary

| Term | Also called | Means |
| --- | --- | --- |
| Bank Account | Account Number, Account Type, Bank City, Bank Details, Bank Name, Bank Verification, Branch Name, cancelled cheque | The financial destination and associated parameters recorded for agent payouts and verification. |
| Agent | FLS User, Onboard POSP, POSP Name | The individual undergoing onboarding to become a certified sales representative or Point of Sales Person. |

## 4 · Answer

Answer with one JSON object whose keys are only these output fields: (none — the output schema names no field).
The output schema names no required field, so there is no input value to copy.
No other input field goes in the answer. Answer with the empty object {}.
"""

PROMPT_VERSION = hashlib.sha256(INSTRUCTION.encode("utf-8")).hexdigest()[:12]
AGENT_VERSION = hashlib.sha256(
    repr((AGENT_ID, MODEL, TEMPERATURE, MAX_RETRIES, AUTONOMY, TOOLS, SERVES_STEPS, PROMPT_VERSION)).encode("utf-8")
).hexdigest()[:12]

_log = logging.getLogger("solution.BLK_01.2")


class GuardrailRefusal(Exception):
    """A blocking rule refused the work it guards. The message is the rule's message."""

    def __init__(self, rule_id: str, message: str):
        super().__init__(f"{rule_id}: {message}")
        self.rule_id = rule_id
        self.message = message


def allowed_step(step: Any) -> bool:
    """Tell whether this agent may act at `step`. A person step never is."""
    return step in SERVES_STEPS and step not in FORBIDDEN_STEPS


def _context(case: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    merged = dict(case) if isinstance(case, dict) else {}
    merged.update(kwargs)
    return merged


def enforce_declared_tools(case: Any = None, **kwargs: Any) -> None:
    """GR-01: refuse to write outside the tools declared in spec/tools.yaml."""
    ctx = _context(case, kwargs)
    tool_id = ctx.get("tool_id")
    if tool_id is not None and tool_id not in TOOLS:
        raise GuardrailRefusal("GR-01", f"refuse to write outside the tools declared in spec/tools.yaml: {tool_id!r}")


def enforce_not_automated(case: Any = None, **kwargs: Any) -> None:
    """GR-02: no automation of any step listed in spec/not_automated.csv, nor of a step this agent does not serve."""
    ctx = _context(case, kwargs)
    step_id = ctx.get("step_id")
    if step_id is not None and not allowed_step(step_id):
        raise GuardrailRefusal("GR-02", f"no automation of any step listed in spec/not_automated.csv: {step_id!r}")


def enforce_blocking_rules(case: Any = None, **kwargs: Any) -> None:
    """GR-03: enforce every blocking rule before an output is written.

    No business rule of spec/rules.csv binds this sub-agent. What remains is the output contract: a write may only
    name OUTPUT_SCHEMA fields and must validate against OUTPUT_SCHEMA."""
    ctx = _context(case, kwargs)
    writes = ctx.get("writes")
    if writes is None:
        return
    if not isinstance(writes, dict):
        raise GuardrailRefusal("GR-03", "enforce every blocking rule in spec/rules.csv before an agent's output is written")
    extra = sorted(set(writes) - set(OUTPUT_SCHEMA["properties"]))
    if extra:
        raise GuardrailRefusal("GR-03", f"the output schema does not name {extra}")
    _validate(writes, OUTPUT_SCHEMA, "GR-03")


def enforce_open_items(case: Any = None, **kwargs: Any) -> None:
    """GR-04: escalate rather than decide when a required field is in spec/open_items.csv."""
    ctx = _context(case, kwargs)
    items = dict(OPEN_ITEMS)
    for item in ctx.get("open_items") or ():
        if isinstance(item, dict) and item.get("item_id"):
            items[item["item_id"]] = item
    required = set(INPUT_SCHEMA["required"]) | set(OUTPUT_SCHEMA["required"]) | set(ctx.get("required_fields") or ())
    for item_id, item in items.items():
        unanswered = not str(item.get("answer") or "").strip()
        if not unanswered:
            continue
        if str(item.get("blocking")).lower() == "true" or item.get("detail") in required or item.get("field") in required:
            raise GuardrailRefusal(
                "GR-04", f"escalate rather than decide when a required field is in spec/open_items.csv: {item_id}")


GUARDRAILS = {
    "GR-01": {"status": "enforced", "enforced_by": "enforce_declared_tools"},
    "GR-02": {"status": "enforced", "enforced_by": "enforce_not_automated"},
    "GR-03": {"status": "enforced", "enforced_by": "enforce_blocking_rules"},
    "GR-04": {"status": "enforced", "enforced_by": "enforce_open_items"},
}
# Rules of kind guardrail bind every agent; run_case calls these before each action.
ALL_AGENT_RULES = ("GR-01", "GR-02", "GR-03", "GR-04")


def _validate(payload: Any, schema: dict[str, Any], rule_id: str) -> None:
    import jsonschema

    try:
        jsonschema.validate(payload, schema)
    except jsonschema.ValidationError as error:
        raise GuardrailRefusal(rule_id, f"schema {schema.get('$id')}: {error.message}") from error


def validate_input(payload: Any) -> None:
    """Validate an agent input against INPUT_SCHEMA."""
    _validate(payload, INPUT_SCHEMA, "GR-03")


def validate_output(payload: Any) -> None:
    """Validate an agent answer against OUTPUT_SCHEMA and the GR-03 write contract."""
    globals()[GUARDRAILS["GR-03"]["enforced_by"]](writes=payload)


def emit_event(event_name: str, case_id: str, **fields: Any) -> dict[str, Any]:
    """Build one event of schemas/event.schema.json and feed it to the Playground KPI store.

    run_case and the tool wrapper emit only events in AUDIT_EVENTS; this builder serves any caller."""
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
        "prompt_version": PROMPT_VERSION,
        "agent_version": AGENT_VERSION,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost": 0.0,
        "status": "ok",
        "confidence": 1.0,
        "override_flag": False,
        "override_reason": "",
        "guardrail_event": "none",
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


def handle_failure(case_id: str, error: Any) -> dict[str, Any]:
    """Halt automatic progression, log the failure trace, and flag the case for human review with the error context."""
    _log.error("BLK_01.2 halted case %s: %r", case_id, error, extra={"correlation_id": case_id})
    return {
        "case_id": case_id,
        "agent_id": AGENT_ID,
        "status_tag": "halted_for_human_review",
        "alert": True,
        "halted": True,
        "escalation_route": FAILURE_ROUTE,
        "error_context": f"{type(error).__name__}: {error}",
        "failure_behaviour": FAILURE_BEHAVIOUR["text"],
    }


def handle_exception(exception_id: str, case_id: str, error: Any) -> dict[str, Any]:
    """Route a declared exception to its escalation route. This sub-agent declares none, so any exception degrades
    to the failure behaviour and resumes nowhere until a person acts."""
    declared = EXCEPTIONS.get(exception_id)
    if declared is None:
        routed = handle_failure(case_id, error)
        routed.update({"exception_id": exception_id, "resume_from": None})
        return routed
    return {
        "exception_id": exception_id,
        "case_id": case_id,
        "escalation_route": declared["escalation_route"],
        "resume_from": declared["resume_from"],
        "status_tag": f"exception:{exception_id}",
        "alert": True,
        "error_context": f"{type(error).__name__}: {error}",
    }


def run_case(case_id: str, case: dict[str, Any]) -> dict[str, Any]:
    """Run the declared action graph of this agent on a copy of `case`."""
    original = copy.deepcopy(case)
    working = copy.deepcopy(case)
    trace: list[str] = []
    action_id = FIRST_ACTION
    last_next: str | None = None
    while action_id is not None and action_id in ACTIONS:
        declared = ACTIONS[action_id]
        try:
            for rule_id in ALL_AGENT_RULES:
                globals()[GUARDRAILS[rule_id]["enforced_by"]](
                    working, step_id=declared["step_id"], tool_ids=declared["tool_ids"])
            writes = globals()[declared["function"]](copy.deepcopy(working))
        except Exception as error:  # noqa: BLE001 - every failure routes, as the Precord says
            on_failure = declared.get("on_failure")
            route = handle_exception(on_failure, case_id, error) if on_failure else handle_failure(case_id, error)
            return {"case": working if trace else original, "trace": trace, "outcome": "routed",
                    "next": None, "route": route}
        working.update(writes)
        trace.append(action_id)
        if "step.completed" in AUDIT_EVENTS:
            emit_event("step.completed", case_id, step_id=declared["step_id"])
        last_next = declared.get("on_success")
        action_id = last_next
    return {"case": working, "trace": trace, "outcome": "completed", "next": last_next, "route": None}


def make_agent() -> Any:
    """Build the ADK Agent of BLK_01.2. The parent BLK_01 composes it into its SequentialAgent."""
    import pydantic
    from google.adk.agents import Agent

    from integrations.tool_01 import invoke as tool_01_invoke
    from solution.adk_model import generate_adk_config, resolve_adk_model

    def tool_01(payload: dict[str, Any], correlation_id: str = "") -> dict[str, Any]:
        """Call TOOL_01 (a labelled mock until the tool exists).

        Args:
            payload: "action_id" names the block action; the other keys are that action's reads.
            correlation_id: the case ID; the host fills it in.

        Returns:
            dict: the tool response, with "status" and "response".
        """
        globals()[GUARDRAILS["GR-01"]["enforced_by"]](tool_id=TOOL_BINDINGS["tool_01"])
        result = tool_01_invoke(payload, correlation_id)
        if "tool.call" in AUDIT_EVENTS:
            emit_event("tool.call", correlation_id, status=str(result.get("status") or "ok"))
        return result

    output_model = pydantic.create_model(
        "Blk012Output", **{name: (Any, ...) for name in OUTPUT_SCHEMA["properties"]})
    model = resolve_adk_model(MODEL, max_retries=MAX_RETRIES)
    return Agent(
        name=AGENT_NAME,
        model=model,
        description=PURPOSE,
        instruction=INSTRUCTION,
        tools=[tool_01],
        output_schema=output_model,
        generate_content_config=generate_adk_config(
            model, MAX_RETRIES, temperature=TEMPERATURE, max_output_tokens=MAX_OUTPUT_TOKENS),
    )
