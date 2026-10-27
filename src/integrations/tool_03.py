"""MOCK for TOOL_03 (document classification and validation, step S5 / ACT_05).

The Precord provides no tools.yaml entry for TOOL_03. Open item
HR-201:BLK_02:TOOL_03 carries it. This module opens no network connection and
reads no credential. It blocks promotion.
"""

REQUIREMENT_REFS = ("TOOL_03", "agent_block_actions@ACT_05:TOOL_03")
IS_MOCK = True
OPEN_ITEMS = ("HR-201:BLK_02:TOOL_03",)
DEFAULT_ASSUMPTION = "Stub the tool on sample data until it exists"
ENDPOINT = "__MOCK__"

REQUEST_FIELDS = (
    "Profile Photo",
    "PAN Card",
    "Aadhaar Front",
    "Aadhaar Back",
    "Bank Proof",
    "Education Document",
)
RESPONSE_FIELDS = ("Categorized document slots", "Validation status")

# sample_data holds no row for these fields, so each takes the literal "sample".
_SAMPLE = {field: "sample" for field in RESPONSE_FIELDS}


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    """Return the canned response. No I/O; endpoint and credential are ignored."""
    return dict(_SAMPLE)
