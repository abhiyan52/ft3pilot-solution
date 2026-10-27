"""INT_UI8 · SYS_A1 Post-Approval Training and Exam screen (integration_map.yaml row INT_UI8, step S8).

The row is an existing client system (kind "tool") reached by browser use (mode "rpa"). tools.yaml has no entry for
it, so the build has no declared call to make: invoke() raises SystemNotConfigured and opens no connection.
Open item HR-306:INT_UI8 accepts the default "Mock the endpoint until it exists"; the row still says kind "tool",
so the row decides and the conflict is reported as a gap. No agent serves this row, and S8 is in the
not-automated register (EX_02): the prospective agent completes training and the exam in person."""
from __future__ import annotations

from typing import Any

REQUIREMENT_REFS: tuple[str, ...] = ("INT_UI8", "handover/sequences.mmd")
MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Post-Approval Training and Exam screen"
SERVES = "Post-Approval Training and Exam step"
FIELD_MAPPING: list[dict[str, Any]] = [
    {"case_field": "", "core_field": "Training Status", "required": True},
    {"case_field": "", "core_field": "Certification status", "required": True},
    {"case_field": "", "core_field": "Active agent code", "required": True},
]


class SystemNotConfigured(RuntimeError):
    """SYS_A1 is not reachable in the build. The message names the integration, never a credential."""


def invoke(payload: dict, correlation_id: str, *, endpoint: str | None = None, credential: str | None = None) -> dict:
    raise SystemNotConfigured(
        f"INT_UI8 ({ENDPOINT} on SYS_A1) is not configured: tools.yaml declares no tool for it "
        f"(correlation_id={correlation_id})"
    )
