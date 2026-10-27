"""BLK_02 · Document & QC Review Agent Block (Precord v2, agents.yaml BLK_02, rung Pilot).

Automates document upload classification, file validation and the QC draft for the Operations / QC reviewer.
It serves S5 (ACT_05) and S7 (ACT_07). S6 and S8 stay with a person: allowed_step refuses them, and no function
of this module acts on them. The agent drafts for approval only; the final decision is checkpoint CHK_02.

Decision type is hybrid: rule checks, slot completeness and the discrepancy list are code (run_case); the model runs
on the merged case through make_agent(). The model is built by solution.adk_model, which applies the declared retries.
TOOL_03 is a labelled mock (open item HR-201:BLK_02:TOOL_03) and blocks promotion.
"""
from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone
from typing import Any


REQUIREMENT_REFS = (
    "BLK_02",
    "agent_specifications@row:2",
    "agent_block_actions@row:5",
    "agent_block_actions@row:7",
    "agent_exception_routes@row:3",
    "agent_exception_routes@row:5",
    "agent_interaction_contracts@row:2",
    "tacit_knowledge@row:5",
    "not_automated_register@row:1",
    "not_automated_register@row:2",
    "prompts/BLK_02.md",
    "schemas/BLK_02.in.schema.json",
    "schemas/BLK_02.out.schema.json",
    "schemas/event.schema.json",
    "standard/runtime.defaults.yaml#guardrails[1]",
    "standard/runtime.defaults.yaml#guardrails[2]",
    "standard/runtime.defaults.yaml#guardrails[3]",
    "standard/runtime.defaults.yaml#guardrails[4]",
    "open_items@HR-201:BLK_02:TOOL_03",
)

AGENT_ID = "BLK_02"
AGENT_NAME = "Document & QC Review Agent Block"
ADK_NAME = "document_qc_review_agent_block"
PRECORD = "7382e6e982b25d279e87608d60f6d2e6faa6d5ba151bbaa6a99338e507891694"

MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-1.5-flash"  # declared; ADK has no model fallback, so it is never called (deviation)
TEMPERATURE = 0.0
TIMEOUT_S = 60
MAX_RETRIES = 2
MAX_OUTPUT_TOKENS = 1024
AUTONOMY = "draft_for_approval"
DECISION_TYPE = "hybrid"
MEMORY_MODE = "Session state"
GROUNDING_MODE = "Full-context injection"
BUDGETS = {"max_latency_ms": 30000, "max_tokens_per_case": 4096}  # recorded only; ADK enforces no per-case budget
CHECKPOINTS = ("CHK_02",)
TRIGGER = "Document upload completion"

SERVES_STEPS = ("S5", "S7")
# context person_steps; the same steps are in not_automated_register (EX_01 regulatory, EX_02 relationship).
FORBIDDEN_STEPS = ("S6", "S8")

TOOLS = ["TOOL_03"]
# Registered callable name -> declared tool ID. tool_policy applies the allowlist (H-09) through it.
TOOL_BINDINGS = {"classify_and_validate_documents": "TOOL_03"}

INPUT_SCHEMA = {
    "$id": "BLK_02.in.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "_provenance": {},
    "description": "No surface with a matching action is mapped to S5, S6, S7, so nothing is known about what BLK_02 reads at it. That is an absence in the surface registers, not a statement that the agent touches nothing.",
    "properties": {},
    "required": [],
    "title": "BLK_02 input",
    "type": "object",
}
OUTPUT_SCHEMA = {
    "$id": "BLK_02.out.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "_provenance": {},
    "description": "No surface with a matching action is mapped to S5, S6, S7, so nothing is known about what BLK_02 writes at it. That is an absence in the surface registers, not a statement that the agent touches nothing.",
    "properties": {},
    "required": [],
    "title": "BLK_02 output",
    "type": "object",
}
EVENT_SCHEMA_REQUIRED = (
    "case_id", "step_id", "agent_id", "event_type", "actor_type", "actor_id", "ts_start", "ts_end", "model",
    "prompt_version", "agent_version", "tokens_in", "tokens_out", "cost", "status", "confidence", "override_flag",
    "override_reason", "guardrail_event",
)

