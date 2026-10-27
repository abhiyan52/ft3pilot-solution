"""INT_UI3: the Profile Details Entry screen of SYS_A1 (InsureBuddy), serving step S3 for BLK_01 (C3).

Copied from integration_map.yaml row INT_UI3: mechanism Browser use, mode rpa, kind tool, status existing, owned by
Client IT. The row decides the kind. Open item HR-306:INT_UI3 accepts the default "Mock the endpoint until it exists",
but that does not change the row, so this module is not a mock; the conflict is a recorded gap.
tools.yaml declares no browser-use tool for this row (C3-19), so no browser path is built. The client screen is not
reachable in the build, and invoke raises IntegrationNotConfigured. This module opens no connection and reads no
credential. Every case_field of FIELD_MAPPING is blank in the Precord; each is a recorded gap."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REQUIREMENT_REFS: tuple[str, ...] = ("INT_UI3", "handover/sequences.mmd")
MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Profile Details Entry screen"
SERVES = "Profile Details Entry step"
FIELD_MAPPING: list[dict[str, Any]] = [
    {"case_field": "", "core_field": "Name", "required": True},
    {"case_field": "", "core_field": "Gender", "required": True},
    {"case_field": "", "core_field": "Date of Birth", "required": True},
    {"case_field": "", "core_field": "Marital Status", "required": True},
    {"case_field": "", "core_field": "Address", "required": True},
    {"case_field": "", "core_field": "Pincode", "required": True},
    {"case_field": "", "core_field": "City", "required": True},
    {"case_field": "", "core_field": "State", "required": True},
]
# The other facts of the row, for the orchestrator and the trace.
INTEGRATION_ID = "INT_UI3"
SYSTEM = "SYS_A1"
STEP_ID = "S3"
AGENTS: tuple[str, ...] = ("BLK_01",)
DIRECTION = "both"
INTERACTION = "sync"
MECHANISM = "Browser use"


class IntegrationNotConfigured(RuntimeError):
    """SYS_A1 Profile Details Entry screen is not configured in this build. The message names the system, never a credential."""


def invoke(
    payload: Mapping[str, Any],
    correlation_id: str,
    *,
    endpoint: str | None = None,
    credential: str | None = None,
) -> dict[str, Any]:
    raise IntegrationNotConfigured(
        f"{INTEGRATION_ID} on {SYSTEM} ({endpoint or ENDPOINT}) is not configured: tools.yaml declares no "
        f"browser-use tool for it, so the build has no path to the client screen (correlation_id={correlation_id})"
    )
