"""BLK_01 · Intake & Verification Agent Block (agents.yaml BLK_01, prompts/BLK_01.md).

A sequential ADK composition of BLK_01.1 (Prospect Intake and Verification) and BLK_01.2 (Bank Details Validation).
The parent registers no tool and runs no model of its own. run_case is the deterministic part of this hybrid agent:
it runs ACT_01 to ACT_04 (steps S1 to S4) in code, enforces every rule that binds BLK_01 before a write, and routes a
refusal or a failure to its declared exception. CHK_01 follows ACT_04; the orchestrator Unit owns that hand-off.
TOOL_01 and TOOL_02 are labelled mocks (open items HR-201:BLK_01:TOOL_01 and HR-201:BLK_01:TOOL_02).
"""
from __future__ import annotations

import hashlib
import importlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable

REQUIREMENT_REFS: tuple[str, ...] = (
    "agents.yaml#BLK_01",
    "prompts/BLK_01.md",
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
    "standard/runtime.defaults.yaml#guardrails[1]",
    "standard/runtime.defaults.yaml#guardrails[2]",
    "standard/runtime.defaults.yaml#guardrails[3]",
    "standard/runtime.defaults.yaml#guardrails[4]",
)

AGENT_ID = "BLK_01"
NAME = "blk_01"
DISPLAY_NAME = "Intake & Verification Agent Block"
PURPOSE = ("Orchestrates prospect registration, identity verification, and bank account validation through "
           "workflow APIs.")
TRIGGER = "Incoming prospect registration submission"

MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.0
TIMEOUT_S = 30
MAX_RETRIES = 3
MAX_OUTPUT_TOKENS = 1024
AUTONOMY = "act_with_review"
DECISION_TYPE = "hybrid"
COMPOSITION = "sequential"
# ADK has no model fallback and no per-case token or latency budget. Both are declared and kept visible here only;
# the harness records them as deviations.
FALLBACK_MODEL = "gemini-1.5-flash"
BUDGETS = {"max_latency_ms": 30000, "max_tokens_per_case": 4096}

MEMORY_MODE = "Session state"
GROUNDING_MODE = "Full-context injection"

SERVES_STEPS: tuple[str, ...] = ("S1", "S2", "S3", "S4")
# context person_steps and not_automated_register: a person does these.
FORBIDDEN_STEPS: tuple[str, ...] = ("S6", "S8")

TOOLS: tuple[str, ...] = ("TOOL_01", "TOOL_02")
INTEGRATION_MODULES = {"TOOL_01": "integrations.tool_01", "TOOL_02": "integrations.tool_02"}
CHECKPOINTS: tuple[str, ...] = ("CHK_01",)

# agent_composition: mode sequential, in the declared order.
SUB_AGENTS: tuple[dict[str, str], ...] = (
    {"agent_id": "BLK_01.1", "module": "agents.blk_01_1", "name": "blk_01_1"},
    {"agent_id": "BLK_01.2", "module": "agents.blk_01_2", "name": "blk_01_2"},
)

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

EVENT_SCHEMA_REQUIRED: tuple[str, ...] = (
    "case_id", "step_id", "agent_id", "event_type", "actor_type", "actor_id", "ts_start", "ts_end", "model",
    "prompt_version", "agent_version", "tokens_in", "tokens_out", "cost", "status", "confidence", "override_flag",
    "override_reason", "guardrail_event",
)