ACTIONS = {
    "ACT_05": {"step_id": "S5", "tool_ids": ["TOOL_03"], "rule_ids": ["BR-ACT_05"], "function": "act_05_classify_and_validate_documents"},
    "ACT_07": {"step_id": "S7", "tool_ids": ["TOOL_01"], "rule_ids": ["BR-ACT_07"], "function": "act_07_draft_qc_review"},
}
# agent_block_actions@row:5 and @row:7. on_success CHK_02 names no action of this agent, so the case stops there.
ACTION_FLOW = {
    "ACT_05": {"name": "Classify and Validate Uploaded Documents", "on_success": "ACT_07", "on_failure": "EXC_03",
               "reads": ("Profile Photo", "PAN Card", "Aadhaar Front", "Aadhaar Back", "Bank Proof", "Education Document"),
               "writes": ("Categorized document slots", "Validation status")},
    "ACT_07": {"name": "Draft QC Review & Anomaly Detection", "on_success": "CHK_02", "on_failure": "EXC_05",
               "reads": ("Application Status", "Uploaded Documents", "KYC Verification Results"),
               "writes": ("Reviewer remark drafts", "Discrepancy recommendation list")},
}
FIRST_ACTION = "ACT_05"
# The tools each action really calls. ACT_07 declares TOOL_01, but BLK_02's tools list does not hold it and
# TOOL_01's mock has no ACT_07 contract, so ACT_07 calls no tool (GR-01). The Completion Report records the conflict.
ACTION_CALLS = {"ACT_05": ("TOOL_03",), "ACT_07": ()}

# The six document slots that INT_UI5 (Document Upload screen) marks required: true.
DOCUMENT_SLOTS = ACTION_FLOW["ACT_05"]["reads"]
# BR-ACT_05 names a permitted extension list and a size limit but gives no value (RULE_PARAMETER_MISSING).
# Empty means undeclared: the enforcer then checks only what needs no parameter. Never fill these by guess.
PERMITTED_EXTENSIONS: tuple[str, ...] = ()
MAX_FILE_SIZE_BYTES: int | None = None
# GR-04: case fields of this agent that an open item holds. No open item names a field BLK_02 reads or writes.
OPEN_ITEM_FIELDS: dict[str, str] = {}

EXCEPTIONS = {
    "EXC_03": {"action_id": "ACT_05", "escalation_route": "Prospective agent upload interface", "resume_from": "ACT_05"},
    "EXC_05": {"action_id": "ACT_07", "escalation_route": "Operations / QC reviewer workbench", "resume_from": "ACT_07"},
}
EXCEPTION_DETAILS = {
    "EXC_03": {"category": "Document Validation Failure", "trigger": "Invalid file size, extension, or unreadable document",
               "containment": "Reject file upload into categorized slot",
               "human_work_item": "Re-upload valid document in required format",
               "recovery": "Re-process newly uploaded file asset"},
    "EXC_05": {"category": "QC Review Discrepancy", "trigger": "Document anomaly or data mismatch detected by agent draft",
               "containment": "Route case to Operations QC exception list",
               "human_work_item": "Inspect flagged document discrepancy and approve or reject",
               "recovery": "Record human review decision and proceed accordingly"},
}

INTERACTIONS = {
    "INT_02": {"channel": "Operations Work Queue", "consent_required": "false", "fallback_channel": "Email alert"},
}
INTERACTION_DETAILS = {
    "INT_02": {"recipient": "Operations / QC reviewer", "trigger": "Application state transitions to QC Pending",
               "purpose": "Present pre-reviewed application and document anomaly draft for QC approval",
               "response_expected": "true",
               "sensitive_data_policy": "Full PII visible only to authorized operations personnel"},
}

AUDIT_EVENTS = ("agent.decision", "human.review", "guardrail.triggered")
COMPLETION_CONDITIONS = ["Documents classified and validated", "QC draft recommendation generated"]
RESUME_STRATEGY = "Resume from document slot assignment after manual re-upload or override."
FAILURE_BEHAVIOUR = {"text": "Flag unreadable documents or classification ambiguity for human operator inspection."}
FAILURE_ROUTE = "Operations / QC reviewer queue"

