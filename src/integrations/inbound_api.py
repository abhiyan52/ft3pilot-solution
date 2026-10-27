"""Inbound API of the Solution: the endpoints that spec/inbound_api.yaml declares.

A case enters through the orchestrator (enter_case), never through a named agent. Case data goes through
solution.cases.CaseStore only. The HIL endpoints serve the C5 checkpoint store, which this module never
imports at load time. Auth values are not checked here: no identity provider is configured.
"""
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

REQUIREMENT_REFS = (
    "spec/inbound_api.yaml",
    "EP-06",
    "EP-01",
    "EP-02",
    "EP-03",
    "EP-04",
    "handover/sequences.mmd",
)

TRIGGER_KIND = "Inbound channel message"

ENDPOINTS = [
    {
        "auth": "HMAC signature",
        "endpoint_id": "EP-06",
        "error_actions": {
            "401": "Refresh token, retry once",
            "403": "Park case · alert Platform support",
            "404": "Route to manual verification",
            "409": "Duplicate · return existing case",
            "422": "Reject with validation report",
            "429": "Backoff 2ⁿ s, max 5",
            "5xx": "Retry ×3, then degrade to human",
            "timeout": "Retry ×2, then route to review"
        },
        "hil": False,
        "idempotency": None,
        "method": "POST",
        "path": "/v1/callbacks/sys-a1",
        "rate_limit": "20 req/s",
        "request_example": {
            "case_id": "c-CASE-0001",
            "status": "completed"
        },
        "summary": "Status callback registered by the core system.",
        "tags": [
            "Solution-provided"
        ],
        "timeout": "5 s"
    },
    {
        "auth": "OAuth2 client credentials",
        "endpoint_id": "EP-01",
        "error_actions": {
            "401": "Refresh token, retry once",
            "403": "Park case · alert Platform support",
            "404": "Route to manual verification",
            "409": "Duplicate · return existing case",
            "422": "Reject with validation report",
            "429": "Backoff 2ⁿ s, max 5",
            "5xx": "Retry ×3, then degrade to human",
            "timeout": "Retry ×2, then route to review"
        },
        "hil": False,
        "idempotency": "Idempotency-Key header (case reference)",
        "method": "POST",
        "path": "/v1/cases",
        "rate_limit": "50 req/s",
        "request_example": {
            "case_reference": "CASE-0001",
            "channel": "core_system",
            "documents": []
        },
        "summary": "Inbound trigger. The core system submits a case for processing.",
        "tags": [
            "Solution-provided"
        ],
        "timeout": "5 s"
    },
    {
        "auth": "OAuth2 client credentials",
        "endpoint_id": "EP-02",
        "error_actions": {
            "401": "Refresh token, retry once",
            "403": "Park case · alert Platform support",
            "404": "Route to manual verification",
            "409": "Duplicate · return existing case",
            "422": "Reject with validation report",
            "429": "Backoff 2ⁿ s, max 5",
            "5xx": "Retry ×3, then degrade to human",
            "timeout": "Retry ×2, then route to review"
        },
        "hil": False,
        "idempotency": None,
        "method": "GET",
        "path": "/v1/cases/{case_id}/status",
        "rate_limit": "100 req/s",
        "request_example": None,
        "summary": "Case status for the core system and the client UI.",
        "tags": [
            "Solution-provided"
        ],
        "timeout": "2 s"
    },
    {
        "auth": "OAuth2 client credentials",
        "endpoint_id": "EP-03",
        "error_actions": {
            "401": "Refresh token, retry once",
            "403": "Park case · alert Platform support",
            "404": "Route to manual verification",
            "409": "Duplicate · return existing case",
            "422": "Reject with validation report",
            "429": "Backoff 2ⁿ s, max 5",
            "5xx": "Retry ×3, then degrade to human",
            "timeout": "Retry ×2, then route to review"
        },
        "hil": True,
        "idempotency": None,
        "method": "GET",
        "path": "/v1/hil/tasks",
        "rate_limit": "20 req/s",
        "request_example": None,
        "summary": "HIL API. Open review tasks, for surfaces the client builds.",
        "tags": [
            "Solution-provided"
        ],
        "timeout": "2 s"
    },
    {
        "auth": "OAuth2 client credentials",
        "endpoint_id": "EP-04",
        "error_actions": {
            "401": "Refresh token, retry once",
            "403": "Park case · alert Platform support",
            "404": "Route to manual verification",
            "409": "Duplicate · return existing case",
            "422": "Reject with validation report",
            "429": "Backoff 2ⁿ s, max 5",
            "5xx": "Retry ×3, then degrade to human",
            "timeout": "Retry ×2, then route to review"
        },
        "hil": True,
        "idempotency": "Idempotency-Key header (task_id)",
        "method": "POST",
        "path": "/v1/hil/tasks/{task_id}/decision",
        "rate_limit": "20 req/s",
        "request_example": {
            "action": "approve",
            "corrected": {},
            "reason_code": "",
            "reviewer": ""
        },
        "summary": "HIL API. A reviewer decision; resumes the case.",
        "tags": [
            "Solution-provided"
        ],
        "timeout": "5 s"
    }
]


router = APIRouter()


def case_store():
    from solution.cases import CaseStore
    return CaseStore()


def _endpoint(endpoint_id: str) -> dict[str, Any]:
    return next(entry for entry in ENDPOINTS if entry["endpoint_id"] == endpoint_id)