# prompts/BLK_01.md, §1 to §4, embedded so the module reads no file at run time.
PROMPT = """# BLK_01 · Intake & Verification Agent Block

## 1 · Platform frame — shared

You are one agent in a specified process. The specification is the repository you were built from, and it is the authority — where it and your judgement disagree, the specification wins and you say so.

- Work only on the case you were given, and only through your declared tools.
- Write only the fields your output schema names. A field you cannot fill is reported as unknown, never inferred.
- Use the canonical names in `context/glossary.csv` for everything you write.
- All arithmetic is deterministic code, never your own. Ask for the number.
- Apply every rule in `spec/rules.csv` that names you, a step you serve, or a field you write.
- Where a value you need is in `spec/open_items.csv`, stop and ask. Do not guess.
- Say what you could not read. A gap reported is a case handled; a gap filled in is a defect nobody can see.

## 2 · Agent instruction — written for this agent

You are the Intake & Verification Agent Block serving steps S1, S2, S3, and S4. You orchestrate prospect creation, duplicate detection, resilient external KYC querying, and IFSC-backed bank verification.
You read prospect registration submissions and write to workflow API and records store through TOOL_01 and TOOL_02. Leave the rest of the case alone.
First, capture initial profile details including full name, mobile number, email, and optional Relationship Manager Business Code. Perform duplicate checks on email and mobile.
Second, execute identity verification by querying the external KYC service using PAN and Aadhaar numbers via TOOL_02.
Third, combine user input with pre-filled KYC data to update the agent profile, capturing address and demographic details.
Fourth, capture bank account type, account holder name, account number, and IFSC code. Use the IFSC code to auto-populate bank name, city, and branch name.
You must not execute manual overrides for duplicate records or bypass verification failures without explicit operational approval.
When external verification services are unavailable or errors occur, halt automatic progression, log failure trace, and flag the case for human review via the escalation route to the FLS User / Employee queue.

### Judgement at these steps

- When external verification services are unavailable, operators proceed with the flow despite the error banner. Looks at: Service Temporarily Unavailable banner present, operator does not pause or retry, proceeds immediately. (FLS User / Employee)

### Never automate these

- S6 (regulatory): Consent and declaration require explicit human legal agreement, active review of terms and conditions, and a secondary OTP verification step bound by regulatory compliance rules.
- S8 (relationship): Post-approval training modules and the POSP certification exam must be completed directly by the prospective agent to satisfy regulatory competency standards.

## 3 · Domain pack — shared vocabulary

`context/ontology_nodes.csv` is the naming authority for every name you write. Where this process's word and yours differ, use this process's.

| Term | Also called | Means |
| --- | --- | --- |
| Aadhaar Card | Aadhaar address, Aadhaar back, Aadhaar front, Aadhaar linkage, Aadhaar Number, Aadhar card, Card Back, PAN Aadhaar | The unique resident identification document collected for identity verification during onboarding. |
| PAN Card | PAN Number | The tax identification document submitted for financial and identity validations. |
| Bank Account | Account Cancelled, Account Create, Account Number, Account Type, Bank City, Bank Details, Bank Documents, Bank Name, Bank Verification, Branch Name, cancelled cheque, Profile Bank, state bank | The financial destination and associated parameters recorded for agent payouts and verification. |
| Address | Address block, Address Details, Address Line, Communication Address, Firm Address, permanent address, pincode city | The residential or business location details provided by the agent. |
| Agent | Agent Approved Successfully, Agent Category, agent code, Agent modal, Agent Onboard, Agent Type, different agent, Field Level Sales, FLS User, Onboard POSP, POSP Create, POSP Exam, POSP Journey, POSP Name, Training POSP | The individual undergoing onboarding to become a certified sales representative or Point of Sales Person. |
| Relationship Manager | Hierarchy Mana, Monitoring Manager, RM Business Code, RM code, RM Name | The internal supervisory role responsible for overseeing and assisting the agent's onboarding journey. |

## 4 · Invocation variables — supplied per case

  case               the case object, `schemas/case.schema.json`
  case_id            the case this invocation is about
  agent_id           `BLK_01`
  checkpoint         `CHK_01`, where a person sees this
  correlation_id     threaded through every tool call, for the trace
"""

OUTPUT_FIELDS: tuple[str, ...] = tuple(OUTPUT_SCHEMA["properties"])
INSTRUCTION = (
    PROMPT
    + "\nAnswer with one JSON object whose keys are only these output fields: "
    + (", ".join(OUTPUT_FIELDS) if OUTPUT_FIELDS else "(none: the output schema names no field)")
    + ".\nRequired fields: "
    + (", ".join(OUTPUT_SCHEMA["required"]) if OUTPUT_SCHEMA["required"] else "(none)")
    + ". Copy the input value of a required field when the step does not change it."
    + " No other input field goes in the answer.\n"
)
PROMPT_VERSION = "sha256:" + hashlib.sha256(INSTRUCTION.encode()).hexdigest()[:12]
# agent_version is owed from MVP; the rung is Pilot. The event schema still requires a string.
AGENT_VERSION = ""