RULE_MESSAGES = {
    "BR-ACT_05": "ACT_05 refuses to proceed: File extension permitted; File size within limits",
    "BR-ACT_07": "ACT_07 refuses to proceed: Required verification checks completed",
    "GR-01": "refuse to write outside the tools declared in spec/tools.yaml",
    "GR-02": "no automation of any step listed in spec/not_automated.csv",
    "GR-03": "enforce every blocking rule in spec/rules.csv before an agent's output is written",
    "GR-04": "escalate rather than decide when a required field is in spec/open_items.csv",
}
GUARDRAILS = {
    "GR-01": {"status": "enforced", "enforced_by": "enforce_gr_01_declared_tools"},
    "GR-02": {"status": "enforced", "enforced_by": "enforce_gr_02_not_automated"},
    "GR-03": {"status": "enforced", "enforced_by": "enforce_gr_03_blocking_rules"},
    "GR-04": {"status": "enforced", "enforced_by": "enforce_gr_04_open_items"},
    "BR-ACT_05": {"status": "enforced", "enforced_by": "enforce_br_act_05_file_validity"},
    "BR-ACT_07": {"status": "enforced", "enforced_by": "enforce_br_act_07_verification_complete"},
}
# Guardrail rules bind every agent; run_case runs them before each action.
ALL_AGENT_RULES = ("GR-01", "GR-02", "GR-03", "GR-04")

# Harness rows owed at rung Pilot: tier PoC or Pilot and status not "Not applicable" (17 concepts).
# H-17 and H-20 are MVP and out of scope; H-11 and H-18 are "Not applicable" (choice None).
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
    "H-10": "File / object drop",
    "H-12": "Per-field extraction score",
    "H-13": "Full (input · output · action)",
    "H-14": "Degrade to human",
    "H-15": "Latency target",
    "H-16": "Few-shot examples",
    "H-19": "Image",
    "H-21": "Tracing on · version IDs on every event",
}
FEW_SHOT: list[dict[str, Any]] = []  # agents.yaml few_shot is empty (FEW_SHOT_EMPTY)

PROMPT = """# BLK_02 · Document & QC Review Agent Block

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

You are the Document & QC Review Agent Block serving steps S5, S6, and S7. You automate document upload classification, file validation, cropping, declaration generation support, and QC pre-review flagging.
You read document upload completions and write to InsureBuddy document store through TOOL_03. Leave the rest of the case alone.
Classify uploaded document files into categorized slots including profile photo, PAN card, Aadhaar front, Aadhaar back, bank proof, education document, and other supporting documents.
Validate uploaded file formats, sizes, and completeness against mandatory document slots.
Generate declaration PDF support and prepare a QC draft recommendation for operations review.
You must not approve agents or finalize consent declarations, as regulatory compliance requires active human agreement and secondary OTP verification.
When documents are unreadable, corrupted, or have classification ambiguity, flag them for human operator inspection and route to the Operations / QC reviewer queue.

### Judgement at these steps

- Reviewers approve applications rapidly without visually inspecting or opening the uploaded documents. Looks at: clicking approve immediately, not opening View action on files. (User / Operations)

### Never automate these

- S6 (regulatory): Consent and declaration require explicit human legal agreement, active review of terms and conditions, and a secondary OTP verification step bound by regulatory compliance rules. **— this is one of your steps**
- S8 (relationship): Post-approval training modules and the POSP certification exam must be completed directly by the prospective agent to satisfy regulatory competency standards.

## 3 · Domain pack — shared vocabulary

`context/ontology_nodes.csv` is the naming authority for every name you write. Where this process's word and yours differ, use this process's.

| Term | Also called | Means |
| --- | --- | --- |
| Aadhaar Card | Aadhaar address, Aadhaar back, Aadhaar front, Aadhaar linkage, Aadhaar Number, Aadhar card, Card Back, PAN Aadhaar | The unique resident identification document collected for identity verification during onboarding. |
| PAN Card | PAN Number | The tax identification document submitted for financial and identity validations. |
| Agent | Agent Approved Successfully, Agent Category, agent code, Agent modal, Agent Onboard, Agent Type, different agent, Field Level Sales, FLS User, Onboard POSP, POSP Create, POSP Exam, POSP Journey, POSP Name, Training POSP | The individual undergoing onboarding to become a certified sales representative or Point of Sales Person. |
| Consent and Declaration | Agree control, Consent Submit, Consent Training, Declaration PDF, disqualification declaration, Documents Consent, PDF generated, second OTP, Verify OTP | The legally binding acknowledgments and OTP verifications executed by the applicant prior to final submission. |
| Operations Quality Control | Certification Pending, Discurrency List, Discrepancy List, Document Center, Documents Submit, Documents Upload Details, Operations QC, QC Pending, Raise Discrepancy | The review process where internal operations staff inspect uploaded documents and raise discrepancies. |
| Educational Qualification | Education Document, Education Qualification | The academic credentials submitted to verify educational eligibility. |

## 4 · Invocation variables — supplied per case

  case               the case object, `schemas/case.schema.json`
  case_id            the case this invocation is about
  agent_id           `BLK_02`
  checkpoint         `CHK_02`, where a person sees this
  correlation_id     threaded through every tool call, for the trace
"""

