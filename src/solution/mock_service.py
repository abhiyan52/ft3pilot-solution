"""Host the mocks of the declared tools (D-3 to D-5). The served Solution calls its own mocks.

Each mock answers with a stub that fits the response schema of its tool. `/__MOCKS__` lists every
mock with what it assumes, so a person knows what is not the real system."""
import os
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from solution.playground_paths import precord

router = APIRouter()


def _mocks() -> list[dict[str, Any]]:
    # BUG-109: a missing or broken data file raises. It never gives an empty list that looks like "no mocks".
    return list(precord().get("files", {}).get("mocks", []))


def _register(mock: dict[str, Any]) -> None:
    @router.api_route(mock["path"], methods=[mock["method"]], name=f"mock_{mock['tool_id']}")
    async def answer(request: Request) -> JSONResponse:
        # Read the body so a client that streams it does not hang.
        await request.body()
        return JSONResponse(mock["response"], headers={"X-Mock": "true", "X-Mock-Tool": mock["tool_id"]})


for _mock in _mocks():
    _register(_mock)


def _request() -> dict[str, Any]:
    request = precord().get("files", {}).get("informationRequest") or {}
    return {"schema_version": request.get("schema_version"), "content_hash": request.get("content_hash")}


@router.get("/__MOCKS__")
def listing() -> dict[str, Any]:
    shown = [{key: value for key, value in mock.items() if key != "response"} for mock in _mocks()]
    # D-5: the versioned request lets a person see that a request repeats an earlier one.
    return {"mocks": shown, "mock_base": os.environ.get("SOLUTION_MOCK_BASE", ""), "information_request": _request()}