ACTIONS: dict[str, dict[str, Any]] = {
    "ACT_01": {"step_id": "S1", "tool_ids": ["TOOL_01"], "rule_ids": ["BR-ACT_01"], "function": "act_01_extract_and_validate_intake"},
    "ACT_02": {"step_id": "S2", "tool_ids": ["TOOL_02"], "rule_ids": ["BR-ACT_02"], "function": "act_02_orchestrate_kyc_verification"},
    "ACT_03": {"step_id": "S3", "tool_ids": ["TOOL_01"], "rule_ids": ["BR-ACT_03"], "function": "act_03_populate_profile_and_address"},
    "ACT_04": {"step_id": "S4", "tool_ids": ["TOOL_01"], "rule_ids": ["BR-ACT_04"], "function": "act_04_resolve_ifsc_and_verify_bank"},
}
# The rest of each action row (agent_block_actions@row:1 to row:4): its reads, writes and routes.
ACTION_DETAILS: dict[str, dict[str, Any]] = {
    "ACT_01": {"name": "Extract and Validate Intake Contact Data",
               "reads": ["Full Name", "Mobile Number", "Email", "RM Business Code"],
               "writes": ["Application record draft"], "on_success": "ACT_02", "on_failure": "EXC_01"},
    "ACT_02": {"name": "Orchestrate External KYC Verification",
               "reads": ["PAN Number", "Aadhaar Number", "CKYC Number"],
               "writes": ["KYC verification status"], "on_success": "ACT_03", "on_failure": "EXC_02"},
    "ACT_03": {"name": "Populate Profile and Address Details",
               "reads": ["Name", "Gender", "Date of Birth", "Address", "Pincode"],
               "writes": ["Agent profile update"], "on_success": "ACT_04", "on_failure": "EXC_01"},
    "ACT_04": {"name": "Resolve IFSC and Verify Bank Details",
               "reads": ["IFSC Code", "Bank Account Number", "Name As In Bank Account"],
               "writes": ["Bank Name", "Bank City", "Branch Name", "Bank verification status"],
               "on_success": "ACT_05", "on_failure": "EXC_01"},
}
FIRST_ACTION = "ACT_01"

EXCEPTIONS: dict[str, dict[str, str]] = {
    "EXC_01": {"action_id": "ACT_01", "escalation_route": "FLS User / Employee manual resolution queue", "resume_from": "ACT_01",
               "category": "Data Conflict / Duplicate", "trigger": "Mobile number or PAN already registered",
               "detection": "Database lookup match during intake", "containment": "Halt automatic record creation",
               "human_work_item": "Resolve duplicate record or correct mobile/PAN entry",
               "recovery": "Update record with unique valid details after human verification"},
    "EXC_02": {"action_id": "ACT_02", "escalation_route": "Async retry queue / Operations exception handler", "resume_from": "ACT_02",
               "category": "External Service Unavailable",
               "trigger": "External KYC service returns service temporarily unavailable",
               "detection": "HTTP 503 or error banner in API response", "containment": "Prevent bypass of verification check",
               "human_work_item": "Verify KYC service status or manually trigger re-query",
               "recovery": "Automated retry with exponential backoff or manual operator resumption upon service recovery"},
}

INTERACTIONS: dict[str, dict[str, Any]] = {
    "INT_01": {"channel": "In-app Notification / Toast", "consent_required": "false", "fallback_channel": "UI inline error"},
}
# The rest of each interaction row (agent_interaction_contracts@row:1).
INTERACTION_DETAILS: dict[str, dict[str, Any]] = {
    "INT_01": {"recipient": "FLS User / Employee or Prospective agent (Posp)", "response_expected": "false",
               "purpose": "Notify user of duplicate mobile/PAN entry or validation error during intake",
               "trigger": "Duplicate check failure or validation error",
               "sensitive_data_policy": "Mask full mobile number and PAN in notifications"},
}
# INT_01 sensitive_data_policy: these values never leave in full.
MASKED_FIELDS: tuple[str, ...] = ("Mobile Number", "PAN Number")

AUDIT_EVENTS: tuple[str, ...] = ("agent.decision", "tool.call", "step.completed")
COMPLETION_CONDITIONS: list[str] = ["Prospect record created", "KYC verified successfully", "Bank details verified"]
RESUME_STRATEGY = "Resume from last successful database write upon manual error resolution."
FAILURE_BEHAVIOUR = {"text": "Halt automatic progression, log failure trace, and flag case for human review with specific error context."}
FAILURE_ROUTE = "FLS User / Employee queue"

FEW_SHOT: list[dict[str, Any]] = []