# agents.yaml serves_steps is S5 and S7, and S6 is a person step, so the scope note below overrides the prompt's S6.
SCOPE_NOTE = """
## Scope of this build

You serve S5 and S7 only. S6 (Consent and Declaration) and S8 (Post-Approval Training and Exam) are done by a person:
do not act on them, and do not generate or finalize a declaration. You never approve, reject or raise a discrepancy:
the Operations / QC reviewer decides at checkpoint CHK_02. The case you receive already holds the deterministic
results of ACT_05 and ACT_07 (categorized slots, validation status, discrepancy list); do not recompute them and do
not call TOOL_03 again for slots the case already holds.
"""


def _output_instruction() -> str:
    fields = list(OUTPUT_SCHEMA.get("properties") or {})
    required = list(OUTPUT_SCHEMA.get("required") or [])
    listed = ", ".join(fields) if fields else "(none: the output schema declares no fields, so answer with {})"
    text = f"\nAnswer with one JSON object whose keys are only these output fields: {listed}.\n"
    if required:
        text += ("Required fields: " + ", ".join(required)
                 + ". Copy each required field's input value when the step does not change it.\n")
    else:
        text += "The output schema names no required field.\n"
    return text + "No other input field goes in the answer.\n"


INSTRUCTION = PROMPT + SCOPE_NOTE + _output_instruction()
PROMPT_VERSION = "BLK_02-" + hashlib.sha256(INSTRUCTION.encode("utf-8")).hexdigest()[:12]
AGENT_VERSION = "BLK_02@" + PRECORD[:12]


class GuardrailRefusal(Exception):
    """A blocking rule refused the write it guards. The message is the rule's declared message."""

    def __init__(self, message: str = "", rule_id: str | None = None, detail: str = "") -> None:
        super().__init__(message if not detail else f"{message} ({detail})")
        self.message = message
        self.rule_id = rule_id
        self.detail = detail


class QCDiscrepancyDetected(Exception):
    """ACT_07 found a document anomaly or data mismatch (EXC_05 trigger). It carries the drafted list."""

    def __init__(self, discrepancies: list[dict[str, Any]], remarks: list[str]) -> None:
        super().__init__(f"{len(discrepancies)} document discrepancy(ies) need QC inspection")
        self.discrepancies = discrepancies
        self.remarks = remarks


def _refuse(rule_id: str, detail: str = "") -> None:
    raise GuardrailRefusal(RULE_MESSAGES[rule_id], rule_id=rule_id, detail=detail)


def allowed_step(step: str) -> bool:
    """True only for a step this agent serves. Every person step and not-automated step is False."""
    return step in SERVES_STEPS and step not in FORBIDDEN_STEPS


