"""C1-4: model routing and fallback from runtime.yaml `models`. The Precord decides; env vars do not.

BUG-064: the agents do not call `call_with_fallback`. ADK has no fallback model, so an agent runs its declared model only.
Only deploy/smoke.py uses the fallback. The build record lists this as `model_notes` in `.specificity/resolved-versions.json`."""
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROUTES: dict[str, dict[str, Any]] = json.loads((Path(__file__).with_name("model_routes.json")).read_text())


def routes() -> dict[str, dict[str, Any]]:
    return ROUTES


def route(agent_id: str) -> dict[str, Any]:
    return ROUTES[agent_id]


def call_with_fallback(agent_id: str, call: Callable[[str], Any]) -> Any:
    """Call the declared model. When it fails, call the fallback model once."""
    chosen = route(agent_id)
    try:
        return call(chosen["model"])
    except Exception as primary:
        fallback = chosen.get("fallback_model")
        if not fallback:
            raise
        try:
            return call(fallback)
        except Exception as second:
            raise RuntimeError(f"{agent_id}: both {chosen['model']} and {fallback} failed: {second}") from primary
