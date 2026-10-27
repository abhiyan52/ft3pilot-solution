"""INT_UI4 · Bank Details Entry screen on SYS_A1 (step S4).

Existing client system, reached by browser use. The Precord declares no
tools.yaml entry for it and the client system is not reachable in the build,
so invoke() raises IntegrationNotConfigured. No browser path is built.
"""

REQUIREMENT_REFS = ("INT_UI4", "handover/sequences.mmd")

MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Bank Details Entry screen"
SERVES = "Bank Details Entry step"

FIELD_MAPPING = [
    {"case_field": "", "core_field": "Account Type", "required": True},
    {"case_field": "", "core_field": "Name As In Bank Account", "required": True},
    {"case_field": "", "core_field": "Bank Account Number", "required": True},
    {"case_field": "", "core_field": "IFSC Code", "required": True},
    {"case_field": "", "core_field": "Bank Name", "required": True},
    {"case_field": "", "core_field": "Bank City", "required": True},
    {"case_field": "", "core_field": "Branch Name", "required": True},
    {"case_field": "", "core_field": "Bank verification submission payload", "required": True},
]


class IntegrationNotConfigured(RuntimeError):
    """The client system behind this integration is not configured in the build."""


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    raise IntegrationNotConfigured(
        f"INT_UI4 ({ENDPOINT} on SYS_A1) is not configured: "
        f"the client system is not reachable in the build "
        f"(correlation_id={correlation_id})"
    )