def validate_input(case: dict[str, Any]) -> None:
    import jsonschema

    jsonschema.validate(case, INPUT_SCHEMA)


def validate_output(answer: dict[str, Any]) -> None:
    import jsonschema

    jsonschema.validate(answer, OUTPUT_SCHEMA)


# ---------------------------------------------------------------- guardrail enforcers

def enforce_gr_01_declared_tools(case: dict[str, Any], action_id: str | None = None,
                                 tool_ids: tuple[str, ...] | list[str] | None = None) -> None:
    """GR-01: refuse a call or write through a tool this agent does not declare."""
    calls = tuple(tool_ids) if tool_ids is not None else ACTION_CALLS.get(action_id or "", ())
    outside = [tool for tool in calls if tool not in TOOLS]
    if outside:
        _refuse("GR-01", f"{action_id or 'call'} would use undeclared tool(s) {outside}")


def enforce_gr_02_not_automated(case: dict[str, Any], action_id: str | None = None, step_id: str | None = None) -> None:
    """GR-02: refuse to act on a step that is not automated or that this agent does not serve."""
    step = step_id or (ACTIONS.get(action_id or "") or {}).get("step_id")
    if action_id is not None and action_id not in ACTIONS:
        _refuse("GR-02", f"{action_id} is not an action of {AGENT_ID}")
    if step is not None and not allowed_step(step):
        _refuse("GR-02", f"step {step} is not automated by {AGENT_ID}")


def enforce_gr_03_blocking_rules(case: dict[str, Any], action_id: str | None = None) -> None:
    """GR-03: refuse an action whose blocking rules have no enforcing function in this module."""
    if action_id is None:
        return
    for rule_id in (ACTIONS.get(action_id) or {}).get("rule_ids", ()):
        entry = GUARDRAILS.get(rule_id) or {}
        if entry.get("status") != "enforced" or not callable(globals().get(entry.get("enforced_by", ""))):
            _refuse("GR-03", f"{rule_id} of {action_id} has no enforcer")


def enforce_gr_04_open_items(case: dict[str, Any], action_id: str | None = None) -> None:
    """GR-04: escalate, never decide, when a field the action reads or writes is held by an open item."""
    flow = ACTION_FLOW.get(action_id or "") or {}
    fields = (*flow.get("reads", ()), *flow.get("writes", ())) if flow else tuple(OPEN_ITEM_FIELDS)
    held = {field: OPEN_ITEM_FIELDS[field] for field in fields if field in OPEN_ITEM_FIELDS}
    if held:
        _refuse("GR-04", f"open item(s) hold {held}")


def _file_parts(value: Any) -> tuple[str | None, Any]:
    """Give (file name, size in bytes) of one document slot value: a file name, or a dict with file_name and size_bytes."""
    if isinstance(value, str):
        return value, None
    if isinstance(value, dict):
        return value.get("file_name"), value.get("size_bytes")
    return None, None


def enforce_br_act_05_file_validity(case: dict[str, Any], action_id: str | None = "ACT_05") -> None:
    """BR-ACT_05: refuse a document whose extension is not permitted or whose size is not within limits.

    An unreadable entry (no file name, no extension, a size that is not a positive integer) is refused too.
    The permitted list and the limit are checked only when the Precord declares them; it declares neither."""
    for slot in DOCUMENT_SLOTS:
        value = case.get(slot)
        if value is None:
            continue
        name, size = _file_parts(value)
        if not isinstance(name, str) or "." not in name.strip(".") or not name.rsplit(".", 1)[-1].strip():
            _refuse("BR-ACT_05", f"{slot}: no readable file name with an extension")
        extension = name.rsplit(".", 1)[-1].strip().lower()
        if PERMITTED_EXTENSIONS and extension not in PERMITTED_EXTENSIONS:
            _refuse("BR-ACT_05", f"{slot}: extension .{extension} is not permitted")
        if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size <= 0):
            _refuse("BR-ACT_05", f"{slot}: file size is not a positive number of bytes")
        if MAX_FILE_SIZE_BYTES is not None and (size is None or size > MAX_FILE_SIZE_BYTES):
            _refuse("BR-ACT_05", f"{slot}: file size is not within {MAX_FILE_SIZE_BYTES} bytes")


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, (str, list, dict, tuple)) and not value)


