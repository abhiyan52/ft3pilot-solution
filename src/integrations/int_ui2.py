"""INT_UI2 on SYS_A1: User Verification screen (step S2).

Mapped row from integration_map.yaml. Browser use, existing client system.
The client system is not reachable in the build, so invoke() raises.
"""

REQUIREMENT_REFS = ("INT_UI2", "handover/sequences.mmd")

MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "User Verification screen"

FIELD_MAPPING = [
    {"case_field": "", "core_field": "PAN Number", "required": True},
    {"case_field": "", "core_field": "Aadhaar Number", "required": True},
    {"case_field": "", "core_field": "CKYC Number", "required": True},
    {"case_field": "", "core_field": "External KYC service response", "required": True},
    {"case_field": "", "core_field": "KYC verification status", "required": True},
    {"case_field": "", "core_field": "System retry queue entry", "required": True},
]

SERVES = "User Verification step"


class IntegrationNotConfiguredError(RuntimeError):
    """The client system behind this integration is not configured in the build."""


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    raise IntegrationNotConfiguredError(
        "INT_UI2 (SYS_A1, User Verification screen) is not configured: "
        "the client system is not reachable in the build"
    )
