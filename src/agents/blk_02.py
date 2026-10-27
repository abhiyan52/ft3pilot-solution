"""BLK_02 · Document & QC Review Agent Block (C3 Unit, Precord v2).

Serves S5 (document classification and validation) and S7 (QC draft). S6 and S8 are person steps and are
never automated here. The decision is hybrid: file rules and the QC draft are code; the model only
words the answer. The agent drafts for approval and never approves (CHK_02 belongs to a person).

Sources: agent_specifications@row:2; agent_block_actions@row:5; agent_block_actions@row:7;
agent_exception_routes@row:3; agent_exception_routes@row:5; agent_interaction_contracts@row:2;
not_automated_register@row:1; not_automated_register@row:2.
ADK reference: https://github.com/google/adk-python/tree/main/contributing/samples/core/quickstart
"""
from __future__ import annotations

import copy
import datetime
from typing import Any

REQUIREMENT_REFS = (
    "BLK_02",
    "agent_specifications@row:2",
    "agent_block_actions@row:5",
    "agent_block_actions@row:7",
    "agent_exception_routes@row:3",
    "agent_exception_routes@row:5",
    "agent_interaction_contracts@row:2",
    "not_automated_register@row:1",
    "not_automated_register@row:2",
    "standard/runtime.defaults.yaml#guardrails",
)

AGENT_ID = "BLK_02"
AGENT_NAME = "Blk02DocumentQcReviewAgentBlock"
AGENT_VERSION = "1"
PROMPT_VERSION = "prompts/BLK_02.md@1"

MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.0
TIMEOUT_S = 60
MAX_RETRIES = 2
MAX_OUTPUT_TOKENS = 1024
AUTONOMY = "draft_for_approval"
DECISION_TYPE = "hybrid"
MEMORY_MODE = "Session state"
GROUNDING_MODE = "Full-context injection"

SERVES_STEPS = ("S5", "S6", "S7")
FORBIDDEN_STEPS = ("S6", "S8")

TOOLS = ["TOOL_03"]
TOOL_BINDINGS = {"classify_and_validate_documents": "TOOL_03"}

AUDIT_EVENTS = ("agent.decision", "human.review", "guardrail.triggered")

COMPLETION_CONDITIONS = ["Documents classified and validated", "QC draft recommendation generated"]
RESUME_STRATEGY = "Resume from document slot assignment after manual re-upload or override."
FAILURE_BEHAVIOUR = {"text": "Flag unreadable documents or classification ambiguity for human operator inspection."}

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

ACTIONS = {
    "ACT_05": {
        "step_id": "S5",
        "tool_ids": ["TOOL_03"],
        "rule_ids": ["BR-ACT_05"],
        "function": "classify_and_validate_documents_action",
    },
    "ACT_07": {
        "step_id": "S7",
        "tool_ids": ["TOOL_01"],
        "rule_ids": ["BR-ACT_07"],
        "function": "draft_qc_review_action",
    },
}

# (on_success, on_failure) of each action. CHK_02 is a checkpoint, not an action of this agent.
_FLOW = {"ACT_05": ("ACT_07", "EXC_03"), "ACT_07": ("CHK_02", "EXC_05")}

_READS = {
    "ACT_05": ("Profile Photo", "PAN Card", "Aadhaar Front", "Aadhaar Back", "Bank Proof", "Education Document"),
    "ACT_07": ("Application Status", "Uploaded Documents", "KYC Verification Results"),
}
_WRITES = {
    "ACT_05": ("Categorized document slots", "Validation status"),
    "ACT_07": ("Reviewer remark drafts", "Discrepancy recommendation list"),
}

EXCEPTIONS = {
    "EXC_03": {
        "action_id": "ACT_05",
        "escalation_route": "Prospective agent upload interface",
        "resume_from": "ACT_05",
    },
    "EXC_05": {
        "action_id": "ACT_07",
        "escalation_route": "Operations / QC reviewer workbench",
        "resume_from": "ACT_07",
    },
}

INTERACTIONS = {
    "INT_02": {
        "channel": "Operations Work Queue",
        "consent_required": "false",
        "fallback_channel": "Email alert",
    },
}

# The Precord states no extension list and no size limit for BR-ACT_05. Both stay unset (see the report gaps).
PERMITTED_EXTENSIONS: tuple[str, ...] | None = None
MAX_FILE_SIZE_BYTES: int | None = None

