"""Inbound API of the Solution (spec/inbound_api.yaml, EP-01 to EP-04 and EP-06).

Every route here is one that the Solution serves. EP-05 (INT_API1) and EP-07 (INT_DB1) are calls the Solution makes to
SYS_A1; they live in their mapped Units and get no route. A case enters through the orchestrator: EP-01 calls
`solution.agent_runtime.enter_case` with a blank agent_id and the trigger kind that orchestration.yaml declares, and
names no agent. The HIL routes read the C5 checkpoint store through `solution.tool_policy.checkpoint_store()`, imported
inside each handler because C3 builds before C5.

Auth is not checked here. EP-01 to EP-04 declare OAuth2 client credentials and EP-06 an HMAC signature; no identity
provider or signing secret is configured, so this is a gap. Rate limits and timeouts are copied, not enforced.
No Precord file gives a request or response schema for any endpoint: a body is refused only when it is not JSON or not
a JSON object, and the HIL decision is checked against the decisions that spec/checkpoints.yaml declares."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

REQUIREMENT_REFS: tuple[str, ...] = (
    "spec/inbound_api.yaml",
    "EP-06",
    "EP-01",
    "EP-02",
    "EP-03",
    "EP-04",
    "handover/sequences.mmd",
)

_ERROR_ACTIONS: dict[str, str] = {
    "401": "Refresh token, retry once",
    "403": "Park case · alert Platform support",
    "404": "Route to manual verification",
    "409": "Duplicate · return existing case",
    "422": "Reject with validation report",
    "429": "Backoff 2ⁿ s, max 5",
    "5xx": "Retry ×3, then degrade to human",
    "timeout": "Retry ×2, then route to review",
}

# Copied from spec/inbound_api.yaml, in the order the Precord lists them.
ENDPOINTS: list[dict[str, Any]] = [
    {
        "auth": "HMAC signature",
        "endpoint_id": "EP-06",
        "error_actions": dict(_ERROR_ACTIONS),
        "hil": False,
        "idempotency": None,
        "method": "POST",
        "path": "/v1/callbacks/sys-a1",
        "rate_limit": "20 req/s",
        "request_example": {"case_id": "c-CASE-0001", "status": "completed"},
        "summary": "Status callback registered by the core system.",
        "tags": ["Solution-provided"],
        "timeout": "5 s",
    },
    {
        "auth": "OAuth2 client credentials",
        "endpoint_id": "EP-01",
        "error_actions": dict(_ERROR_ACTIONS),
        "hil": False,
        "idempotency": "Idempotency-Key header (case reference)",
        "method": "POST",
        "path": "/v1/cases",
        "rate_limit": "50 req/s",
        "request_example": {"case_reference": "CASE-0001", "channel": "core_system", "documents": []},
        "summary": "Inbound trigger. The core system submits a case for processing.",
        "tags": ["Solution-provided"],
        "timeout": "5 s",
    },
    {
        "auth": "OAuth2 client credentials",
        "endpoint_id": "EP-02",
        "error_actions": dict(_ERROR_ACTIONS),
        "hil": False,
        "idempotency": None,
        "method": "GET",
        "path": "/v1/cases/{case_id}/status",
        "rate_limit": "100 req/s",
        "request_example": None,
        "summary": "Case status for the core system and the client UI.",
        "tags": ["Solution-provided"],
        "timeout": "2 s",
    },
    {
        "auth": "OAuth2 client credentials",
        "endpoint_id": "EP-03",
        "error_actions": dict(_ERROR_ACTIONS),
        "hil": True,
        "idempotency": None,
        "method": "GET",
        "path": "/v1/hil/tasks",
        "rate_limit": "20 req/s",
        "request_example": None,
        "summary": "HIL API. Open review tasks, for surfaces the client builds.",
        "tags": ["Solution-provided"],
        "timeout": "2 s",
    },
    {
        "auth": "OAuth2 client credentials",
        "endpoint_id": "EP-04",
        "error_actions": dict(_ERROR_ACTIONS),
        "hil": True,
        "idempotency": "Idempotency-Key header (task_id)",
        "method": "POST",
        "path": "/v1/hil/tasks/{task_id}/decision",
        "rate_limit": "20 req/s",
        "request_example": {"action": "approve", "corrected": {}, "reason_code": "", "reviewer": ""},
        "summary": "HIL API. A reviewer decision; resumes the case.",
        "tags": ["Solution-provided"],
        "timeout": "5 s",
    },
]

ENDPOINTS_BY_ID: dict[str, dict[str, Any]] = {endpoint["endpoint_id"]: endpoint for endpoint in ENDPOINTS}

# orchestration.yaml triggers: EP-01 is the inbound trigger, and this is the one kind the Precord declares.
TRIGGER_KIND = "Inbound channel message"

# spec/checkpoints.yaml decisions[].action. A decision outside its checkpoint's list is refused.
CHECKPOINT_DECISIONS: dict[str, tuple[str, ...]] = {
    "CHK_01": ("Confirm and proceed", "Edit details"),
    "CHK_02": ("Approve agent", "Raise discrepancy", "Reject"),
}

HIL_NOT_BUILT = "The HIL store is not built: checkpoints.service is absent"
TASK_PREFIX = "t-"
CASE_PREFIX = "c-"

router = APIRouter()


def case_store() -> Any:
    """A fresh CaseStore on every call. No handler keeps it."""
    from solution.cases import CaseStore
    return CaseStore()


def error_response(endpoint_id: str, code: str, detail: str) -> JSONResponse:
    """The one error shape: the status of the code and the action that the endpoint's error_actions names for it."""
    actions = ENDPOINTS_BY_ID[endpoint_id]["error_actions"]
    action = actions.get(code)
    if action is None and code.isdigit() and code.startswith("5"):
        action = actions["5xx"]
    if action is None:
        raise KeyError(f"{endpoint_id} declares no error action for {code}")
    return JSONResponse(status_code=int(code), content={"error": code, "action": action, "detail": detail})


