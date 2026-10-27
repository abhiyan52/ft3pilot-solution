"""INT_UI3 on SYS_A1: Profile Details Entry screen (browser use, existing client system).

Source: integration_map@INT_UI3 (step S3, agent BLK_01).
The client system is not reachable in the build. invoke() raises.
"""

REQUIREMENT_REFS = ("INT_UI3", "handover/sequences.mmd")

MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Profile Details Entry screen"

FIELD_MAPPING = [
    {"case_field": "", "core_field": "Name", "required": True},
    {"case_field": "", "core_field": "Gender", "required": True},
    {"case_field": "", "core_field": "Date of Birth", "required": True},
    {"case_field": "", "core_field": "Marital Status", "required": True},
    {"case_field": "", "core_field": "Address", "required": True},
    {"case_field": "", "core_field": "Pincode", "required": True},
    {"case_field": "", "core_field": "City", "required": True},
    {"case_field": "", "core_field": "State", "required": True},
]

SERVES = "Profile Details Entry step"


class IntegrationNotConfigured(RuntimeError):
    """The client system behind INT_UI3 is not configured in this build."""


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    raise IntegrationNotConfigured(
        "INT_UI3 (SYS_A1, Profile Details Entry screen) is not configured: "
        "the client system is not reachable in the build "
        f"(correlation_id={correlation_id})"
    )
