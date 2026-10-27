"""INT_UI5 · SYS_A1 · Document Upload screen (step S5).

Existing client system reached by browser use. The client system is not
reachable in the build, so invoke() raises IntegrationNotConfigured.
"""

REQUIREMENT_REFS = (
    "INT_UI5",
    "handover/sequences.mmd",
)

MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Document Upload screen"
SERVES = "Document Upload step"

FIELD_MAPPING = [
    {"case_field": "", "core_field": "Profile Photo", "required": True},
    {"case_field": "", "core_field": "PAN Card", "required": True},
    {"case_field": "", "core_field": "Aadhaar Front", "required": True},
    {"case_field": "", "core_field": "Aadhaar Back", "required": True},
    {"case_field": "", "core_field": "Bank Proof", "required": True},
    {"case_field": "", "core_field": "Education Document", "required": True},
    {"case_field": "", "core_field": "Categorized document records", "required": True},
    {"case_field": "", "core_field": "Validation status flags", "required": True},
    {"case_field": "", "core_field": "Cropped image assets", "required": True},
]


class IntegrationNotConfigured(RuntimeError):
    """The client system for this integration is not configured in the build."""


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    """Call the Document Upload screen. Never reachable in the build."""
    raise IntegrationNotConfigured(
        "INT_UI5 (SYS_A1, Document Upload screen) is not configured: "
        "the client system is not reachable in the build "
        f"(correlation_id={correlation_id})"
    )
