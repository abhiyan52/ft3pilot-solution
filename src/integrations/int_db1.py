"""INT_DB1 · SYS_A1 record lookup (DB read/write, existing client system).

The client system is not reachable in the build, so invoke() raises.
"""

REQUIREMENT_REFS = ("INT_DB1", "handover/sequences.mmd")

MODE = "db"
KIND = "tool"
IS_MOCK = False
ENDPOINT = None
SERVES = "record lookup"

FIELD_MAPPING = [
    {"case_field": "", "core_field": "record schema", "required": True},
]

OUTBOUND_ENDPOINTS = [
    {
        "auth": "Not stated",
        "endpoint_id": "EP-07",
        "error_actions": {
            "401": "Refresh token, retry once",
            "403": "Park case · alert Platform support",
            "404": "Route to manual verification",
            "409": "Duplicate · return existing case",
            "422": "Reject with validation report",
            "429": "Backoff 2ⁿ s, max 5",
            "5xx": "Retry ×3, then degrade to human",
            "timeout": "Retry ×2, then route to review",
        },
        "idempotency": None,
        "method": "GET",
        "path": "/sys-a1/int-db1/{id}",
        "timeout": "5 s",
    }
]


class IntegrationNotConfiguredError(RuntimeError):
    """The client system SYS_A1 is not configured in this build."""


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    raise IntegrationNotConfiguredError(
        "INT_DB1 (SYS_A1 record lookup) is not configured: "
        "the client system is not reachable in the build"
    )
