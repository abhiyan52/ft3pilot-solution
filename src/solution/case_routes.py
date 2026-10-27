"""Case routes. Each write names its author in X-Actor and its source in the body."""
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from solution.cases import CaseStore, UnknownCase, VersionConflict
from solution.masking import mask_cases, mask_fields, mask_history

router = APIRouter()


class NewCase(BaseModel):
    case_id: str


class FieldWrite(BaseModel):
    value: Any
    source: str = "api"
    expected_version: int | None = None


@router.post("/cases", status_code=201)
def create_case(body: NewCase):
    return CaseStore().create_case(body.case_id)


@router.get("/cases")
def list_cases(limit: int = 100, offset: int = 0):
    return {"cases": mask_cases(CaseStore().list_cases(min(max(limit, 1), 500), max(offset, 0)))}


@router.get("/cases/{case_id}")
def read_case(case_id: str):
    try:
        return {"case_id": case_id, "fields": mask_fields(CaseStore().read_case(case_id))}
    except UnknownCase:
        raise HTTPException(404, f"No case {case_id}") from None


@router.put("/cases/{case_id}/fields/{field}")
def write_field(case_id: str, field: str, body: FieldWrite, x_actor: str = Header(default="api")):
    try:
        return CaseStore().write_field(case_id, field, body.value, author=x_actor, source=body.source,
                                       expected_version=body.expected_version)
    except UnknownCase:
        raise HTTPException(404, f"No case {case_id}") from None
    except VersionConflict as error:
        raise HTTPException(409, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.get("/cases/{case_id}/history")
def history(case_id: str, field: str | None = None):
    store = CaseStore()
    try:
        store.read_case(case_id)
    except UnknownCase:
        raise HTTPException(404, f"No case {case_id}") from None
    return {"case_id": case_id, "history": mask_history(store.history(case_id, field))}
