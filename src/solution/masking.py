"""Masking of personal data in what the Solution shows (C1-6, C9-5).

`data_management.json` names the case fields to mask and how. The routes call `mask_fields`, `mask_cases` and `mask_history`
before a value leaves the Solution. The database keeps the true value. A method that this module does not know
masks the whole value, so an unknown rule never shows more than a known one."""
import hashlib
import json
from pathlib import Path
from typing import Any

PLAN_PATH = Path(__file__).with_name("data_management.json")
REDACTED = "[masked]"


def rules() -> dict[str, str]:
    """Give the masking method of each field. A file that is missing or unreadable gives no rule."""
    try:
        plan = json.loads(PLAN_PATH.read_text())
    except (OSError, ValueError):
        return {}
    return {str(rule["field"]): str(rule.get("method") or "redact")
            for rule in plan.get("masking") or [] if isinstance(rule, dict) and rule.get("field")}


def mask_value(method: str, value: Any) -> Any:
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value)
    if method == "partial":
        return ("*" * max(len(text) - 4, 0)) + text[-4:] if len(text) > 4 else REDACTED
    if method == "hash":
        return hashlib.sha256(text.encode()).hexdigest()[:16]
    return REDACTED


def mask_fields(fields: dict[str, Any]) -> dict[str, Any]:
    plan = rules()
    return {name: mask_value(plan[name], value) if name in plan else value for name, value in fields.items()}


def mask_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan = rules()
    return [dict(row, value=mask_value(plan[row["field"]], row.get("value"))) if row.get("field") in plan else row
            for row in rows]


LISTED_FIELDS = ("status", "step", "assignee")


def mask_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mask the case fields that a case list shows. last_action names a field and an author, never a value."""
    plan = rules()
    return [dict(case, **{name: mask_value(plan[name], case.get(name)) for name in LISTED_FIELDS if name in plan})
            for case in cases]
