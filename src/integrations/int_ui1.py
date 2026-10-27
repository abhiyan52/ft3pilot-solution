"""INT_UI1: Create an Agent or Account screen on SYS_A1 (step S1).

The mapped row says KIND "tool", MODE "rpa" (browser use). The client system
is not reachable in the build, so invoke() raises IntegrationNotConfigured.
No network connection, no browser path and no credential read lives here.
"""

REQUIREMENT_REFS = ("INT_UI1", "handover/sequences.mmd")

MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Create an Agent or Account screen"
SERVES = "Create an Agent or Account step"

FIELD_MAPPING = [
    {"case_field": "", "core_field": "Full Name", "required": True},
    {"case_field": "", "core_field": "Mobile Number", "required": True},
    {"case_field": "", "core_field": "Email", "required": True},
    {"case_field": "", "core_field": "RM Business Code", "required": True},
    {"case_field": "", "core_field": "Application record draft", "required": True},
    {"case_field": "", "core_field": "Validation error status", "required": True},
]


class IntegrationNotConfigured(RuntimeError):
    """The client system SYS_A1 is not configured or reachable in the build."""


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    raise IntegrationNotConfigured(
        "INT_UI1 (SYS_A1, 'Create an Agent or Account screen', browser use) "
        "is not configured; correlation_id=%s" % (correlation_id,)
    )
