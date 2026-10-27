"""INT_UI6: the Consent and Declaration screen of SYS_A1 (InsureBuddy), step S6.

Copied from integration_map.yaml row INT_UI6. The row says an existing system
(kind tool) reached by browser use (mode rpa), so this is not a mock. The build
cannot reach the client system and spec/tools.yaml declares no browser tool, so
invoke() raises. Open item HR-306:INT_UI6 accepted the default "Mock the endpoint
until it exists"; that does not change the row, and is recorded as a gap.

S6 is in spec/not_automated.csv (EX_01, regulatory) and the orchestration gives
it to a person. No agent serves this row. Nothing here may automate consent.
"""
from __future__ import annotations

from typing import Any

REQUIREMENT_REFS: tuple[str, ...] = ("INT_UI6", "handover/sequences.mmd")

MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Consent and Declaration screen"
SERVES = "Consent and Declaration step"

SYSTEM = "SYS_A1"
STEP_ID = "S6"
AGENTS: tuple[str, ...] = ()

# case_field is blank on every row in the Precord; each blank is a gap.
FIELD_MAPPING: list[dict[str, Any]] = [
    {"case_field": "", "core_field": "Terms reviewed flag", "required": True},
    {"case_field": "", "core_field": "Declaration checkbox", "required": True},
    {"case_field": "", "core_field": "Consent date", "required": True},
    {"case_field": "", "core_field": "Declaration PDF", "required": True},
]

GAPS: tuple[str, ...] = (
    "INT_UI6: case_field is empty for 'Terms reviewed flag'.",
    "INT_UI6: case_field is empty for 'Declaration checkbox'.",
    "INT_UI6: case_field is empty for 'Consent date'.",
    "INT_UI6: case_field is empty for 'Declaration PDF'.",
    "INT_UI6: mapped.agents is empty; no agent serves this row.",
    "INT_UI6: open item HR-306:INT_UI6 default says mock, but the row says kind tool; the row decides.",
    "INT_UI6: spec/tools.yaml declares no browser tool, so no browser path is built (C3-19).",
    "INT_UI6: step S6 is not automated (EX_01, regulatory) and is owned by a person.",
)


class IntegrationNotConfiguredError(RuntimeError):
    """SYS_A1 is not reachable in the build, and no browser tool is declared for it."""


def invoke(
    payload: dict[str, Any],
    correlation_id: str,
    *,
    endpoint: str | None = None,
    credential: str | None = None,
) -> dict[str, Any]:
    """Refuse the call: the Consent and Declaration screen of SYS_A1 is not configured."""
    raise IntegrationNotConfiguredError(
        f"INT_UI6 ({SYSTEM}, {ENDPOINT}) is not configured: the client system is not reachable "
        f"in the build and spec/tools.yaml declares no browser tool for it. Step {STEP_ID} is "
        f"not automated (EX_01). correlation_id={correlation_id}"
    )
