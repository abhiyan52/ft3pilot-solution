"""INT_UI8 on SYS_A1: Post-Approval Training and Exam screen (step S8).

The client system is not reachable in the build. This module opens no
connection and reads no credential.
"""

REQUIREMENT_REFS = ("INT_UI8", "handover/sequences.mmd")

MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Post-Approval Training and Exam screen"
SERVES = "Post-Approval Training and Exam step"

FIELD_MAPPING = [
    {"case_field": "", "core_field": "Training Status", "required": True},
    {"case_field": "", "core_field": "Certification status", "required": True},
    {"case_field": "", "core_field": "Active agent code", "required": True},
]


class IntegrationNotConfigured(RuntimeError):
    """The client system for this integration is not configured in the build."""


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    raise IntegrationNotConfigured(
        "INT_UI8 (SYS_A1, Post-Approval Training and Exam screen) is not "
        "configured: the client system is not reachable in the build "
        f"[correlation_id={correlation_id}]"
    )
