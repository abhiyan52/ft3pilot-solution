"""Labelled mock of TOOL_02, the external KYC verification tool (ACT_02, step S2).

TOOL_02 has no tools.yaml entry. Open item HR-201:BLK_01:TOOL_02 carries it, and its default assumption is to stub
the tool on sample data until it exists. This module does that and nothing more. It opens no network connection,
reads no credential and calls no real system. IS_MOCK blocks promotion.

Request fields are the reads of ACT_02 (agent_block_actions@row:2). The response field is its write. The Precord
ships no sample data, so SAMPLE_ROWS is empty and the response reports the status as unknown (None), never inferred."""
from typing import Any

REQUIREMENT_REFS = ("TOOL_02", "agent_block_actions@row:2", "open_items:HR-201:BLK_01:TOOL_02")
IS_MOCK = True
OPEN_ITEMS = ("HR-201:BLK_01:TOOL_02",)
DEFAULT_ASSUMPTION = "Stub the tool on sample data until it exists"
ENDPOINT = "__MOCK__"

REQUEST_FIELDS = ("PAN Number", "Aadhaar Number", "CKYC Number")
RESPONSE_FIELDS = ("KYC verification status",)

# Rows of context/sample_data.csv for this tool. The Precord ships none.
SAMPLE_ROWS: tuple[dict[str, Any], ...] = ()


def _matches(row: dict[str, Any], request: dict[str, Any]) -> bool:
    keys = [field for field in REQUEST_FIELDS if row.get(field) not in (None, "")]
    return bool(keys) and all(row.get(field) == request.get(field) for field in keys)


def invoke(payload: dict[str, Any], correlation_id: str, *, endpoint: str | None = None,
           credential: Any = None) -> dict[str, Any]:
    """Answer one KYC query from SAMPLE_ROWS. `endpoint` and `credential` are accepted and ignored: a mock calls nothing."""
    payload = payload if isinstance(payload, dict) else {}
    request = {field: payload.get(field) for field in REQUEST_FIELDS}
    row = next((r for r in SAMPLE_ROWS if _matches(r, request)), None)
    response = {field: (row.get(field) if row else None) for field in RESPONSE_FIELDS}
    return {
        "tool_id": "TOOL_02",
        "mock": IS_MOCK,
        "endpoint": ENDPOINT,
        "correlation_id": correlation_id,
        "assumption": DEFAULT_ASSUMPTION,
        "open_items": list(OPEN_ITEMS),
        "request": request,
        "seeded": row is not None,
        **response,
    }