def error_response(endpoint_id: str, code: str, detail: str) -> JSONResponse:
    actions = _endpoint(endpoint_id)["error_actions"]
    key = "5xx" if code.startswith("5") else code
    return JSONResponse(status_code=int(code), content={"error": code, "action": actions.get(key), "detail": detail})


async def _json_body(request: Request) -> Any:
    """The parsed JSON body, or None when it is not valid JSON."""
    try:
        return await request.json()
    except ValueError:
        return None


def _idempotency_key(endpoint_id: str, request: Request) -> str | None:
    if not _endpoint(endpoint_id)["idempotency"]:
        return None
    return request.headers.get("Idempotency-Key") or None


async def status_callback(request: Request):
    body = await _json_body(request)
    if not isinstance(body, dict) or not isinstance(body.get("case_id"), str) or not isinstance(body.get("status"), str):
        return error_response("EP-06", "422", "The body must be a JSON object with a text case_id and a text status")
    try:
        case_store().read_case(body["case_id"])
    except LookupError:
        return error_response("EP-06", "404", f"Unknown case {body['case_id']}")
    # The case schema declares no status field, so write_field would refuse it. Nothing is stored.
    return {"case_id": body["case_id"], "status": "received"}


async def submit_case(request: Request):
    key = _idempotency_key("EP-01", request)
    if not key:
        return error_response("EP-01", "422", "The Idempotency-Key header is required")
    payload = await _json_body(request)
    if not isinstance(payload, dict):
        return error_response("EP-01", "422", "The body must be a JSON object")
    case_id = "c-" + key
    response = {"case_id": case_id, "status": "received", "correlation_id": case_id}
    from solution.state import StateStore
    entries = StateStore("case_entries")
    store = case_store()
    # A case counts as existing once its entry is recorded. A case row with no entry is a run that failed part
    # way, so a retry with the same key runs it again (create_case is idempotent).
    try:
        store.read_case(case_id)
        if entries.get(case_id) is not None:
            return response  # 409 action: duplicate, return the existing case
    except LookupError:
        pass
    store.create_case(case_id)
    from solution.agent_runtime import enter_case
    try:
        result = await enter_case("", payload, correlation_id=case_id, trigger_kind=TRIGGER_KIND)
    except ValueError as error:
        return error_response("EP-01", "422", str(error))
    except Exception as error:
        return error_response("EP-01", "500", f"The case could not be run: {error}")
    entries.put(case_id, result["entry"])
    return response


async def case_status(case_id: str):
    try:
        fields = case_store().read_case(case_id)
    except LookupError:
        return error_response("EP-02", "404", f"Unknown case {case_id}")
    return {"case_id": case_id, "fields": fields}


def _hil_store():
    """The shared checkpoint store, or None when checkpoints.service is absent."""
    try:
        from solution.tool_policy import checkpoint_store
        return checkpoint_store()
    except ImportError:
        return None


def _hil_absent(endpoint_id: str) -> JSONResponse:
    return error_response(endpoint_id, "503", "The HIL store is not built: checkpoints.service is absent")


def _field(item: Any, *names: str) -> Any:
    for name in names:
        value = item.get(name) if isinstance(item, dict) else getattr(item, name, None)
        if value is not None:
            return value
    return ""


async def hil_tasks(request: Request):
    store = _hil_store()
    if store is None:
        return _hil_absent("EP-03")
    tasks = [{"task_id": "t-" + str(_field(item, "case_id")),
              "checkpoint": _field(item, "checkpoint_id", "checkpoint"), "sla_due": ""}
             for item in store.pending()]
    return {"tasks": tasks}


async def hil_decision(task_id: str, request: Request):
    key = _idempotency_key("EP-04", request)
    if not key:
        return error_response("EP-04", "422", "The Idempotency-Key header is required")
    body = await _json_body(request)
    if not isinstance(body, dict) or not isinstance(body.get("action"), str) or not body["action"]:
        return error_response("EP-04", "422", "The body must be a JSON object with a text action")
    corrected = body.get("corrected") or {}
    if not isinstance(corrected, dict):
        return error_response("EP-04", "422", "corrected must be a JSON object")
    store = _hil_store()
    if store is None:
        return _hil_absent("EP-04")
    from solution.state import StateStore
    seen = StateStore("inbound_idempotency")
    first = seen.get("EP-04:" + key)
    if first is not None:
        return first
    case_id = task_id.removeprefix("t-")
    try:
        version = _field(store.read(case_id), "version")
        applied = store.apply(case_id, version, body["action"], patch=corrected,
                              actor=str(body.get("reviewer") or ""), reason=str(body.get("reason_code") or ""))
    except LookupError:
        return error_response("EP-04", "404", f"Unknown task {task_id}")
    except ValueError as error:
        return error_response("EP-04", "422", str(error))
    response = {"task_id": task_id, "status": "decided", "case_version": _field(applied, "version") or version}
    seen.put("EP-04:" + key, response)
    return response


_HANDLERS = {
    "EP-06": status_callback,
    "EP-01": submit_case,
    "EP-02": case_status,
    "EP-03": hil_tasks,
    "EP-04": hil_decision,
}

for _entry in ENDPOINTS:
    router.add_api_route(_entry["path"], _HANDLERS[_entry["endpoint_id"]], methods=[_entry["method"]],
                         summary=_entry["summary"], tags=_entry["tags"])
