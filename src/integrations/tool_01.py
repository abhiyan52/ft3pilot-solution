"""MOCK for TOOL_01. No tools.yaml entry exists; open item HR-201:BLK_01:TOOL_01 carries it.

Serves ACT_01, ACT_03 and ACT_04 of BLK_01. Blocks promotion. Opens no connection and reads no credential.
"""

REQUIREMENT_REFS = ("TOOL_01",)
IS_MOCK = True
OPEN_ITEMS = ("HR-201:BLK_01:TOOL_01",)
DEFAULT_ASSUMPTION = "Stub the tool on sample data until it exists"
ENDPOINT = "__MOCK__"

# Request fields: the reads of ACT_01, ACT_03 and ACT_04.
REQUEST_FIELDS = (
    "Full Name",
    "Mobile Number",
    "Email",
    "RM Business Code",
    "Name",
    "Gender",
    "Date of Birth",
    "Address",
    "Pincode",
    "IFSC Code",
    "Bank Account Number",
    "Name As In Bank Account",
)

# Response fields: the writes of the same actions. sample_data holds no row for
# any of them, so each takes the literal "sample".
RESPONSE_FIELDS = (
    "Application record draft",
    "Agent profile update",
    "Bank Name",
    "Bank City",
    "Branch Name",
    "Bank verification status",
)

_SAMPLE = {field: "sample" for field in RESPONSE_FIELDS}


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    """Return the flat sample response. Never calls a real system."""
    return dict(_SAMPLE)