# harness.checklist rows owed at Pilot whose status is not "Not applicable".
HARNESS: dict[str, str] = {
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

RULES: dict[str, dict[str, str]] = {
    "BR-ACT_01": {"kind": "business_rule", "enforcement": "blocking", "applies_to": "ACT_01",
                  "rule": "Mobile number unique; Email valid format",
                  "message": "ACT_01 refuses to proceed: Mobile number unique; Email valid format"},
    "BR-ACT_02": {"kind": "business_rule", "enforcement": "blocking", "applies_to": "ACT_02",
                  "rule": "KYC service response received or queued",
                  "message": "ACT_02 refuses to proceed: KYC service response received or queued"},
    "BR-ACT_03": {"kind": "business_rule", "enforcement": "blocking", "applies_to": "ACT_03",
                  "rule": "Pincode and state match",
                  "message": "ACT_03 refuses to proceed: Pincode and state match"},
    "BR-ACT_04": {"kind": "business_rule", "enforcement": "blocking", "applies_to": "ACT_04",
                  "rule": "IFSC format valid; Bank account verification passed",
                  "message": "ACT_04 refuses to proceed: IFSC format valid; Bank account verification passed"},
    "GR-01": {"kind": "guardrail", "enforcement": "blocking", "applies_to": "all agents",
              "rule": "refuse to write outside the tools declared in spec/tools.yaml",
              "message": "GR-01 refuses: refuse to write outside the tools declared in spec/tools.yaml"},
    "GR-02": {"kind": "guardrail", "enforcement": "blocking", "applies_to": "all agents",
              "rule": "no automation of any step listed in spec/not_automated.csv",
              "message": "GR-02 refuses: no automation of any step listed in spec/not_automated.csv"},
    "GR-03": {"kind": "guardrail", "enforcement": "blocking", "applies_to": "all agents",
              "rule": "enforce every blocking rule in spec/rules.csv before an agent's output is written",
              "message": "GR-03 refuses: enforce every blocking rule in spec/rules.csv before an agent's output is written"},
    "GR-04": {"kind": "guardrail", "enforcement": "blocking", "applies_to": "all agents",
              "rule": "escalate rather than decide when a required field is in spec/open_items.csv",
              "message": "GR-04 refuses: escalate rather than decide when a required field is in spec/open_items.csv"},
}

GUARDRAILS: dict[str, dict[str, str]] = {
    "GR-01": {"status": "enforced", "enforced_by": "enforce_gr_01"},
    "GR-02": {"status": "enforced", "enforced_by": "enforce_gr_02"},
    "GR-03": {"status": "enforced", "enforced_by": "enforce_gr_03"},
    "GR-04": {"status": "enforced", "enforced_by": "enforce_gr_04"},
    "BR-ACT_01": {"status": "enforced", "enforced_by": "enforce_br_act_01"},
    "BR-ACT_02": {"status": "enforced", "enforced_by": "enforce_br_act_02"},
    "BR-ACT_03": {"status": "enforced", "enforced_by": "enforce_br_act_03"},
    "BR-ACT_04": {"status": "enforced", "enforced_by": "enforce_br_act_04"},
}
# Guardrail rules bind every agent; run_case calls these before each action.
ALL_AGENT_RULES: tuple[str, ...] = ("GR-01", "GR-02", "GR-03", "GR-04")

# Fields that an open item leaves undecided. The open items on BLK_01 (HR-201:BLK_01:TOOL_01, HR-201:BLK_01:TOOL_02)
# name tools, not case fields, and take their default assumption, so no field is held here.
OPEN_ITEM_FIELDS: frozenset[str] = frozenset()

# Values the Precord names for a passed verification (completion_conditions). No status enum is declared.
KYC_VERIFIED = "KYC verified successfully"
BANK_VERIFIED = "Bank details verified"
# BR-ACT_02 "queued": the Precord names no queue status value, so only an explicit queued flag counts.
QUEUED_KEY = "queued"

# Assumptions where a rule names a format without a value (RULE_PARAMETER_MISSING, reported as gaps):
# email needs one "@" with text either side and a dot in the domain; an Indian PIN code is six digits not starting
# with 0; an IFSC is four letters, a zero, and six letters or digits (the RBI format).
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PINCODE_PATTERN = re.compile(r"^[1-9][0-9]{5}$")
IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
# The Precord ships no pincode-to-state reference, so a mismatch can only be proven when one is supplied.
PINCODE_STATE_REFERENCE: dict[str, str] = {}

_log = logging.getLogger(f"solution.{AGENT_ID}")


class GuardrailRefusal(Exception):
    """A blocking rule refused a write. Carries the rule's message."""

    def __init__(self, rule_id: str, detail: str = "") -> None:
        self.rule_id = rule_id
        self.detail = detail
        message = RULES[rule_id]["message"] if rule_id in RULES else rule_id
        super().__init__(f"{message} ({detail})" if detail else message)


def allowed_step(step: str) -> bool:
    """Tell whether BLK_01 may act at a step: only S1 to S4, never a person step."""
    return step in SERVES_STEPS and step not in FORBIDDEN_STEPS


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _value(case: dict[str, Any], response: dict[str, Any] | None, field: str) -> Any:
    if response and not _blank(response.get(field)):
        return response.get(field)
    return case.get(field)


# --- guardrails that bind every agent ---------------------------------------------------------------------------

def enforce_gr_01(case: dict[str, Any], action_id: str | None = None, *, tool_id: str | None = None,
                  **_: Any) -> None:
    """GR-01: a write goes only through a tool declared for this agent and for the action that writes."""
    if tool_id is not None and tool_id not in TOOLS:
        raise GuardrailRefusal("GR-01", f"tool {tool_id} is not declared for {AGENT_ID}")
    if action_id is not None:
        action = ACTIONS.get(action_id)
        if action is None:
            raise GuardrailRefusal("GR-01", f"{action_id} is not an action of {AGENT_ID}")
        undeclared = [t for t in action["tool_ids"] if t not in TOOLS]
        if undeclared:
            raise GuardrailRefusal("GR-01", f"{action_id} names undeclared tools {undeclared}")
        if tool_id is not None and tool_id not in action["tool_ids"]:
            raise GuardrailRefusal("GR-01", f"{action_id} may not call {tool_id}")


def enforce_gr_02(case: dict[str, Any], action_id: str | None = None, *, step_id: str | None = None,
                  **_: Any) -> None:
    """GR-02: never act at a step a person does (S6, S8) or at a step BLK_01 does not serve."""
    steps = [s for s in (step_id, ACTIONS.get(action_id or "", {}).get("step_id")) if s]
    for step in steps:
        if not allowed_step(step):
            raise GuardrailRefusal("GR-02", f"step {step} is not automated by {AGENT_ID}")


def enforce_gr_03(case: dict[str, Any], action_id: str | None = None, **_: Any) -> None:
    """GR-03: every blocking rule of the action has an enforcer in this module before its output is written."""
    if action_id is None:
        return
    action = ACTIONS.get(action_id)
    if action is None:
        raise GuardrailRefusal("GR-03", f"{action_id} is not an action of {AGENT_ID}")
    for rule_id in action["rule_ids"]:
        binding = GUARDRAILS.get(rule_id)
        if binding is None or binding.get("status") != "enforced" or not callable(globals().get(binding["enforced_by"])):
            raise GuardrailRefusal("GR-03", f"{rule_id} has no enforcer")


def enforce_gr_04(case: dict[str, Any], action_id: str | None = None, *, fields: Any = None, **_: Any) -> None:
    """GR-04: escalate when a field the action needs is still undecided in an open item."""
    needed = set(fields or ())
    if action_id in ACTIONS:
        needed.update(ACTION_DETAILS[action_id]["reads"])
    held = sorted(needed & OPEN_ITEM_FIELDS)
    if held:
        raise GuardrailRefusal("GR-04", f"open item holds {held}")


# --- business rules of the actions -------------------------------------------------------------------------------

def enforce_br_act_01(case: dict[str, Any], *, response: dict[str, Any] | None = None,
                      registered_mobile_numbers: Any = (), **_: Any) -> None:
    """BR-ACT_01: the mobile number is present and not already registered; the email has a valid format."""
    mobile = _value(case, response, "Mobile Number")
    email = _value(case, response, "Email")
    if _blank(mobile):
        raise GuardrailRefusal("BR-ACT_01", "Mobile Number missing")
    if str(mobile).strip() in {str(m).strip() for m in registered_mobile_numbers or ()}:
        raise GuardrailRefusal("BR-ACT_01", "Mobile Number already registered")
    if response and (response.get("duplicate") is True or response.get("status") == "duplicate"):
        raise GuardrailRefusal("BR-ACT_01", "Mobile Number already registered")
    if _blank(email) or not EMAIL_PATTERN.match(str(email).strip()):
        raise GuardrailRefusal("BR-ACT_01", "Email format invalid")


def enforce_br_act_02(case: dict[str, Any], *, response: dict[str, Any] | None = None, **_: Any) -> None:
    """BR-ACT_02: the KYC service answered with a status, or the query is queued. Unavailable never passes."""
    if response and response.get("status") == "error":
        raise GuardrailRefusal("BR-ACT_02", "KYC service error")
    queued = (response or {}).get(QUEUED_KEY) is True or case.get(QUEUED_KEY) is True
    if _blank(_value(case, response, "KYC verification status")) and not queued:
        raise GuardrailRefusal("BR-ACT_02", "no KYC response received or queued")


def enforce_br_act_03(case: dict[str, Any], *, response: dict[str, Any] | None = None, **_: Any) -> None:
    """BR-ACT_03: the pincode is well formed and, where a reference is supplied, matches the state."""
    pincode = _value(case, response, "Pincode")
    if _blank(pincode) or not PINCODE_PATTERN.match(str(pincode).strip()):
        raise GuardrailRefusal("BR-ACT_03", "Pincode missing or malformed")
    state = _value(case, response, "State")
    expected = PINCODE_STATE_REFERENCE.get(str(pincode).strip()[:3])
    if expected is not None and not _blank(state) and str(state).strip().casefold() != expected.casefold():
        raise GuardrailRefusal("BR-ACT_03", "Pincode and State do not match")


def enforce_br_act_04(case: dict[str, Any], *, response: dict[str, Any] | None = None, **_: Any) -> None:
    """BR-ACT_04: the IFSC has the valid format and the bank verification passed."""
    ifsc = _value(case, response, "IFSC Code")
    if _blank(ifsc) or not IFSC_PATTERN.match(str(ifsc).strip().upper()):
        raise GuardrailRefusal("BR-ACT_04", "IFSC Code format invalid")
    status = _value(case, response, "Bank verification status")
    if _blank(status) or str(status).strip().casefold() != BANK_VERIFIED.casefold():
        raise GuardrailRefusal("BR-ACT_04", "Bank account verification not passed")


# --- tools -------------------------------------------------------------------------------------------------------

def _invoke_tool(action_id: str, tool_id: str, payload: dict[str, Any], correlation_id: str) -> dict[str, Any]:
    """Call one declared integration. The integration resolves endpoint and credential."""
    enforce_gr_01({}, action_id, tool_id=tool_id)
    module = importlib.import_module(INTEGRATION_MODULES[tool_id])
    started = _now()
    result = module.invoke(payload, correlation_id)
    emit_event("tool.call", correlation_id, step_id=ACTIONS[action_id]["step_id"], ts_start=started,
               status=str(result.get("status") or "ok"), actor_type="system", actor_id=tool_id)
    return result


def _reads(case: dict[str, Any], action_id: str) -> dict[str, Any]:
    return {field: case.get(field) for field in ACTION_DETAILS[action_id]["reads"]}


# --- actions -----------------------------------------------------------------------------------------------------

def _guard_all_agents(case: dict[str, Any], action_id: str) -> None:
    for rule_id in ALL_AGENT_RULES:
        globals()[GUARDRAILS[rule_id]["enforced_by"]](case, action_id)


def act_01_extract_and_validate_intake(case: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
    """ACT_01 (S1): validate intake contact data, then draft the application record through TOOL_01."""
    _guard_all_agents(case, "ACT_01")
    reads = _reads(case, "ACT_01")
    enforce_br_act_01(reads)
    result = _invoke_tool("ACT_01", "TOOL_01", {"action_id": "ACT_01", **reads}, correlation_id)
    response = result.get("response") or {}
    enforce_br_act_01(reads, response=response)
    return {"Application record draft": response.get("Application record draft")}


def act_02_orchestrate_kyc_verification(case: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
    """ACT_02 (S2): query the external KYC service through TOOL_02. No answer and no queue is never a pass."""
    _guard_all_agents(case, "ACT_02")
    reads = _reads(case, "ACT_02")
    result = _invoke_tool("ACT_02", "TOOL_02", dict(reads), correlation_id)
    enforce_br_act_02(reads, response=result)
    return {"KYC verification status": result.get("KYC verification status")}


def act_03_populate_profile_and_address(case: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
    """ACT_03 (S3): check the pincode, then update the agent profile through TOOL_01."""
    _guard_all_agents(case, "ACT_03")
    reads = _reads(case, "ACT_03")
    enforce_br_act_03(reads)
    result = _invoke_tool("ACT_03", "TOOL_01", {"action_id": "ACT_03", **reads}, correlation_id)
    response = result.get("response") or {}
    return {"Agent profile update": response.get("Agent profile update")}


def act_04_resolve_ifsc_and_verify_bank(case: dict[str, Any], *, correlation_id: str = "") -> dict[str, Any]:
    """ACT_04 (S4): resolve the IFSC to bank, city and branch, and verify the account through TOOL_01."""
    _guard_all_agents(case, "ACT_04")
    reads = _reads(case, "ACT_04")
    result = _invoke_tool("ACT_04", "TOOL_01", {"action_id": "ACT_04", **reads}, correlation_id)
    response = result.get("response") or {}
    enforce_br_act_04(reads, response=response)
    return {field: response.get(field) for field in ACTION_DETAILS["ACT_04"]["writes"]}


# --- exceptions, failure and interactions -------------------------------------------------------------------------

def _mask(field: str, value: Any) -> Any:
    if field not in MASKED_FIELDS or value is None:
        return value
    try:
        from solution.masking import mask_value
    except ModuleNotFoundError:
        text = str(value)
        return ("*" * max(len(text) - 4, 0)) + text[-4:] if len(text) > 4 else "[masked]"
    return mask_value("partial", value)


def notify(interaction_id: str, case_id: str, text: str, fields: dict[str, Any] | None = None, *,
           send: Callable[[str, dict[str, Any]], bool] | None = None, consent: bool = False) -> dict[str, Any]:
    """Build one message on the declared channel, masked per its policy. Falls back when the channel fails.

    No delivery integration is declared for INT_01, so without `send` the message is returned undelivered."""
    contract = INTERACTIONS[interaction_id]
    if contract["consent_required"] == "true" and not consent:
        return {"interaction_id": interaction_id, "sent": False, "reason": "consent required"}
    message = {"interaction_id": interaction_id, "case_id": case_id, "text": text,
               "fields": {name: _mask(name, value) for name, value in (fields or {}).items()}}
    channel, sent = contract["channel"], False
    if send is not None:
        sent = bool(send(channel, message))
        if not sent:
            channel = contract["fallback_channel"]
            sent = bool(send(channel, message))
    return {**message, "channel": channel, "sent": sent}


def _exc_01(case_id: str, error: BaseException | str) -> dict[str, Any]:
    """EXC_01: duplicate or invalid intake data. Record creation halts; a person resolves it; resume at ACT_01."""
    contract = EXCEPTIONS["EXC_01"]
    return {
        "exception_id": "EXC_01", "status_tag": "duplicate_or_invalid_intake_hold", "alert": True,
        "containment": contract["containment"], "record_creation_halted": True,
        "escalation_route": contract["escalation_route"], "human_work_item": contract["human_work_item"],
        "recovery": contract["recovery"], "resume_from": contract["resume_from"], "error": str(error),
        "notification": notify("INT_01", case_id, "Duplicate mobile/PAN entry or validation error during intake."),
    }


def _exc_02(case_id: str, error: BaseException | str) -> dict[str, Any]:
    """EXC_02: KYC service unavailable. Verification is never bypassed; the case waits on the retry queue."""
    contract = EXCEPTIONS["EXC_02"]
    return {
        "exception_id": "EXC_02", "status_tag": "kyc_service_unavailable", "alert": True,
        "containment": contract["containment"], "verification_bypassed": False,
        "escalation_route": contract["escalation_route"], "human_work_item": contract["human_work_item"],
        "recovery": contract["recovery"], "resume_from": contract["resume_from"], "error": str(error),
    }


_EXCEPTION_HANDLERS = {"EXC_01": "_exc_01", "EXC_02": "_exc_02"}


def handle_exception(exception_id: str, case_id: str, error: BaseException | str) -> dict[str, Any]:
    """Route a declared exception on its own path. An undeclared one degrades to human review."""
    handler = _EXCEPTION_HANDLERS.get(exception_id)
    if handler is None:
        return handle_failure(case_id, error)
    _log.warning("%s on case %s: %s", exception_id, case_id, error)
    return globals()[handler](case_id, error)


def handle_failure(case_id: str, error: BaseException | str) -> dict[str, Any]:
    """FAILURE_BEHAVIOUR: halt automatic progression, log the failure trace, flag the case for human review."""
    _log.error("BLK_01 failure on case %s: %r", case_id, error, exc_info=isinstance(error, BaseException))
    return {"status_tag": "halted_for_human_review", "alert": True, "halted": True,
            "escalation_route": FAILURE_ROUTE, "error_context": f"{type(error).__name__}: {error}"
            if isinstance(error, BaseException) else str(error), "failure_behaviour": FAILURE_BEHAVIOUR["text"]}


# --- events ------------------------------------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit_event(event_name: str, case_id: str, **fields: Any) -> dict[str, Any]:
    """Build one event of schemas/event.schema.json and feed it to the Playground KPI store."""
    now = _now()
    event: dict[str, Any] = {
        "case_id": case_id, "step_id": "", "agent_id": AGENT_ID, "event_type": event_name,
        "actor_type": "agent", "actor_id": AGENT_ID, "ts_start": now, "ts_end": now, "model": MODEL,
        "prompt_version": PROMPT_VERSION, "agent_version": AGENT_VERSION, "tokens_in": 0, "tokens_out": 0,
        "cost": 0.0, "status": "ok", "confidence": 0.0, "override_flag": False, "override_reason": "",
        "guardrail_event": "",
    }
    event.update(fields)
    event["event_type"], event["case_id"] = event_name, case_id
    try:
        from kpis.service import feed_events
    except ModuleNotFoundError as error:
        if error.name not in ("kpis", "kpis.service"):
            raise
        return event
    feed_events([event])
    return event


# --- execution path ----------------------------------------------------------------------------------------------

def _validate(instance: Any, schema: dict[str, Any]) -> None:
    import jsonschema

    jsonschema.validate(instance, {k: v for k, v in schema.items() if k != "_provenance"})


def run_case(case_id: str, case: dict[str, Any]) -> dict[str, Any]:
    """Run ACT_01 to ACT_04 in order. A refusal or an error stops the case and routes it to its exception."""
    _validate(case, INPUT_SCHEMA)
    current = dict(case)
    trace: list[str] = []
    action_id: str | None = FIRST_ACTION
    next_id: str | None = None
    while action_id in ACTIONS:
        action, details = ACTIONS[action_id], ACTION_DETAILS[action_id]
        started = _now()
        try:
            for rule_id in ALL_AGENT_RULES:
                globals()[GUARDRAILS[rule_id]["enforced_by"]](current, action_id)
            writes = globals()[action["function"]](current, correlation_id=case_id)
            _validate(writes, OUTPUT_SCHEMA)
        except Exception as error:  # a refusal and a failure both stop the case here
            refused = isinstance(error, GuardrailRefusal)
            route = handle_exception(details["on_failure"], case_id, error)
            emit_event("agent.decision", case_id, step_id=action["step_id"], ts_start=started,
                       status="guardrail_refused" if refused else type(error).__name__,
                       guardrail_event=error.rule_id if refused else "")
            return {"case": current, "trace": trace, "outcome": "routed",
                    "next": details["on_failure"], "route": route}
        current = {**current, **{k: v for k, v in writes.items() if k in details["writes"]}}
        trace.append(action_id)
        emit_event("step.completed", case_id, step_id=action["step_id"], ts_start=started)
        next_id = details["on_success"]
        action_id = next_id
    return {"case": current, "trace": trace, "outcome": "completed", "next": next_id, "route": None}


# --- ADK composition ---------------------------------------------------------------------------------------------

def make_agent() -> Any:
    """Build the declared sequential composition of BLK_01.1 and BLK_01.2. The parent holds no model and no tool."""
    from google.adk.agents import SequentialAgent

    sub_agents = [importlib.import_module(sub["module"]).make_agent() for sub in SUB_AGENTS]
    return SequentialAgent(name=NAME, description=PURPOSE, sub_agents=sub_agents)


def _sub_agent_tool_bindings() -> dict[str, str]:
    """Union of the leaf sub-agents' TOOL_BINDINGS. A sub-agent module not yet built contributes none."""
    bindings: dict[str, str] = {}
    for sub in SUB_AGENTS:
        try:
            module = importlib.import_module(sub["module"])
        except ModuleNotFoundError as error:
            if error.name not in (sub["module"], "agents"):
                raise
            continue
        bindings.update(getattr(module, "TOOL_BINDINGS", {}) or {})
    return bindings


# Last, so a sub-agent that reads this module's constants during import finds them defined.
TOOL_BINDINGS: dict[str, str] = _sub_agent_tool_bindings()
