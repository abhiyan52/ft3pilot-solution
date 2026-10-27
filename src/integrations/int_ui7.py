"""INT_UI7 on SYS_A1: Operations QC Review screen (browser use, existing system).

The client system is not reachable in the build. invoke() raises
IntegrationNotConfigured. No browser path is built and no network is opened.
"""

REQUIREMENT_REFS = ("INT_UI7", "handover/sequences.mmd")

MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Operations QC Review screen"

FIELD_MAPPING = [
    {"case_field": "", "core_field": "Application Status", "required": True},
    {"case_field": "", "core_field": "Agent Type", "required": True},
    {"case_field": "", "core_field": "Uploaded Documents", "required": True},
    {"case_field": "", "core_field": "KYC Verification Results", "required": True},
    {"case_field": "", "core_field": "Reviewer remark drafts", "required": True},
    {"case_field": "", "core_field": "Discrepancy lists", "required": True},
    {"case_field": "", "core_field": "Application approval state transitions", "required": True},
]

SERVES = "Operations QC Review step"


class IntegrationNotConfigured(RuntimeError):
    """The client system behind INT_UI7 is not configured in this build."""


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    raise IntegrationNotConfigured(
        "INT_UI7 (SYS_A1, Operations QC Review screen) is not configured: "
        "the client system is not reachable in the build "
        f"(correlation_id={correlation_id})"
    )
