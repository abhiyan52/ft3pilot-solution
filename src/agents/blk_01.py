"""BLK_01 Intake & Verification Agent Block (parent of BLK_01.1 and BLK_01.2, sequential).

Serves S1, S2, S3, S4. Hybrid decision: the rule checks run in code, the model work sits in the sub-agents.
The parent registers no tool callable of its own; TOOL_BINDINGS is the union of its sub-agents' bindings.
S6 and S8 are person steps and are never automated here.
"""
from __future__ import annotations

import contextvars
import copy
import importlib
import logging
import re
from datetime import datetime, timezone

REQUIREMENT_REFS = (
    "BLK_01",
    "agent_specifications@row:1",
    "agent_block_actions@row:1",
    "agent_block_actions@row:2",
    "agent_block_actions@row:3",
    "agent_block_actions@row:4",
    "agent_exception_routes@row:1",
    "agent_exception_routes@row:2",
    "agent_interaction_contracts@row:1",
    "tacit_knowledge@row:3",
    "not_automated_register@row:1",
    "not_automated_register@row:2",
)

AGENT_ID = "BLK_01"
MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.0
TIMEOUT_S = 30
MAX_RETRIES = 3
MAX_OUTPUT_TOKENS = 1024
AUTONOMY = "act_with_review"
DECISION_TYPE = "hybrid"
MEMORY_MODE = "Session state"
GROUNDING_MODE = "Full-context injection"
PROMPT_VERSION = "prompts/BLK_01.md"
AGENT_VERSION = "1"

SERVES_STEPS = ("S1", "S2", "S3", "S4")
PERSON_STEPS = ("S6", "S8")
FORBIDDEN_STEPS = ("S6", "S8")
TOOLS = ("TOOL_01", "TOOL_02")
SUB_AGENT_MODULES = ("agents.blk_01_1", "agents.blk_01_2")
SUB_AGENT_NAMES = ("blk_01_1", "blk_01_2")
COMPOSITION = "sequential"

_INTEGRATION_MODULES = {
    "TOOL_01": "integrations.tool_01",
    "TOOL_02": "integrations.tool_02",
}

AUDIT_EVENTS = ("agent.decision", "tool.call", "step.completed")

COMPLETION_CONDITIONS = [
    "Prospect record created",
    "KYC verified successfully",
    "Bank details verified",
]
RESUME_STRATEGY = "Resume from last successful database write upon manual error resolution."

FAILURE_BEHAVIOUR = {
    "text": "Halt automatic progression, log failure trace, and flag case for human review with specific error context."
}

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

INSTRUCTION = (
    "You are the Intake & Verification Agent Block serving steps S1, S2, S3, and S4. "
    "You orchestrate prospect creation, duplicate detection, resilient external KYC querying, and IFSC-backed bank verification.\n"
    "You read prospect registration submissions and write to workflow API and records store through TOOL_01 and TOOL_02. "
    "Leave the rest of the case alone.\n"
    "First, capture initial profile details including full name, mobile number, email, and optional Relationship Manager "
    "Business Code. Perform duplicate checks on email and mobile.\n"
    "Second, execute identity verification by querying the external KYC service using PAN and Aadhaar numbers via TOOL_02.\n"
    "Third, combine user input with pre-filled KYC data to update the agent profile, capturing address and demographic details.\n"
    "Fourth, capture bank account type, account holder name, account number, and IFSC code. "
    "Use the IFSC code to auto-populate bank name, city, and branch name.\n"
    "You must not execute manual overrides for duplicate records or bypass verification failures without explicit operational approval.\n"
    "When external verification services are unavailable or errors occur, halt automatic progression, log failure trace, "
    "and flag the case for human review via the escalation route to the FLS User / Employee queue."
)

