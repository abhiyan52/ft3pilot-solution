"""MOCK for TOOL_02, the external KYC verification service (ACT_02).

The Precord has no tools.yaml entry for this tool. Open item
HR-201:BLK_01:TOOL_02 carries it. This module opens no network connection and
reads no credential. It blocks promotion.
"""

REQUIREMENT_REFS = ("TOOL_02", "agent_block_actions@ACT_02")

IS_MOCK = True

OPEN_ITEMS = ("HR-201:BLK_01:TOOL_02",)

DEFAULT_ASSUMPTION = "Stub the tool on sample data until it exists"

ENDPOINT = "__MOCK__"

# Request fields (reads of ACT_02): PAN Number, Aadhaar Number, CKYC Number.
# sample_data holds no rows, so each response value is the string "sample".
_RESPONSE = {
    "KYC verification status": "sample",
}


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    """Return the canned KYC response. No network, no credential."""
    return dict(_RESPONSE)
