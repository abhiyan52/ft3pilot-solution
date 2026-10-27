"""INT_UI4: the Bank Details Entry screen of SYS_A1 (step S4), served to BLK_01.

Source: integration_map.yaml row INT_UI4. The row is an existing client system (kind "tool", mode "rpa"),
but tools.yaml declares no entry for it. The build therefore opens no connection, drives no browser and
reads no credential. invoke() raises SystemNotConfiguredError until client IT declares the tool.
"""
from __future__ import annotations

from typing import Any


REQUIREMENT_REFS: tuple[str, ...] = ("INT_UI4", "handover/sequences.mmd")
MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Bank Details Entry screen"
SERVES = "Bank Details Entry step"
SYSTEM = "SYS_A1"
STEP_ID = "S4"
AGENTS: tuple[str, ...] = ("BLK_01",)

# Copied from integration_map.yaml INT_UI4. Every case_field is blank in the Precord; that is a recorded gap.
FIELD_MAPPING: list[dict[str, Any]] = [
    {"case_field": "", "core_field": "Account Type", "required": True},
    {"case_field": "", "core_field": "Name As In Bank Account", "required": True},
    {"case_field": "", "core_field": "Bank Account Number", "required": True},
    {"case_field": "", "core_field": "IFSC Code", "required": True},
    {"case_field": "", "core_field": "Bank Name", "required": True},
    {"case_field": "", "core_field": "Bank City", "required": True},
    {"case_field": "", "core_field": "Branch Name", "required": True},
    {"case_field": "", "core_field": "Bank verification submission payload", "required": True},
]


class SystemNotConfiguredError(RuntimeError):
    """SYS_A1 Bank Details Entry screen is not configured: tools.yaml declares no tool for INT_UI4."""


def invoke(payload: dict[str, Any], correlation_id: str, *, endpoint: str | None = None,
           credential: Any = None) -> dict[str, Any]:
    """Refuse the call. The client system is not reachable in the build and no browser path is declared (C3-19)."""
    raise SystemNotConfiguredError(
        f"{SYSTEM} '{endpoint or ENDPOINT}' ({REQUIREMENT_REFS[0]}, {MODE}) is not configured: "
        f"tools.yaml declares no tool for it (correlation_id={correlation_id})"
    )