# No open item in the register names a field of this agent as blocking.
BLOCKING_OPEN_ITEM_FIELDS: tuple[str, ...] = ()

_RULE_MESSAGES = {
    "BR-ACT_05": "ACT_05 refuses to proceed: File extension permitted; File size within limits",
    "BR-ACT_07": "ACT_07 refuses to proceed: Required verification checks completed",
}

_ENFORCERS = {
    "GR-01": "enforce_gr_01",
    "GR-02": "enforce_gr_02",
    "GR-03": "enforce_gr_03",
    "GR-04": "enforce_gr_04",
    "BR-ACT_05": "enforce_br_act_05",
    "BR-ACT_07": "enforce_br_act_07",
}

GUARDRAILS = {rule_id: {"status": "enforced", "enforced_by": name} for rule_id, name in _ENFORCERS.items()}
_ALL_AGENT_RULES = ("GR-01", "GR-02", "GR-03", "GR-04")


class QcDiscrepancy(Exception):
    """EXC_05 detection: the QC draft found a document anomaly or data mismatch. It carries the draft."""

    def __init__(self, message: str, draft: dict):
        super().__init__(message)
        self.draft = draft


class GuardrailRefusal(Exception):
    """A blocking rule refused the write it guards. The message is the message of the rule."""

    def __init__(self, message: str = "", rule_id: str = ""):
        super().__init__(message)
        self.message = message
        self.rule_id = rule_id


def allowed_step(step: str) -> bool:
    """True only for a step this agent serves that is not a person step."""
    return step in SERVES_STEPS and step not in FORBIDDEN_STEPS


# --- guardrails ---------------------------------------------------------------------------------------------

def enforce_gr_01(case: Any = None, action_id: str | None = None, tool_id: str | None = None) -> None:
    """GR-01: no write outside the tools declared for this agent."""
    if action_id is not None and action_id not in ACTIONS:
        raise GuardrailRefusal(f"GR-01 refuses: {action_id} is not an action of {AGENT_ID}", "GR-01")
    if tool_id is not None and tool_id not in TOOLS:
        raise GuardrailRefusal(f"GR-01 refuses: {tool_id} is not a declared tool of {AGENT_ID}", "GR-01")


def enforce_gr_02(case: Any = None, action_id: str | None = None, step_id: str | None = None) -> None:
    """GR-02: no automation of a step in not_automated or person_steps."""
    if step_id is None and action_id in ACTIONS:
        step_id = ACTIONS[action_id]["step_id"]
    if step_id is not None and not allowed_step(step_id):
        raise GuardrailRefusal(f"GR-02 refuses: step {step_id} is not automated", "GR-02")


def enforce_gr_03(case: Any = None, action_id: str | None = None, writes: Any = None) -> None:
    """GR-03: every blocking rule of the action holds, and the output names only declared writes."""
    if action_id is None:
        return
    if action_id not in ACTIONS:
        raise GuardrailRefusal(f"GR-03 refuses: {action_id} is not an action of {AGENT_ID}", "GR-03")
    for rule_id in ACTIONS[action_id]["rule_ids"]:
        globals()[_ENFORCERS[rule_id]](case)
    if writes is not None:
        extra = sorted(name for name in writes if name not in _WRITES[action_id])
        if extra:
            raise GuardrailRefusal(f"GR-03 refuses: {action_id} may not write {extra}", "GR-03")


def enforce_gr_04(case: Any = None, action_id: str | None = None) -> None:
    """GR-04: escalate, do not decide, when a field of the action sits in a blocking open item.

    The case schema declares no open-item property, so the blocking fields come only from the constant above.
    """
    hit = sorted(
        field
        for field in (*_READS.get(action_id, ()), *_WRITES.get(action_id, ()))
        if field in BLOCKING_OPEN_ITEM_FIELDS
    )
    if hit:
        raise GuardrailRefusal(f"GR-04 refuses: required field {hit} is in an open item; escalate", "GR-04")


def _extension(document: dict) -> str:
    ext = document.get("extension")
    if not ext:
        name = str(document.get("filename") or "")
        ext = name.rsplit(".", 1)[-1] if "." in name else ""
    return str(ext).lower().lstrip(".")


