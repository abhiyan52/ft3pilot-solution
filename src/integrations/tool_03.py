"""MOCK of TOOL_03, which the Precord does not yet provide. It blocks promotion.

spec/tools.yaml has no TOOL_03 entry. Open item HR-201:BLK_02:TOOL_03 carries it, and this module
implements that item's default assumption only. It opens no connection and reads no credential.
"""
from __future__ import annotations

from typing import Any


REQUIREMENT_REFS = (
    "TOOL_03",
    "open_items@HR-201:BLK_02:TOOL_03",
    "agent_block_actions@row:5#ACT_05",
)
IS_MOCK = True
OPEN_ITEMS = ("HR-201:BLK_02:TOOL_03",)
DEFAULT_ASSUMPTION = "Stub the tool on sample data until it exists"
ENDPOINT = "__MOCK__"

# Request fields are the reads of ACT_05; response fields are its writes (agent_block_actions@row:5).
REQUEST_FIELDS = (
    "Profile Photo",
    "PAN Card",
    "Aadhaar Front",
    "Aadhaar Back",
    "Bank Proof",
    "Education Document",
)
RESPONSE_FIELDS = (
    "Categorized document slots",
    "Validation status",
)

# context/sample_data.csv holds no rows, so there is nothing to seed a response with.
SAMPLE_ROWS: tuple[dict[str, Any], ...] = ()


def invoke(payload: dict[str, Any], correlation_id: str, *, endpoint: str | None = None,
           credential: str | None = None) -> dict[str, Any]:
    """Return the ACT_05 response fields from sample data. A field with no sample value is None (unknown)."""
    if not isinstance(payload, dict):
        raise TypeError("TOOL_03 payload must be a dict")
    if not correlation_id:
        raise ValueError("TOOL_03 requires a correlation ID")
    unknown = sorted(set(payload) - set(REQUEST_FIELDS))
    if unknown:
        raise ValueError(f"TOOL_03 payload has fields no action names: {unknown}")
    row = SAMPLE_ROWS[0] if SAMPLE_ROWS else {}
    return {field: row.get(field) for field in RESPONSE_FIELDS}
