"""BLK_01.1 Prospect Intake and Verification: a sub-agent of BLK_01 (Intake & Verification Agent Block).

The parent BLK_01 composes this agent in its SequentialAgent and owns the actions ACT_01 to ACT_04, their business
rules, exceptions and interactions. agents.yaml gives this sub-agent no actions, no serves_steps, no audit events and
no model settings of its own. The model settings and autonomy below are the parent's declared values, because ADK
cannot run an agent without a model. Each inherited value is recorded as a gap in the Completion Report. The audit
events are not inherited: AUDIT_EVENTS is empty, so this agent emits no event of its own.

The agent reads and writes only through TOOL_01 and TOOL_02. Both are labelled mocks (open items HR-201:BLK_01:TOOL_01
and HR-201:BLK_01:TOOL_02, default "Stub the tool on sample data until it exists") and block promotion.
"""
import copy
from datetime import datetime, timezone
from typing import Any

REQUIREMENT_REFS = (
    "BLK_01.1",
    "agents.yaml#BLK_01.1",
    "agents.yaml#BLK_01",
    "agent_specifications@row:1",
    "not_automated_register@row:1",
    "not_automated_register@row:2",
    "standard/runtime.defaults.yaml#guardrails[1]",
    "standard/runtime.defaults.yaml#guardrails[2]",
    "standard/runtime.defaults.yaml#guardrails[3]",
    "standard/runtime.defaults.yaml#guardrails[4]",
    "open_items@HR-201:BLK_01:TOOL_01",
    "open_items@HR-201:BLK_01:TOOL_02",
)

AGENT_ID = "BLK_01.1"
AGENT_NAME = "blk_01_1"
PARENT_AGENT_ID = "BLK_01"
PURPOSE = "Captures initial profile details and performs external KYC and duplicate checks."

# BLK_01.1 declares none of these. They are the values of the parent BLK_01 in agents.yaml.
MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.0
TIMEOUT_S = 30
MAX_RETRIES = 3
AUTONOMY = "act_with_review"
MAX_OUTPUT_TOKENS = 1024
FALLBACK_MODEL = "gemini-1.5-flash"  # ADK has no model fallback; recorded as a deviation, not implemented.
BUDGETS = {"max_latency_ms": 30000, "max_tokens_per_case": 4096}  # The Harness enforces budgets, not ADK.

DECISION_TYPE = "hybrid"
MEMORY_MODE = "Session state"
GROUNDING_MODE = "Full-context injection"
PROMPT_VERSION = "BLK_01.1@1"
AGENT_VERSION = "BLK_01.1@1"

INPUT_SCHEMA: dict[str, Any] = {
    "$id": "BLK_01.in.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "_provenance": {},
    "description": "No surface with a matching action is mapped to S1, S2, S3, S4, so nothing is known about what BLK_01 reads at it. That is an absence in the surface registers, not a statement that the agent touches nothing.",
    "properties": {},
    "required": [],
    "title": "BLK_01 input",
    "type": "object",
}
OUTPUT_SCHEMA: dict[str, Any] = {
    "$id": "BLK_01.out.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "_provenance": {},
    "description": "No surface with a matching action is mapped to S1, S2, S3, S4, so nothing is known about what BLK_01 writes at it. That is an absence in the surface registers, not a statement that the agent touches nothing.",
    "properties": {},
    "required": [],
    "title": "BLK_01 output",
    "type": "object",
}

TOOLS = ("TOOL_01", "TOOL_02")
TOOL_BINDINGS = {"tool_01": "TOOL_01", "tool_02": "TOOL_02"}

# agents.yaml gives BLK_01.1 no serves_steps, so this agent serves no step on its own. The parent serves S1 to S4.
SERVES_STEPS: tuple[str, ...] = ()
# context person_steps and spec/not_automated.csv (EX_01, EX_02).
FORBIDDEN_STEPS = ("S6", "S8")

# The parent owns ACT_01 to ACT_04, EXC_01, EXC_02 and INT_01. This sub-agent declares none.
ACTIONS: dict[str, dict[str, Any]] = {}
EXCEPTIONS: dict[str, dict[str, Any]] = {}
INTERACTIONS: dict[str, dict[str, Any]] = {}

