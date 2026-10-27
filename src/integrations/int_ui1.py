"""INT_UI1: SYS_A1 "Create an Agent or Account screen", serving step S1 for BLK_01 (integration_map.yaml).

The row is an existing client system driven by browser use. tools.yaml declares no tool for it, so the build
opens no browser, no network connection and reads no credential: invoke() raises SystemNotConfiguredError.
Open item HR-306:INT_UI1 accepts "Mock the endpoint until it exists"; the row says kind "tool", so the row wins
and the conflict is reported as a gap, not built as a mock.
"""
from __future__ import annotations

from typing import Any


REQUIREMENT_REFS = ("INT_UI1", "handover/sequences.mmd")

MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Create an Agent or Account screen"
SERVES = "Create an Agent or Account step"

SYSTEM = "SYS_A1"
STEP_ID = "S1"
AGENTS = ("BLK_01",)

FIELD_MAPPING: list[dict[str, Any]] = [
    {"case_field": "", "core_field": "Full Name", "required": True},
    {"case_field": "", "core_field": "Mobile Number", "required": True},
    {"case_field": "", "core_field": "Email", "required": True},
    {"case_field": "", "core_field": "RM Business Code", "required": True},
    {"case_field": "", "core_field": "Application record draft", "required": True},
    {"case_field": "", "core_field": "Validation error status", "required": True},
]

# mapped.endpoints is empty, so OUTBOUND_ENDPOINTS is not defined.


class SystemNotConfiguredError(RuntimeError):
    """SYS_A1 is not reachable in the build: no tools.yaml entry, no endpoint binding, no credential."""


def invoke(payload: dict[str, Any], correlation_id: str, *, endpoint: str | None = None,
           credential: str | None = None) -> dict[str, Any]:
    """Refuse the call. KIND is "tool", and the client system is not configured for this build."""
    raise SystemNotConfiguredError(
        f"INT_UI1 ({SYSTEM}, {ENDPOINT!r}, mode {MODE}) is not configured: tools.yaml declares no tool and no "
        f"browser path is built (correlation_id={correlation_id})"
    )
