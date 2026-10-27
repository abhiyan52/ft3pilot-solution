"""INT_UI2: the User Verification screen of SYS_A1 (InsureBuddy), serving step S2 for BLK_01.

Source: integration_map.yaml row INT_UI2. The row is an existing client system reached by browser use, so the module
is a tool and not a mock. tools.yaml declares no entry for it, so the Solution holds no browser path, no endpoint and
no credential for it (C3-19). `invoke` refuses with `SystemNotConfiguredError` until client IT declares the tool.

Open item HR-306:INT_UI2 accepts the default "Mock the endpoint until it exists". The row still says kind tool, so the
module follows the row and the conflict is a recorded gap.

Every field below has an empty case_field: the case schema names no property for it yet."""
from __future__ import annotations

from typing import Any

REQUIREMENT_REFS = ("INT_UI2", "handover/sequences.mmd")

MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "User Verification screen"
SERVES = "User Verification step"

FIELD_MAPPING = [
    {"case_field": "", "core_field": "PAN Number", "required": True},
    {"case_field": "", "core_field": "Aadhaar Number", "required": True},
    {"case_field": "", "core_field": "CKYC Number", "required": True},
    {"case_field": "", "core_field": "External KYC service response", "required": True},
    {"case_field": "", "core_field": "KYC verification status", "required": True},
    {"case_field": "", "core_field": "System retry queue entry", "required": True},
]


class SystemNotConfiguredError(RuntimeError):
    """SYS_A1 is not reachable in the build: tools.yaml declares no tool for INT_UI2."""


def invoke(payload: dict[str, Any], correlation_id: str, *, endpoint: str | None = None,
           credential: str | None = None) -> dict[str, Any]:
    """Refuse the call. The Solution opens no browser session and no connection to SYS_A1."""
    raise SystemNotConfiguredError(
        f"INT_UI2 ({ENDPOINT} on SYS_A1) is not configured: tools.yaml declares no tool for it, "
        f"so no browser path is built (correlation_id={correlation_id})")
