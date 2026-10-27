"""INT_UI6 · Consent and Declaration screen on SYS_A1 (browser use, existing system).

Serves step S6, which spec/not_automated.csv (EX_01) keeps with a person.
The client system is not reachable in the build, so invoke() raises.
"""

REQUIREMENT_REFS = ("INT_UI6", "handover/sequences.mmd")

MODE = "rpa"
KIND = "tool"
IS_MOCK = False
ENDPOINT = "Consent and Declaration screen"
SERVES = "Consent and Declaration step"

FIELD_MAPPING = [
    {"case_field": "", "core_field": "Terms reviewed flag", "required": True},
    {"case_field": "", "core_field": "Declaration checkbox", "required": True},
    {"case_field": "", "core_field": "Consent date", "required": True},
    {"case_field": "", "core_field": "Declaration PDF", "required": True},
]


class SystemNotConfiguredError(RuntimeError):
    """The client system behind INT_UI6 is not configured in the build."""


def invoke(payload, correlation_id, *, endpoint=None, credential=None):
    raise SystemNotConfiguredError(
        "INT_UI6 (SYS_A1, Consent and Declaration screen) is not configured: "
        "the client system is not reachable in the build "
        f"(correlation_id={correlation_id})"
    )