def enforce_br_act_07_verification_complete(case: dict[str, Any], action_id: str | None = "ACT_07") -> None:
    """BR-ACT_07: refuse the QC draft until the verification results and the uploaded documents are on the case."""
    missing = [field for field in ("KYC Verification Results", "Uploaded Documents") if _empty(case.get(field))]
    if missing:
        _refuse("BR-ACT_07", f"not on the case: {missing}")


# ---------------------------------------------------------------- tool callable (registered with ADK)

def classify_and_validate_documents(profile_photo: str = "", pan_card: str = "", aadhaar_front: str = "",
                                    aadhaar_back: str = "", bank_proof: str = "", education_document: str = "",
                                    tool_context: Any = None) -> dict:
    """Classify uploaded documents into their slots and return each slot's validation status (TOOL_03).

    Args:
        profile_photo: file reference of the Profile Photo, or empty when not uploaded.
        pan_card: file reference of the PAN Card, or empty.
        aadhaar_front: file reference of the Aadhaar Front, or empty.
        aadhaar_back: file reference of the Aadhaar Back, or empty.
        bank_proof: file reference of the Bank Proof, or empty.
        education_document: file reference of the Education Document, or empty.

    Returns:
        dict: "Categorized document slots" and "Validation status"; a value the tool cannot give is null.
    """
    from integrations.tool_03 import invoke

    state = getattr(tool_context, "state", None) or {}
    correlation_id = state.get("correlation_id") if hasattr(state, "get") else None
    if not correlation_id:
        return {"status": "error", "error_message": "No correlation ID in the session; TOOL_03 was not called."}
    values = (profile_photo, pan_card, aadhaar_front, aadhaar_back, bank_proof, education_document)
    payload = {slot: value or None for slot, value in zip(DOCUMENT_SLOTS, values)}
    try:
        enforce_gr_01_declared_tools(payload, tool_ids=("TOOL_03",))
        globals()[GUARDRAILS["BR-ACT_05"]["enforced_by"]](payload)
    except GuardrailRefusal as error:
        return {"status": "error", "rule_id": error.rule_id, "error_message": str(error)}
    return invoke(payload, correlation_id)


# ---------------------------------------------------------------- actions

def act_05_classify_and_validate_documents(case: dict[str, Any], *, correlation_id: str | None = None) -> dict[str, Any]:
    """ACT_05 (S5): validate the uploaded files, then classify them through TOOL_03. Returns only the ACT_05 writes."""
    flow = ACTION_FLOW["ACT_05"]
    reads = {field: copy.deepcopy(case.get(field)) for field in flow["reads"]}
    for rule_id in ACTIONS["ACT_05"]["rule_ids"]:
        globals()[GUARDRAILS[rule_id]["enforced_by"]](reads, "ACT_05")
    from integrations.tool_03 import invoke

    response = invoke(reads, correlation_id or str(case.get("case_id") or ""))
    return {field: response.get(field) for field in flow["writes"]}


def _uploaded_slots(uploaded: Any) -> set[str]:
    """The document slots that the Uploaded Documents value names: dict keys, or list items (names or dicts with slot)."""
    if isinstance(uploaded, dict):
        return {slot for slot, value in uploaded.items() if not _empty(value)}
    if isinstance(uploaded, (list, tuple)):
        names = set()
        for item in uploaded:
            if isinstance(item, str):
                names.add(item)
            elif isinstance(item, dict) and isinstance(item.get("slot"), str):
                names.add(item["slot"])
        return names
    return set()