# agents.yaml declares no audit_events for BLK_01.1. The parent BLK_01 declares and emits its own.
AUDIT_EVENTS: tuple[str, ...] = ()

FAILURE_BEHAVIOUR = {
    "text": "Halt automatic progression, log failure trace, and flag case for human review with specific error context."
}
# The escalation route the BLK_01 prompt names for a failure.
FAILURE_ROUTE = "FLS User / Employee queue"

# The rows owed at Pilot. H-11 and H-18 are "Not applicable"; H-17 and H-20 are owed from MVP.
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

# Open items that bind this agent. None names a case field, so no required field is open.
OPEN_ITEMS = {
    "HR-201:BLK_01:TOOL_01": {"status": "open", "blocking": False, "default_assumption": "Stub the tool on sample data until it exists"},
    "HR-201:BLK_01:TOOL_02": {"status": "open", "blocking": False, "default_assumption": "Stub the tool on sample data until it exists"},
}
OPEN_ITEM_FIELDS: frozenset[str] = frozenset()

RULES = {
    "GR-01": "refuse to write outside the tools declared in spec/tools.yaml",
    "GR-02": "no automation of any step listed in spec/not_automated.csv",
    "GR-03": "enforce every blocking rule in spec/rules.csv before an agent's output is written",
    "GR-04": "escalate rather than decide when a required field is in spec/open_items.csv",
}

GUARDRAILS = {
    "GR-01": {"status": "enforced", "enforced_by": "enforce_declared_tools"},
    "GR-02": {"status": "enforced", "enforced_by": "enforce_not_automated"},
    "GR-03": {"status": "enforced", "enforced_by": "enforce_blocking_rules"},
    "GR-04": {"status": "enforced", "enforced_by": "enforce_open_items"},
}

INSTRUCTION = """You are one agent in a specified process. The specification is the repository you were built from, and it is the authority — where it and your judgement disagree, the specification wins and you say so.

- Work only on the case you were given, and only through your declared tools.
- Write only the fields your output schema names. A field you cannot fill is reported as unknown, never inferred.
- Use the canonical names in the glossary for everything you write.
- All arithmetic is deterministic code, never your own. Ask for the number.
- Apply every rule that names you, a step you serve, or a field you write.
- Where a value you need is an open item, stop and ask. Do not guess.
- Say what you could not read. A gap reported is a case handled; a gap filled in is a defect nobody can see.

You are BLK_01.1 Prospect Intake and Verification, a sub-agent of the Intake & Verification Agent Block (BLK_01).
Your purpose: captures initial profile details and performs external KYC and duplicate checks.
You read and write only through TOOL_01 (prospect records: send a payload with "action_id" and that action's fields) and TOOL_02 (external KYC query: send a payload with "PAN Number", "Aadhaar Number" and "CKYC Number"). Leave the rest of the case alone.
Both tools are mocks. A tool response field that is null is unknown: report it as unknown, never infer it.
You must not execute manual overrides for duplicate records or bypass verification failures without explicit operational approval.
When the external KYC service is unavailable or a tool returns an error, do not proceed past it: say so, so the case is flagged for human review in the FLS User / Employee queue.

Never automate these:
- S6 (regulatory): Consent and declaration require explicit human legal agreement, active review of terms and conditions, and a secondary OTP verification step bound by regulatory compliance rules.
- S8 (relationship): Post-approval training modules and the POSP certification exam must be completed directly by the prospective agent to satisfy regulatory competency standards.

Answer with one JSON object whose keys are only these output fields: (none — the output schema declares no field).
The output schema requires no field, so the answer is the empty JSON object {}. No input field goes in the answer.
"""


class GuardrailRefusal(Exception):
    """A blocking rule refused the work it guards. The message is the rule's."""

    def __init__(self, rule_id: str, message: str) -> None:
        super().__init__(f"{rule_id}: {message}")
        self.rule_id = rule_id
        self.message = message