def enforce_br_act_05(case: Any) -> None:
    """BR-ACT_05: file extension permitted; file size within limits. Each document that is present is checked."""
    message = _RULE_MESSAGES["BR-ACT_05"]
    present = {k: case.get(k) for k in _READS["ACT_05"] if isinstance(case, dict) and case.get(k) not in (None, "")}
    if not present:
        raise GuardrailRefusal(message, "BR-ACT_05")
    for document in present.values():
        if not isinstance(document, dict):
            raise GuardrailRefusal(message, "BR-ACT_05")
        ext = _extension(document)
        size = document.get("size_bytes", document.get("size"))
        if not ext or isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise GuardrailRefusal(message, "BR-ACT_05")
        if PERMITTED_EXTENSIONS is not None and ext not in {e.lower().lstrip(".") for e in PERMITTED_EXTENSIONS}:
            raise GuardrailRefusal(message, "BR-ACT_05")
        if MAX_FILE_SIZE_BYTES is not None and size > MAX_FILE_SIZE_BYTES:
            raise GuardrailRefusal(message, "BR-ACT_05")


def enforce_br_act_07(case: Any) -> None:
    """BR-ACT_07: the verification checks the draft depends on are complete."""
    message = _RULE_MESSAGES["BR-ACT_07"]
    for field in _READS["ACT_07"]:
        if not isinstance(case, dict) or case.get(field) in (None, "", [], {}):
            raise GuardrailRefusal(message, "BR-ACT_07")


# --- actions ------------------------------------------------------------------------------------------------

def _view(case: dict, action_id: str) -> dict:
    """Only the fields the action reads."""
    return {k: copy.deepcopy(case[k]) for k in _READS[action_id] if k in case}


def classify_and_validate_documents_action(case: dict, correlation_id: str | None = None) -> dict:
    """ACT_05: classify and validate the uploaded documents through TOOL_03."""
    view = _view(case, "ACT_05")
    enforce_br_act_05(view)
    from integrations.tool_03 import invoke

    enforce_gr_01(case, "ACT_05", "TOOL_03")
    response = invoke(view, correlation_id or str((case or {}).get("case_id") or ""))
    return {name: response.get(name) for name in _WRITES["ACT_05"]}


def draft_qc_review_action(case: dict, correlation_id: str | None = None) -> dict:
    """ACT_07: draft reviewer remarks and a discrepancy list in code. Nothing is approved here."""
    view = _view(case, "ACT_07")
    enforce_br_act_07(view)
    uploaded = view["Uploaded Documents"]
    discrepancies: list[str] = []
    slots = uploaded if isinstance(uploaded, dict) else {}
    for slot in _READS["ACT_05"]:
        if slot not in slots or slots[slot] in (None, ""):
            discrepancies.append(f"Document slot '{slot}' has no uploaded document.")
    # KYC Verification Results has no declared shape, so no KYC mismatch is derived from it (see gaps).
    remarks = [f"Application Status: {view['Application Status']}."]
    remarks.append("Open each uploaded document before you decide; this draft does not replace inspection.")
    remarks.extend(discrepancies or ["No discrepancy found by the automated pre-review."])
    draft = {"Reviewer remark drafts": remarks, "Discrepancy recommendation list": discrepancies}
    if discrepancies:
        # EXC_05 detection: a non-empty discrepancy list goes to the Operations QC exception list.
        # No confidence threshold is declared for H-12, so none is applied.
        raise QcDiscrepancy(f"{len(discrepancies)} discrepancy item(s) found in the QC draft", draft)
    return draft


# --- exceptions, failure, events ----------------------------------------------------------------------------

def _contain_exc_03(case_id: str, error: Any) -> dict:
    return {
        "status_tag": "document_validation_failed",
        "containment": "Reject file upload into categorized slot",
        "human_work_item": "Re-upload valid document in required format",
    }


def _contain_exc_05(case_id: str, error: Any) -> dict:
    return {
        "status_tag": "qc_review_discrepancy",
        "containment": "Route case to Operations QC exception list",
        "human_work_item": "Inspect flagged document discrepancy and approve or reject",
        "draft": copy.deepcopy(getattr(error, "draft", None)),
        "interaction_id": "INT_02",
        "channel": INTERACTIONS["INT_02"]["channel"],
        "fallback_channel": INTERACTIONS["INT_02"]["fallback_channel"],
    }