def act_07_draft_qc_review(case: dict[str, Any], *, correlation_id: str | None = None) -> dict[str, Any]:
    """ACT_07 (S7): draft the QC review for CHK_02. It never approves; the reviewer decides.

    The deterministic part: each required document slot missing from Uploaded Documents is a discrepancy.
    A discrepancy raises QCDiscrepancyDetected, so run_case routes the case to EXC_05. ACT_07 calls no tool."""
    flow = ACTION_FLOW["ACT_07"]
    reads = {field: copy.deepcopy(case.get(field)) for field in flow["reads"]}
    for rule_id in ACTIONS["ACT_07"]["rule_ids"]:
        globals()[GUARDRAILS[rule_id]["enforced_by"]](reads, "ACT_07")
    present = _uploaded_slots(reads["Uploaded Documents"])
    discrepancies = [{"slot": slot, "finding": "required document not uploaded"}
                     for slot in DOCUMENT_SLOTS if slot not in present]
    remarks = [f"{item['slot']}: {item['finding']}; ask the applicant to upload it." for item in discrepancies]
    if discrepancies:
        raise QCDiscrepancyDetected(discrepancies, remarks)
    return {"Reviewer remark drafts": remarks, "Discrepancy recommendation list": discrepancies}


# ---------------------------------------------------------------- exceptions and failure

def handle_exception(exception_id: str, case_id: str, error: BaseException | Any) -> dict[str, Any]:
    """Contain, escalate and give the resume point of one declared exception. Each exception is its own path."""
    if exception_id == "EXC_03":
        return _route_exc_03(case_id, error)
    if exception_id == "EXC_05":
        return _route_exc_05(case_id, error)
    return handle_failure(case_id, error)


def _route(exception_id: str, case_id: str, error: Any, status_tag: str, **extra: Any) -> dict[str, Any]:
    declared, details = EXCEPTIONS[exception_id], EXCEPTION_DETAILS[exception_id]
    return {"exception_id": exception_id, "case_id": case_id, "action_id": declared["action_id"],
            "escalation_route": declared["escalation_route"], "resume_from": declared["resume_from"],
            "containment": details["containment"], "human_work_item": details["human_work_item"],
            "recovery": details["recovery"], "status_tag": status_tag, "alert": True,
            "rule_id": getattr(error, "rule_id", None), "error": str(error), **extra}


def _route_exc_03(case_id: str, error: Any) -> dict[str, Any]:
    """EXC_03: an invalid or unreadable upload. No slot takes the file; the applicant re-uploads, then ACT_05 reruns."""
    return _route("EXC_03", case_id, error, "document_upload_rejected", slot_assignment="rejected")


def _route_exc_05(case_id: str, error: Any) -> dict[str, Any]:
    """EXC_05: a document anomaly or mismatch. The case joins the Operations QC exception list with the drafted findings."""
    return _route("EXC_05", case_id, error, "qc_exception_list",
                  discrepancies=list(getattr(error, "discrepancies", []) or []),
                  remarks=list(getattr(error, "remarks", []) or []))


def handle_failure(case_id: str, error: BaseException | Any) -> dict[str, Any]:
    """FAILURE_BEHAVIOUR: flag the case for human operator inspection on the Operations / QC reviewer queue."""
    return {"case_id": case_id, "status_tag": "flagged_for_human_inspection", "alert": True,
            "escalation_route": FAILURE_ROUTE, "failure_behaviour": FAILURE_BEHAVIOUR["text"], "error": str(error)}


# ---------------------------------------------------------------- interactions and events

