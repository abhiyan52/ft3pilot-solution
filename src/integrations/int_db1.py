"""INT_DB1 on SYS_A1: record lookup (integration_map.yaml, integration_id INT_DB1).

The row is kind "tool", mode "db", status "existing", owner Client IT. The client system is not reachable in the
build, so `invoke` raises `SystemNotConfigured`. It opens no connection and reads no credential.
Open item HR-306:INT_DB1 says the system is "not available" and accepts the default "Mock the endpoint until it
exists". The row decides the kind, so this module is not a mock; the conflict is reported as a gap.
OUTBOUND_ENDPOINTS are calls this module makes to SYS_A1. The Solution does not serve them."""
from __future__ import annotations

from typing import Any

REQUIREMENT_REFS: tuple[str, ...] = ("INT_DB1", "handover/sequences.mmd")

MODE = "db"
KIND = "tool"
IS_MOCK = KIND == "mock"

# integration_map.yaml gives this row no endpoint (null). Copied as is; reported as a gap.
ENDPOINT: str | None = None

# Copied from the row. case_field is empty and "record schema" names no field; reported as a gap.
FIELD_MAPPING: list[dict[str, Any]] = [
    {"case_field": "", "core_field": "record schema", "required": True},
]

SERVES = "record lookup"

OUTBOUND_ENDPOINTS: list[dict[str, Any]] = [
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
    },
]


class SystemNotConfigured(RuntimeError):
    """SYS_A1 (INT_DB1) is not configured in this build. The message names the integration, never a credential."""


def invoke(
    payload: dict[str, Any],
    correlation_id: str,
    *,
    endpoint: str | None = None,
    credential: str | None = None,
) -> dict[str, Any]:
    """Look up a record on SYS_A1 through INT_DB1. The client system is not reachable in the build, so this raises."""
    raise SystemNotConfigured(
        f"INT_DB1 on SYS_A1 ({SERVES}) is not configured: the client system is not reachable in this build "
        f"(correlation_id={correlation_id})"
    )
