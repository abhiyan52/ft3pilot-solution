"""INT_API1 on SYS_A1: the workflow adapter that the Solution builds (integration_map.yaml, INT_API1).

The row is kind `adapter` and mode `api`, so this module is not a mock. Open item HR-306:INT_API1 accepts the
default "Mock the endpoint until it exists", but the row decides the kind, so the conflict is reported as a gap.
The client system is not reachable in the build: `invoke` opens no connection, reads no credential and raises
`SystemNotConfigured`. OUTBOUND_ENDPOINTS are calls this module makes to SYS_A1. The Solution does not serve them."""
from __future__ import annotations

from typing import Any

REQUIREMENT_REFS = ("INT_API1", "handover/sequences.mmd")
INTEGRATION_ID = "INT_API1"
SYSTEM = "SYS_A1"
MODE = "api"
KIND = "adapter"
IS_MOCK = False
ENDPOINT = "workflow API"
SERVES = "workflow integration"
DIRECTION = "both"
INTERACTION = "async callback"

# Copied from integration_map.yaml INT_API1. case_field is blank in the Precord; it stays blank here.
FIELD_MAPPING: list[dict[str, Any]] = [
    {"case_field": "", "core_field": "payload_pending", "required": True},
]

# Copied from integration_map.yaml INT_API1 endpoints. No router serves these.
OUTBOUND_ENDPOINTS: list[dict[str, Any]] = [
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


class SystemNotConfigured(RuntimeError):
    """SYS_A1 is not configured for this build. The message names the integration and system, never a credential."""


def invoke(payload: dict[str, Any], correlation_id: str, *, endpoint: str | None = None,
           credential: str | None = None) -> dict[str, Any]:
    """Call SYS_A1 through INT_API1. The client system is not reachable in the build, so this always raises."""
    raise SystemNotConfigured(
        f"{INTEGRATION_ID} on {SYSTEM} is not configured: the workflow API adapter has no reachable endpoint "
        f"in this build (correlation_id={correlation_id})."
    )