def send_interaction(interaction_id: str, case_id: str, message: dict[str, Any], senders: dict[str, Any],
                     *, consent: bool = False) -> dict[str, Any]:
    """Send one declared interaction through the host's sender for its channel; use the fallback channel on failure.

    INT_02 goes to the Operations / QC reviewer, who is authorized for full PII under its sensitive_data_policy."""
    declared = INTERACTIONS[interaction_id]
    if declared["consent_required"] == "true" and not consent:
        return {"interaction_id": interaction_id, "sent": False, "channel": None, "reason": "consent not recorded"}
    for channel in (declared["channel"], declared["fallback_channel"]):
        sender = senders.get(channel)
        if sender is None:
            continue
        try:
            sender({"case_id": case_id, "interaction_id": interaction_id, **message})
        except Exception:  # noqa: BLE001 - a failed channel moves to the fallback channel
            continue
        return {"interaction_id": interaction_id, "sent": True, "channel": channel}
    return {"interaction_id": interaction_id, "sent": False, "channel": None, "reason": "no channel delivered"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit_event(event_name: str, case_id: str, **fields: Any) -> dict[str, Any]:
    """Build one event of schemas/event.schema.json and feed it to the Playground KPI store. The case ID is the correlation ID."""
    if event_name not in AUDIT_EVENTS:
        raise ValueError(f"{event_name} is not an audit event of {AGENT_ID}")
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
        if error.name not in {"kpis", "kpis.service"}:
            raise
        return event
    feed_events([event])
    return event


# ---------------------------------------------------------------- execution path

def run_case(case_id: str, case: dict[str, Any]) -> dict[str, Any]:
    """Run ACT_05 then ACT_07 on a copy of the case. Stop at CHK_02, or route on the first failure."""
    validate_input(case)
    working = copy.deepcopy(case)
    trace: list[str] = []
    action_id: str | None = FIRST_ACTION
    last_success: str | None = None
    while action_id in ACTIONS:
        declared, flow = ACTIONS[action_id], ACTION_FLOW[action_id]
        started = _now()
        try:
            for rule_id in ALL_AGENT_RULES:
                globals()[GUARDRAILS[rule_id]["enforced_by"]](working, action_id)
        except GuardrailRefusal as error:
            return _routed(case_id, case, trace, action_id, error, started)
        trace.append(action_id)
        try:
            writes = globals()[declared["function"]](working, correlation_id=case_id)
        except Exception as error:  # noqa: BLE001 - every action failure takes its declared exception route
            return _routed(case_id, case, trace, action_id, error, started)
        working.update({field: writes[field] for field in flow["writes"] if field in writes})
        emit_event("agent.decision", case_id, step_id=declared["step_id"], ts_start=started, ts_end=_now(),
                   status="ok")
        last_success = flow["on_success"]
        action_id = last_success
    return {"case": working, "trace": trace, "outcome": "completed", "next": last_success, "route": None}


def _routed(case_id: str, case: dict[str, Any], trace: list[str], action_id: str, error: Exception,
            started: str) -> dict[str, Any]:
    step_id = ACTIONS[action_id]["step_id"]
    if isinstance(error, GuardrailRefusal):
        emit_event("guardrail.triggered", case_id, step_id=step_id, ts_start=started, ts_end=_now(),
                   actor_type="system", status="refused", guardrail_event=error.rule_id)
    on_failure = ACTION_FLOW[action_id]["on_failure"]
    route = handle_exception(on_failure, case_id, error) if on_failure in EXCEPTIONS else handle_failure(case_id, error)
    return {"case": copy.deepcopy(case), "trace": trace, "outcome": "routed", "next": None, "route": route}


# ---------------------------------------------------------------- ADK factory

_JSON_TYPES = {"string": str, "integer": int, "number": float, "boolean": bool, "array": list, "object": dict}


def _output_model() -> Any:
    from pydantic import create_model

    properties = OUTPUT_SCHEMA.get("properties") or {}
    required = set(OUTPUT_SCHEMA.get("required") or [])
    fields = {name: ((_JSON_TYPES.get(spec.get("type"), Any)), ... if name in required else None)
              for name, spec in properties.items()}
    return create_model("BLK_02Output", **fields)


def make_agent() -> Any:
    """Build the ADK agent of BLK_02: the declared model, instruction, TOOL_03 callable and enforced output schema."""
    from google.adk.agents import Agent

    from integrations.tool_03 import invoke  # noqa: F401 - TOOL_03 must be importable before the tool is registered
    from solution.adk_model import generate_adk_config, resolve_adk_model

    model = resolve_adk_model(MODEL, max_retries=MAX_RETRIES)
    return Agent(
        name=ADK_NAME,
        model=model,
        description="Automates document upload classification, file validation, and quality control draft generation.",
        instruction=INSTRUCTION,
        tools=[classify_and_validate_documents],
        output_schema=_output_model(),
        generate_content_config=generate_adk_config(model, MAX_RETRIES, temperature=TEMPERATURE,
                                                    max_output_tokens=MAX_OUTPUT_TOKENS),
    )