def handle_exception(exception_id: str, case_id: str, error: Any) -> dict:
    if exception_id == "EXC_03":
        detail = _contain_exc_03(case_id, error)
    elif exception_id == "EXC_05":
        detail = _contain_exc_05(case_id, error)
    else:
        raise KeyError(exception_id)
    route = EXCEPTIONS[exception_id]
    return {
        **detail,
        "exception_id": exception_id,
        "case_id": case_id,
        "error": str(error),
        "escalation_route": route["escalation_route"],
        "resume_from": route["resume_from"],
        "alert": True,
    }


def handle_failure(case_id: str, error: Any) -> dict:
    return {
        "status_tag": "flagged_for_human_inspection",
        "case_id": case_id,
        "error": str(error),
        "escalation_route": "Operations / QC reviewer queue",
        "alert": True,
    }


def emit_event(event_name: str, case_id: str, **fields: Any) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
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


def run_case(case_id: str, case: dict) -> dict:
    working = copy.deepcopy(case)
    trace: list[str] = []
    current = next(iter(ACTIONS))
    last_next = None
    while current in ACTIONS:
        meta = ACTIONS[current]
        on_success, on_failure = _FLOW[current]
        try:
            for rule_id in _ALL_AGENT_RULES:
                globals()[_ENFORCERS[rule_id]](working, current)
            writes = globals()[meta["function"]](working, case_id)
            enforce_gr_03(working, current, writes)
        except Exception as error:  # the case ends here: routed, never retried
            guardrail = (error.rule_id or "guardrail") if isinstance(error, GuardrailRefusal) else ""
            if guardrail:
                emit_event("guardrail.triggered", case_id, step_id=meta["step_id"], status="refused",
                           guardrail_event=guardrail)
            route = handle_exception(on_failure, case_id, error)
            return {"case": working, "trace": trace, "outcome": "routed", "next": None, "route": route}
        working.update(writes)
        trace.append(current)
        emit_event("agent.decision", case_id, step_id=meta["step_id"])
        last_next = on_success
        current = on_success
    return {"case": working, "trace": trace, "outcome": "completed", "next": last_next, "route": None}


# --- ADK ----------------------------------------------------------------------------------------------------

INSTRUCTION = """You are the Document & QC Review Agent Block (BLK_02). You serve S5 (Document Upload) and S7 (Operations QC Review).
You automate document upload classification and file validation, and you prepare a QC draft recommendation for operations review.

Rules you follow:
- Work only on the case you were given, and only through your declared tool, classify_and_validate_documents (TOOL_03).
- Write only the fields your output schema names. A field you cannot fill is reported as unknown, never inferred.
- All arithmetic is deterministic code. Ask for the number.
- Where a value you need is an open item, stop and ask. Do not guess.
- Say what you could not read. A gap reported is a case handled; a gap filled in is a defect nobody can see.

Classify uploaded files into their slots: profile photo, PAN card, Aadhaar front, Aadhaar back, bank proof, education document.
Validate file extension and size. You only draft. You never approve an agent. The Operations / QC reviewer decides at CHK_02.
Never automate S6 (Consent and Declaration: explicit human legal agreement and a second OTP) or S8 (Post-Approval Training and Exam).
When a document is unreadable, corrupted or ambiguous to classify, flag it for human inspection and route it to the Operations / QC reviewer queue.
Reviewers have been seen approving without opening the documents. Put each discrepancy in your draft so that they must open them.

Answer with one JSON object whose keys are only these output fields: (none: the output schema declares no property).
No field is required. No other input field goes in the answer."""


def classify_and_validate_documents(payload: dict, correlation_id: str = "") -> dict:
    """Classify and validate the uploaded documents (TOOL_03)."""
    from integrations.tool_03 import invoke

    enforce_gr_01(None, None, "TOOL_03")
    return invoke(payload, correlation_id)


def make_agent():
    from google.adk.agents import Agent
    from pydantic import create_model
    from solution.adk_model import generate_adk_config, resolve_adk_model

    fields = {name: (Any, None) for name in OUTPUT_SCHEMA["properties"]}
    output_model = create_model("Blk02Output", **fields)
    model = resolve_adk_model(MODEL, max_retries=MAX_RETRIES)
    return Agent(
        name=AGENT_NAME,
        model=model,
        instruction=INSTRUCTION,
        tools=[classify_and_validate_documents],
        output_schema=output_model,
        generate_content_config=generate_adk_config(
            model, MAX_RETRIES, temperature=TEMPERATURE, max_output_tokens=MAX_OUTPUT_TOKENS
        ),
    )
