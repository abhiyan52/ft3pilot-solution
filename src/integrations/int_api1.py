"""INT_API1 on SYS_A1: Solution-built adapter for the workflow integration.

The client system is not reachable in the build. invoke() raises
NotConfiguredError. No network connection is opened and no credential is read.
"""

REQUIREMENT_REFS = (
    "INT_API1",
    "handover/sequences.mmd",
)

MODE = "api"
KIND = "adapter"
IS_MOCK = False
ENDPOINT = "workflow API"

FIELD_MAPPING = [
    {"case_field": "", "core_field": "payload_pending", "required": True},
]

SERVES = "workflow integration"

OUTBOUND_ENDPOINTS = [
    {
        "auth": "mTLS",
        "endpoint_id": "EP-05",
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
        "idempotency": "Idempotency-Key header (case_id)",
        "method": "PUT",
        "path": "/adapter/sys-a1/int-api1/{id}",
        "timeout": "10 s",
    },
]


class IntegrationNotConfiguredError(RuntimeError):
    """The client system for INT_API1 is not configured in this build."""


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    raise IntegrationNotConfiguredError(
        "INT_API1 (SYS_A1, workflow API) is not configured: "
        "the client system is not reachable in the build"
    )