async def read_body(request: Request) -> dict[str, Any] | None:
    """The JSON object in the body, or None when the body is not JSON or not an object."""
    try:
        body = json.loads(await request.body())
    except (ValueError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


def received(case_id: str) -> dict[str, Any]:
    return {"case_id": case_id, "status": "received", "correlation_id": case_id}


@router.post(ENDPOINTS_BY_ID["EP-06"]["path"])
async def status_callback(request: Request) -> Any:
    """EP-06. The case schema names no field for a callback status, so the callback goes to the state store."""
    endpoint = ENDPOINTS_BY_ID["EP-06"]
    body = await read_body(request)
    if body is None:
        return error_response(endpoint["endpoint_id"], "422", "The body is not a JSON object")
    case_id = body.get("case_id")
    if not isinstance(case_id, str) or not case_id:
        return error_response(endpoint["endpoint_id"], "422", "case_id is required and must be text")
    try:
        case_store().read_case(case_id)
    except LookupError:
        return error_response(endpoint["endpoint_id"], "404", f"No case {case_id}")
    from solution.state import StateStore
    StateStore("case_callbacks").put(case_id, body)
    return received(case_id)


@router.post(ENDPOINTS_BY_ID["EP-01"]["path"])
async def submit_case(request: Request) -> Any:
    """EP-01, the inbound trigger. A repeated Idempotency-Key gives the existing case and runs nothing (409 action)."""
    endpoint = ENDPOINTS_BY_ID["EP-01"]
    body = await read_body(request)
    if body is None:
        return error_response(endpoint["endpoint_id"], "422", "The body is not a JSON object")
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        return error_response(endpoint["endpoint_id"], "422", "The Idempotency-Key header (case reference) is required")
    case_id = CASE_PREFIX + key
    store = case_store()
    try:
        store.read_case(case_id)
    except LookupError:
        pass
    else:
        return received(case_id)
    store.create_case(case_id)
    from solution.agent_runtime import enter_case
    result = await enter_case("", body, correlation_id=case_id, trigger_kind=TRIGGER_KIND)
    from solution.state import StateStore
    StateStore("case_entries").put(case_id, result["entry"])
    return received(case_id)


@router.get(ENDPOINTS_BY_ID["EP-02"]["path"])
async def case_status(case_id: str) -> Any:
    """EP-02. The Precord declares no status enum, so this gives the case fields and invents no status value."""
    endpoint = ENDPOINTS_BY_ID["EP-02"]
    try:
        fields = case_store().read_case(case_id)
    except LookupError:
        return error_response(endpoint["endpoint_id"], "404", f"No case {case_id}")
    return {"case_id": case_id, "case": fields}


def hil_store(endpoint_id: str) -> tuple[Any, JSONResponse | None]:
    """The one shared CheckpointStore, or a 503 when C5 has not built checkpoints.service."""
    try:
        from solution.tool_policy import checkpoint_store
        return checkpoint_store(), None
    except ImportError:
        return None, error_response(endpoint_id, "503", HIL_NOT_BUILT)


@router.get(ENDPOINTS_BY_ID["EP-03"]["path"])
async def hil_tasks() -> Any:
    """EP-03. The checkpoint declares no SLA clock start, so sla_due stays blank."""
    store, failure = hil_store(ENDPOINTS_BY_ID["EP-03"]["endpoint_id"])
    if failure is not None:
        return failure
    tasks = [{"task_id": TASK_PREFIX + str(item["case_id"]),
              "checkpoint": item.get("checkpoint_id", item.get("checkpoint")),
              "sla_due": ""}
             for item in store.pending()]
    return {"tasks": tasks}


@router.post(ENDPOINTS_BY_ID["EP-04"]["path"])
async def hil_decision(task_id: str, request: Request) -> Any:
    """EP-04. A repeated Idempotency-Key gives the first response and applies nothing. Without the C5 store every
    decision gives 503, whatever the task or body, so the store is checked first."""
    endpoint = ENDPOINTS_BY_ID["EP-04"]
    endpoint_id = endpoint["endpoint_id"]
    store, failure = hil_store(endpoint_id)
    if failure is not None:
        return failure
    body = await read_body(request)
    if body is None:
        return error_response(endpoint_id, "422", "The body is not a JSON object")
    action = body.get("action")
    corrected = body.get("corrected", {})
    reviewer = body.get("reviewer", "")
    reason_code = body.get("reason_code", "")
    if not isinstance(action, str) or not action:
        return error_response(endpoint_id, "422", "action is required and must be text")
    if not isinstance(corrected, dict):
        return error_response(endpoint_id, "422", "corrected must be a JSON object")
    if not isinstance(reviewer, str) or not isinstance(reason_code, str):
        return error_response(endpoint_id, "422", "reviewer and reason_code must be text")
    if not task_id.startswith(TASK_PREFIX):
        return error_response(endpoint_id, "404", f"No task {task_id}")
    case_id = task_id[len(TASK_PREFIX):]
    key =request.headers.get("Idempotency-Key", "").strip() or task_id
    from solution.state import StateStore
    decided = StateStore("hil_decisions")
    first = decided.get(key)
    if first is not None:
        return first
    try:
        record = store.read(case_id)
    except LookupError:
        return error_response(endpoint_id, "404", f"No open task {task_id}")
    if not isinstance(record, dict):
        return error_response(endpoint_id, "404", f"No open task {task_id}")
    allowed = CHECKPOINT_DECISIONS.get(str(record.get("checkpoint_id", "")))
    if allowed is not None and action not in allowed:
        return error_response(endpoint_id, "422", f"{action!r} is not a decision of {record['checkpoint_id']}: "
                                                  f"{', '.join(allowed)}")
    version = record.get("version")
    try:
        applied = store.apply(case_id, version, action, patch=corrected, actor=reviewer, reason=reason_code)
    except LookupError:
        return error_response(endpoint_id, "404", f"No open task {task_id}")
    except ValueError as error:
        return error_response(endpoint_id, "422", str(error))
    case_version = applied.get("version", version) if isinstance(applied, dict) else version
    response = {"task_id": task_id, "status": "decided", "case_version": case_version}
    decided.put(key, response)
    return response
