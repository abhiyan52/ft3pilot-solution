"""INT_UI7: the Operations QC Review screen of SYS_A1 (InsureBuddy), for step S7. Copied from integration_map.yaml.

The row is an existing client system reached by browser use, so the module is a tool, not a mock. tools.yaml declares no
entry for it and no browser path is declared, so the build opens no session to the system: invoke raises
SystemNotConfiguredError. Open item HR-306:INT_UI7 (default accepted) says to mock the endpoint; the row decides the kind.
"""
from __future__ import annotations

from typing import Any

REQUIREMENT_REFS: tuple[str, ...] = ("INT_UI7", "handover/sequences.mmd")
MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Operations QC Review screen"
SERVES = "Operations QC Review step"
SYSTEM = "SYS_A1"
STEP_ID = "S7"
AGENTS: tuple[str, ...] = ("BLK_02",)

# Every case_field is empty in the Precord; each one is a gap until the case schema names the field.
FIELD_MAPPING: list[dict[str, Any]] = [
    {"case_field": "", "core_field": "Application Status", "required": True},
    {"case_field": "", "core_field": "Agent Type", "required": True},
    {"case_field": "", "core_field": "Uploaded Documents", "required": True},
    {"case_field": "", "core_field": "KYC Verification Results", "required": True},
    {"case_field": "", "core_field": "Reviewer remark drafts", "required": True},
    {"case_field": "", "core_field": "Discrepancy lists", "required": True},
    {"case_field": "", "core_field": "Application approval state transitions", "required": True},
]

GAPS: tuple[str, ...] = tuple(
    f"INT_UI7 field '{row['core_field']}' has no case_field" for row in FIELD_MAPPING if not row["case_field"]
) + (
    "INT_UI7 has no tools.yaml entry and no declared browser path; open item HR-306:INT_UI7 says mock, the row says tool",
)


class SystemNotConfiguredError(RuntimeError):
    """SYS_A1 is not reachable in the build: no tools.yaml entry, no browser path, and no credential binding."""


def invoke(payload: dict[str, Any], correlation_id: str, *, endpoint: str | None = None, credential: Any = None) -> dict[str, Any]:
    """Call the Operations QC Review screen. The system is not configured in the build, so this always raises."""
    raise SystemNotConfiguredError(
        f"{SYSTEM} ({ENDPOINT}) is not configured for {MODE} access; "
        f"INT_UI7 has no tools.yaml entry (correlation_id={correlation_id})"
    )
