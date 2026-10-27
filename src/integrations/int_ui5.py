"""INT_UI5 · Document Upload screen on SYS_A1 (integration_map.yaml row INT_UI5, step S5, agent BLK_02).

The row is an existing client system reached by browser use (mode rpa, kind tool). tools.yaml declares no entry for it
and no browser path is declared (C3-19), so this module builds none. The client system is not reachable in the build:
invoke raises SystemNotConfigured. It opens no connection and reads no credential.

Open item HR-306:INT_UI5 accepts the default "Mock the endpoint until it exists". The row still says kind tool, so this
module copies the row and is not a mock; the conflict is recorded as a gap in the Completion Report."""
from __future__ import annotations

from typing import Any

REQUIREMENT_REFS: tuple[str, ...] = ("INT_UI5", "handover/sequences.mmd")
MODE = "rpa"
KIND = "tool"
IS_MOCK = KIND == "mock"
ENDPOINT = "Document Upload screen"
SERVES = "Document Upload step"
SYSTEM = "SYS_A1"
STEP_ID = "S5"
AGENTS: tuple[str, ...] = ("BLK_02",)

# Copied exactly from integration_map.yaml INT_UI5. Every case_field is blank in the Precord.
FIELD_MAPPING: list[dict[str, Any]] = [
    {"case_field": "", "core_field": "Profile Photo", "required": True},
    {"case_field": "", "core_field": "PAN Card", "required": True},
    {"case_field": "", "core_field": "Aadhaar Front", "required": True},
    {"case_field": "", "core_field": "Aadhaar Back", "required": True},
    {"case_field": "", "core_field": "Bank Proof", "required": True},
    {"case_field": "", "core_field": "Education Document", "required": True},
    {"case_field": "", "core_field": "Categorized document records", "required": True},
    {"case_field": "", "core_field": "Validation status flags", "required": True},
    {"case_field": "", "core_field": "Cropped image assets", "required": True},
]


class SystemNotConfigured(RuntimeError):
    """The client system behind this integration is not configured in the build. The message names no credential."""


def invoke(payload: dict[str, Any], correlation_id: str, *, endpoint: str | None = None,
           credential: str | None = None) -> dict[str, Any]:
    raise SystemNotConfigured(
        f"{REQUIREMENT_REFS[0]} on {SYSTEM} ({ENDPOINT}, mode {MODE}) is not configured: the client system is not "
        f"reachable in the build and tools.yaml declares no browser path (correlation_id={correlation_id})"
    )