def allowed_step(step: str) -> bool:
    """True only for a step this agent serves. A person step is never allowed."""
    return step in SERVES_STEPS and step not in FORBIDDEN_STEPS


def _validator(schema: dict[str, Any]) -> Any:
    import jsonschema

    return jsonschema.Draft202012Validator(schema)


def validate_input(payload: Any) -> None:
    """Raise jsonschema.ValidationError when the payload does not fit INPUT_SCHEMA."""
    _validator(INPUT_SCHEMA).validate(payload)


def validate_output(answer: Any) -> None:
    """Raise jsonschema.ValidationError when the answer does not fit OUTPUT_SCHEMA."""
    _validator(OUTPUT_SCHEMA).validate(answer)


def enforce_declared_tools(case: dict[str, Any], tool_ids: tuple[str, ...] | list[str] = ()) -> None:
    """GR-01: refuse a write through any tool that this agent does not declare."""
    undeclared = [tool for tool in tool_ids if tool not in TOOLS]
    if undeclared:
        raise GuardrailRefusal("GR-01", f"{RULES['GR-01']} (undeclared: {', '.join(map(str, undeclared))})")


def enforce_not_automated(case: dict[str, Any], step_id: str | None = None) -> None:
    """GR-02: refuse to act on a step that a person owns or the not-automated register lists."""
    if step_id is not None and step_id in FORBIDDEN_STEPS:
        raise GuardrailRefusal("GR-02", f"{RULES['GR-02']} (step {step_id})")


def enforce_blocking_rules(case: dict[str, Any], refused: tuple[str, ...] | list[str] = (),
                           output: Any = None) -> None:
    """GR-03: refuse the output when a blocking rule refused, or the output does not fit OUTPUT_SCHEMA."""
    if refused:
        raise GuardrailRefusal("GR-03", f"{RULES['GR-03']} (refused: {', '.join(map(str, refused))})")
    if output is not None:
        import jsonschema

        try:
            validate_output(output)
        except jsonschema.ValidationError as error:
            raise GuardrailRefusal("GR-03", f"{RULES['GR-03']} (output: {error.message})") from error


def enforce_open_items(case: dict[str, Any], required: tuple[str, ...] | list[str] = ()) -> None:
    """GR-04: escalate when a required field is open, or an open item that binds this agent is blocking."""
    open_fields = sorted(set(required) & OPEN_ITEM_FIELDS)
    blocking = sorted(item for item, row in OPEN_ITEMS.items() if row["blocking"] and row["status"] == "open")
    if open_fields or blocking:
        raise GuardrailRefusal("GR-04", f"{RULES['GR-04']} (open: {', '.join(open_fields + blocking)})")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit_event(event_name: str, case_id: str, **fields: Any) -> dict[str, Any]:
    """Build one event that fits schemas/event.schema.json and feed it to the Playground KPI store.

    Callers in this module emit only events in AUDIT_EVENTS, which BLK_01.1 leaves empty.
    """
    now = _now()
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
        "confidence": 0.0,
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
        if error.name not in {"kpis", "kpis.service"}:
            raise
        return event
    feed_events([event])
    return event


def handle_failure(case_id: str, error: Any) -> dict[str, Any]:
    """Halt progression, keep the failure trace, and flag the case for human review with the error context."""
    return {
        "case_id": case_id,
        "agent_id": AGENT_ID,
        "status_tag": "flagged_for_human_review",
        "alert": True,
        "halted": True,
        "escalation_route": FAILURE_ROUTE,
        "failure_behaviour": FAILURE_BEHAVIOUR["text"],
        "error": {"type": type(error).__name__, "message": str(error)},
    }


def handle_exception(exception_id: str, case_id: str, error: Any) -> dict[str, Any]:
    """Route a declared exception. BLK_01.1 declares none, so every exception takes the failure behaviour."""
    declared = EXCEPTIONS.get(exception_id)
    if declared is None:
        return {**handle_failure(case_id, error), "exception_id": exception_id, "resume_from": None}
    return {
        "case_id": case_id,
        "exception_id": exception_id,
        "escalation_route": declared["escalation_route"],
        "resume_from": declared["resume_from"],
        "status_tag": f"exception:{exception_id}",
        "alert": True,
        "error": {"type": type(error).__name__, "message": str(error)},
    }