HARNESS = {
    "H-01": "Coordinator + sub-agents",
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

# Each action: its step, tools and rules, and the function in this module that runs it.
ACTIONS = {
    "ACT_01": {"step_id": "S1", "tool_ids": ["TOOL_01"], "rule_ids": ["BR-ACT_01"], "function": "act_01_extract_validate_intake"},
    "ACT_02": {"step_id": "S2", "tool_ids": ["TOOL_02"], "rule_ids": ["BR-ACT_02"], "function": "act_02_orchestrate_kyc_verification"},
    "ACT_03": {"step_id": "S3", "tool_ids": ["TOOL_01"], "rule_ids": ["BR-ACT_03"], "function": "act_03_populate_profile_address"},
    "ACT_04": {"step_id": "S4", "tool_ids": ["TOOL_01"], "rule_ids": ["BR-ACT_04"], "function": "act_04_resolve_ifsc_verify_bank"},
}

_READS = {
    "ACT_01": ("Full Name", "Mobile Number", "Email", "RM Business Code"),
    "ACT_02": ("PAN Number", "Aadhaar Number", "CKYC Number"),
    "ACT_03": ("Name", "Gender", "Date of Birth", "Address", "Pincode"),
    "ACT_04": ("IFSC Code", "Bank Account Number", "Name As In Bank Account"),
}
_WRITES = {
    "ACT_01": ("Application record draft",),
    "ACT_02": ("KYC verification status",),
    "ACT_03": ("Agent profile update",),
    "ACT_04": ("Bank Name", "Bank City", "Branch Name", "Bank verification status"),
}
_ON_SUCCESS = {"ACT_01": "ACT_02", "ACT_02": "ACT_03", "ACT_03": "ACT_04", "ACT_04": "ACT_05"}
_ON_FAILURE = {"ACT_01": "EXC_01", "ACT_02": "EXC_02", "ACT_03": "EXC_01", "ACT_04": "EXC_01"}

EXCEPTIONS = {
    "EXC_01": {
        "action_id": "ACT_01",
        "escalation_route": "FLS User / Employee manual resolution queue",
        "resume_from": "ACT_01",
    },
    "EXC_02": {
        "action_id": "ACT_02",
        "escalation_route": "Async retry queue / Operations exception handler",
        "resume_from": "ACT_02",
    },
}

INTERACTIONS = {
    "INT_01": {
        "channel": "In-app Notification / Toast",
        "consent_required": "false",
        "fallback_channel": "UI inline error",
    },
}

GUARDRAILS = {
    "GR-01": {"status": "enforced", "enforced_by": "enforce_gr_01"},
    "GR-02": {"status": "enforced", "enforced_by": "enforce_gr_02"},
    "GR-03": {"status": "enforced", "enforced_by": "enforce_gr_03"},
    "GR-04": {"status": "enforced", "enforced_by": "enforce_gr_04"},
    "BR-ACT_01": {"status": "enforced", "enforced_by": "enforce_br_act_01"},
    "BR-ACT_02": {"status": "enforced", "enforced_by": "enforce_br_act_02"},
    "BR-ACT_03": {"status": "enforced", "enforced_by": "enforce_br_act_03"},
    "BR-ACT_04": {"status": "enforced", "enforced_by": "enforce_br_act_04"},
}
_ALL_AGENT_RULES = ("GR-01", "GR-02", "GR-03", "GR-04")

_RULE_MESSAGES = {
    "GR-01": "refuse to write outside the tools declared in spec/tools.yaml",
    "GR-02": "no automation of any step listed in spec/not_automated.csv",
    "GR-03": "enforce every blocking rule in spec/rules.csv before an agent's output is written",
    "GR-04": "escalate rather than decide when a required field is in spec/open_items.csv",
    "BR-ACT_01": "ACT_01 refuses to proceed: Mobile number unique; Email valid format",
    "BR-ACT_02": "ACT_02 refuses to proceed: KYC service response received or queued",
    "BR-ACT_03": "ACT_03 refuses to proceed: Pincode and state match",
    "BR-ACT_04": "ACT_04 refuses to proceed: IFSC format valid; Bank account verification passed",
}

# No open item of this agent names a required case field; the open items cover tool stubs only.
OPEN_REQUIRED_FIELDS: frozenset = frozenset()

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
_PINCODE = re.compile(r"^[1-9][0-9]{5}$")

_log = logging.getLogger(__name__)
_CORRELATION: contextvars.ContextVar = contextvars.ContextVar("blk_01_correlation_id", default="")


class GuardrailRefusal(Exception):
    """A blocking rule refused the write it guards."""

    def __init__(self, rule_id, message=None):
        self.rule_id = rule_id
        self.message = message or _RULE_MESSAGES.get(rule_id, rule_id)
        super().__init__(self.message)


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def _refuse(rule_id):
    raise GuardrailRefusal(rule_id, _RULE_MESSAGES[rule_id])


def allowed_step(step):
    """True only for a step this agent serves and no person owns."""
    return step in SERVES_STEPS and step not in PERSON_STEPS and step not in FORBIDDEN_STEPS


# ---- guardrail enforcers ---------------------------------------------------

def enforce_gr_01(case, action_id=None, tool_id=None):
    """Refuse a write through a tool this agent does not declare."""
    tools = [tool_id] if tool_id else list((ACTIONS.get(action_id) or {}).get("tool_ids") or [])
    if any(t not in TOOLS for t in tools):
        _refuse("GR-01")


def enforce_gr_02(case, action_id=None, step_id=None):
    """Refuse any step that a person owns or the business kept manual."""
    step = step_id or (ACTIONS.get(action_id) or {}).get("step_id")
    if step is not None and (not allowed_step(step) or step in FORBIDDEN_STEPS or step in PERSON_STEPS):
        _refuse("GR-02")


def enforce_gr_03(case, action_id=None):
    """Refuse an action whose blocking rules have no enforcer function in this module."""
    for rule_id in (ACTIONS.get(action_id) or {}).get("rule_ids") or []:
        entry = GUARDRAILS.get(rule_id) or {}
        if entry.get("status") != "enforced" or not callable(globals().get(entry.get("enforced_by"))):
            _refuse("GR-03")


def enforce_gr_04(case, action_id=None):
    """Escalate rather than decide when a required field is an open item and has no value."""
    case = case or {}
    for field in _READS.get(action_id, ()):
        if field in OPEN_REQUIRED_FIELDS and _blank(case.get(field)):
            _refuse("GR-04")


def enforce_br_act_01(case):
    """Email valid format; mobile number present. Uniqueness is unproven: the Precord names no duplicate-lookup source."""
    case = case or {}
    email, mobile = case.get("Email"), case.get("Mobile Number")
    if _blank(email) or not _EMAIL.match(str(email).strip()):
        _refuse("BR-ACT_01")
    if _blank(mobile):
        _refuse("BR-ACT_01")


def enforce_br_act_02(case):
    """The KYC service response must be received (or queued): a status has to be present."""
    if _blank((case or {}).get("KYC verification status")):
        _refuse("BR-ACT_02")


def enforce_br_act_03(case):
    """Pincode well formed. The pincode-state match is unproven: ACT_03 does not read State and the Precord has no table."""
    pincode = (case or {}).get("Pincode")
    if _blank(pincode) or not _PINCODE.match(str(pincode).strip()):
        _refuse("BR-ACT_03")


def enforce_br_act_04(case):
    """IFSC format valid; a returned bank verification status must be present. The Precord declares no status values."""
    case = case or {}
    ifsc = case.get("IFSC Code")
    if _blank(ifsc) or not _IFSC.match(str(ifsc).strip().upper()):
        _refuse("BR-ACT_04")
    if "Bank verification status" in case and _blank(case.get("Bank verification status")):
        _refuse("BR-ACT_04")


# ---- events, tools, notifications -----------------------------------------

def emit_event(event_name, case_id, **fields):
    """Build one event dict (schemas/event.schema.json) and feed it to the KPI store."""
    if event_name not in AUDIT_EVENTS:
        raise ValueError(f"{event_name} is not a declared audit event of {AGENT_ID}")
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
    except ModuleNotFoundError as missing:
        if missing.name not in ("kpis", "kpis.service"):
            raise
        return event
    feed_events([event])
    return event


def _call_tool(tool_id, request, step_id):
    enforce_gr_01({}, tool_id=tool_id)
    invoke = importlib.import_module(_INTEGRATION_MODULES[tool_id]).invoke
    correlation_id = _CORRELATION.get()
    response = invoke(request, correlation_id)
    emit_event("tool.call", correlation_id, step_id=step_id)
    return response or {}


def _mask(value):
    """Mask through the shared helper; a blank value stays blank."""
    from solution.masking import mask_value

    return mask_value("partial", str(value)) if not _blank(value) else ""


def build_notification(case_id, case, interaction_id="INT_01", channel_failed=False):
    """INT_01: a notification with the mobile number and PAN masked. consent_required false, so nothing waits on consent."""
    spec = INTERACTIONS[interaction_id]
    if str(spec["consent_required"]).lower() == "true" and not (case or {}).get("consent"):
        return None
    channel = spec["fallback_channel"] if channel_failed else spec["channel"]
    case = case or {}
    return {
        "interaction_id": interaction_id,
        "channel": channel,
        "case_id": case_id,
        "message": "Duplicate or invalid entry found during intake. Mobile: %s, PAN: %s. Please correct it."
        % (_mask(case.get("Mobile Number")) or "n/a", _mask(case.get("PAN Number")) or "n/a"),
    }


# ---- actions ---------------------------------------------------------------

def _view(case, action_id):
    return {field: case.get(field) for field in _READS[action_id]}


def act_01_extract_validate_intake(case):
    request = _view(case, "ACT_01")
    enforce_br_act_01(request)
    response = _call_tool("TOOL_01", request, "S1")
    return {"Application record draft": response.get("Application record draft")}


def act_02_orchestrate_kyc_verification(case):
    request = _view(case, "ACT_02")
    response = _call_tool("TOOL_02", request, "S2")
    enforce_br_act_02({"KYC verification status": response.get("KYC verification status")})
    return {"KYC verification status": response.get("KYC verification status")}


def act_03_populate_profile_address(case):
    request = _view(case, "ACT_03")
    enforce_br_act_03(request)
    response = _call_tool("TOOL_01", request, "S3")
    return {"Agent profile update": response.get("Agent profile update")}


def act_04_resolve_ifsc_verify_bank(case):
    request = _view(case, "ACT_04")
    enforce_br_act_04(request)
    response = _call_tool("TOOL_01", request, "S4")
    enforce_br_act_04({"IFSC Code": request["IFSC Code"], "Bank verification status": response.get("Bank verification status")})
    return {field: response.get(field) for field in _WRITES["ACT_04"]}


# ---- failure and exception routing ----------------------------------------

def _contain_exc_01(case_id, error):
    # Duplicate or data conflict: halt record creation, hand to the manual resolution queue.
    return {"status_tag": "duplicate_or_data_conflict_halted"}


def _contain_exc_02(case_id, error):
    # KYC service unavailable: the verification check is never bypassed; the case waits on retry.
    return {"status_tag": "kyc_service_unavailable_queued"}


_CONTAINMENT = {"EXC_01": _contain_exc_01, "EXC_02": _contain_exc_02}


def handle_exception(exception_id, case_id, error):
    spec = EXCEPTIONS[exception_id]
    result = _CONTAINMENT[exception_id](case_id, error)
    _log.warning("%s on case %s: %s", exception_id, case_id, error)
    return {
        "exception_id": exception_id,
        "case_id": case_id,
        "escalation_route": spec["escalation_route"],
        "resume_from": spec["resume_from"],
        "status_tag": result["status_tag"],
        "alert": True,
        "error": str(error),
    }


def handle_failure(case_id, error):
    _log.error("BLK_01 failed on case %s: %r", case_id, error)
    return {
        "case_id": case_id,
        "status_tag": "halted_for_human_review",
        "alert": True,
        "escalation_route": EXCEPTIONS["EXC_01"]["escalation_route"],
        "error": f"{type(error).__name__}: {error}",
    }


# ---- run -------------------------------------------------------------------

def _validate(schema, instance):
    import jsonschema

    jsonschema.validate(instance, schema)


def run_case(case_id, case):
    working = copy.deepcopy(case)
    trace = []
    current = None
    last = None
    token = _CORRELATION.set(case_id)
    try:
        _validate(INPUT_SCHEMA, working)
        for action_id, spec in ACTIONS.items():
            current = action_id
            for rule_id in _ALL_AGENT_RULES:
                globals()[GUARDRAILS[rule_id]["enforced_by"]](working, action_id)
            writes = globals()[spec["function"]](working)
            _validate(OUTPUT_SCHEMA, writes)
            working = {**working, **writes}
            trace.append(action_id)
            last = action_id
            emit_event("step.completed", case_id, step_id=spec["step_id"])
        return {"case": working, "trace": trace, "outcome": "completed", "next": _ON_SUCCESS.get(last), "route": None}
    except Exception as error:
        exception_id = _ON_FAILURE.get(current)
        route = handle_exception(exception_id, case_id, error) if exception_id else handle_failure(case_id, error)
        emit_event("agent.decision", case_id, step_id=(ACTIONS.get(current) or {}).get("step_id", ""), status=route["status_tag"])
        return {"case": working, "trace": trace, "outcome": "routed", "next": _ON_SUCCESS.get(last), "route": route}
    finally:
        _CORRELATION.reset(token)


# ---- tool bindings and agent -----------------------------------------------

def _sub_agent_modules():
    return [importlib.import_module(name) for name in SUB_AGENT_MODULES]


# Union of the leaf sub-agents' bindings; the parent registers no callable. A missing sub-agent module fails the import.
TOOL_BINDINGS = {
    **importlib.import_module("agents.blk_01_1").TOOL_BINDINGS,
    **importlib.import_module("agents.blk_01_2").TOOL_BINDINGS,
}


def make_agent():
    from google.adk.agents import SequentialAgent

    sub_agents = []
    for name, module in zip(SUB_AGENT_NAMES, _sub_agent_modules()):
        sub_agent = module.make_agent()
        # The composition declares these names; the sub-agent module may carry its display name.
        sub_agent.name = name
        sub_agents.append(sub_agent)
    return SequentialAgent(name=AGENT_ID, sub_agents=sub_agents)