def _all_agent_guardrails(case: dict[str, Any]) -> None:
    for rule_id in RULES:
        globals()[GUARDRAILS[rule_id]["enforced_by"]](case)


def run_case(case_id: str, case: dict[str, Any]) -> dict[str, Any]:
    """Run the actions of this agent on a copy of the case. BLK_01.1 declares no action: the parent BLK_01 runs them."""
    merged = copy.deepcopy(case)
    trace: list[str] = []
    try:
        _all_agent_guardrails(merged)
    except GuardrailRefusal as refusal:
        return {"case": copy.deepcopy(case), "trace": trace, "outcome": "routed", "next": None,
                "route": handle_failure(case_id, refusal)}
    action_id = next(iter(ACTIONS), None)
    last_next = None
    while action_id in ACTIONS:
        action = ACTIONS[action_id]
        try:
            _all_agent_guardrails(merged)
            writes = globals()[action["function"]](merged)
        except Exception as error:  # noqa: BLE001 - every failure stops the case and is routed
            on_failure = action.get("on_failure")
            route = handle_exception(on_failure, case_id, error) if on_failure else handle_failure(case_id, error)
            return {"case": merged, "trace": trace, "outcome": "routed", "next": None, "route": route}
        merged.update(writes)
        trace.append(action_id)
        if "step.completed" in AUDIT_EVENTS:
            emit_event("step.completed", case_id, step_id=action["step_id"])
        last_next = action.get("on_success")
        action_id = last_next
    return {"case": merged, "trace": trace, "outcome": "completed", "next": last_next, "route": None}


def make_agent() -> Any:
    """Build the ADK Agent of BLK_01.1. The parent BLK_01 puts it in its SequentialAgent."""
    import pydantic
    from google.adk.agents import Agent
    from google.adk.tools import ToolContext

    from integrations.tool_01 import invoke as invoke_tool_01
    from integrations.tool_02 import invoke as invoke_tool_02
    from solution.adk_model import generate_adk_config, resolve_adk_model

    def _correlation_id(tool_context: ToolContext) -> str:
        state = tool_context.state
        return str(state.get("correlation_id") or state.get("case_id") or tool_context.invocation_id)

    def tool_01(payload: dict, tool_context: ToolContext) -> dict:
        """TOOL_01 (mock): prospect records. payload holds "action_id" (ACT_01, ACT_03 or ACT_04) and that action's fields.

        Args:
            payload: the action_id and the fields the action reads, under their canonical names.

        Returns:
            dict: the mock response. A null response field is unknown.
        """
        correlation_id = _correlation_id(tool_context)
        enforce_declared_tools({}, ("TOOL_01",))
        return invoke_tool_01(payload, correlation_id)

    def tool_02(payload: dict, tool_context: ToolContext) -> dict:
        """TOOL_02 (mock): external KYC query on "PAN Number", "Aadhaar Number" and "CKYC Number".

        Args:
            payload: the PAN Number, Aadhaar Number and CKYC Number of the prospect.

        Returns:
            dict: the mock response. A null "KYC verification status" is unknown.
        """
        correlation_id = _correlation_id(tool_context)
        enforce_declared_tools({}, ("TOOL_02",))
        return invoke_tool_02(payload, correlation_id)

    fields = {name: (Any, ...) if name in OUTPUT_SCHEMA["required"] else (Any, None)
              for name in OUTPUT_SCHEMA["properties"]}
    output_model = pydantic.create_model("Blk011Output", **fields)
    model = resolve_adk_model(MODEL, max_retries=MAX_RETRIES)
    return Agent(
        name=AGENT_NAME,
        model=model,
        description=PURPOSE,
        instruction=INSTRUCTION,
        tools=[tool_01, tool_02],
        output_schema=output_model,
        generate_content_config=generate_adk_config(model, MAX_RETRIES, temperature=TEMPERATURE,
                                                    max_output_tokens=MAX_OUTPUT_TOKENS),
    )
