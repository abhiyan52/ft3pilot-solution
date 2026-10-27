"""The ADK model of an agent. The choice of provider, model, and key is in `llm_config`; this file builds the ADK model."""
from __future__ import annotations

import logging
import os
from typing import Any

try:
    from solution import llm_config as config
except ImportError:  # the file was loaded by its path, outside the package (a test, or a script)
    import importlib.util
    import sys
    from pathlib import Path

    _spec = importlib.util.spec_from_file_location("solution_llm_config", Path(__file__).with_name("llm_config.py"))
    assert _spec and _spec.loader
    config = importlib.util.module_from_spec(_spec)
    sys.modules["solution_llm_config"] = config
    _spec.loader.exec_module(config)

_PRECORD_DEFAULT = "gemini-2.5-flash"
GEMINI_3 = "gemini-3"
_OVERRIDES: list[tuple[str, str]] = []
_DROPPED: list[tuple[str, str]] = []
_log = logging.getLogger(__name__)


def test_mode() -> bool:
    """Tell whether SOLUTION_TEST_MODE is on. Only test mode may replace the declared model through the older settings."""
    return (os.environ.get("SOLUTION_TEST_MODE") or "").strip().lower() in config.TRUE


def model_overrides() -> tuple[tuple[str, str], ...]:
    """Give each (declared model, model used) pair that a setting or the platform route replaced in this process."""
    return tuple(_OVERRIDES)


def dropped_settings() -> tuple[tuple[str, str], ...]:
    """Give each (model, setting) pair that a declared sampling setting did not reach the model in this process."""
    return tuple(_DROPPED)


def gateway_codex() -> bool:
    """Tell whether Specificity serves this Solution with a model route of its own (a preview or the platform)."""
    config.load_env_file()
    return (os.environ.get("SOLUTION_ADK_PLATFORM") or "").strip().lower() in config.GATEWAY_PLATFORMS and config.is_preview(os.environ)


def _resolved(declared: str) -> Any:
    chosen = config.resolve(declared)
    if chosen.model != declared and (declared, chosen.model) not in _OVERRIDES:
        _OVERRIDES.append((declared, chosen.model))
        _log.warning("The model %s replaces the declared model %s (%s)", chosen.model, declared,
                     "Specificity model route" if chosen.mode == "platform" else
                     "pinned default" if chosen.model == config.DEFAULT_GEMINI_MODEL else "settings of this Solution")
    return chosen


def configured_model_name(precord_default: str = _PRECORD_DEFAULT) -> str:
    """Give the model the agents call: the one the Precord declares, unless the settings or the platform route name another."""
    return str(_resolved(precord_default).model)


def configure_litellm_proxy() -> None:
    """Kept for older callers. The key and address go to the model call, so there is nothing to configure here."""


def adk_credentials_ready() -> bool:
    """Tell whether the settings give the agents a model and a key."""
    return not config.problem(_PRECORD_DEFAULT)


def resolve_adk_model(precord_default: str = _PRECORD_DEFAULT, max_retries: int | None = None) -> Any:
    """Return the model of an agent: a plain Gemini name, or a LiteLlm wrapper for any other provider.

    `max_retries` is the declared retry count. A LiteLlm wrapper retries a failed call that many times
    (`max_retries=1` gives at most two requests). A Gemini model name takes its retries from `generate_adk_config`."""
    chosen = _resolved(precord_default)
    if chosen.adk_model is None:
        # ADK reads these from the environment. A setting of this Solution fills a name that is not set.
        if chosen.provider == "vertex":
            os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
            # llm_config refused an empty region, so GOOGLE_CLOUD_LOCATION is set. No default region is chosen here.
            os.environ.setdefault("GOOGLE_CLOUD_LOCATION", chosen.region)
        elif chosen.api_key:
            os.environ.setdefault("GOOGLE_API_KEY", chosen.api_key)
        if chosen.api_base:
            os.environ.setdefault("GOOGLE_GEMINI_BASE_URL", chosen.api_base)
        return chosen.model
    if chosen.provider == "gateway-claude":
        try:
            from solution.claude_code_pool_llm import ClaudeCodePoolLlm
        except ImportError:
            import importlib.util
            from pathlib import Path
            spec = importlib.util.spec_from_file_location("solution_claude_pool", Path(__file__).with_name("claude_code_pool_llm.py"))
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            ClaudeCodePoolLlm = module.ClaudeCodePoolLlm
        return ClaudeCodePoolLlm(model=chosen.model, pool_url=chosen.api_base, pool_token=chosen.api_key)
    import litellm
    from google.adk.models.lite_llm import LiteLlm

    # Some models refuse a setting, such as a temperature. LiteLLM drops a setting that the model does not support.
    litellm.drop_params = True
    options: dict[str, Any] = dict(chosen.extra)
    if chosen.api_key:
        options["api_key"] = chosen.api_key
    if chosen.api_base:
        options["api_base"] = chosen.api_base
    if max_retries is not None:
        options["max_retries"] = max_retries
    # LiteLLM's `chatgpt` provider (the Specificity route) reads its token file and CHATGPT_API_BASE from the environment.
    return LiteLlm(model=chosen.adk_model, **options)


def generate_adk_config(model: Any, max_retries: int | None = None, **settings: Any) -> Any:
    """Build the generate_content_config of an agent, with the declared retries for a Gemini model.

    A Gemini model id retries through the HTTP options of the config: `attempts` counts every request,
    so `max_retries=1` is two attempts. A LiteLlm wrapper retries by itself (see `resolve_adk_model`), and
    a retry option in the config would add a second layer on top, so the config holds none for it."""
    from google.genai import types

    if max_retries is not None and isinstance(model, str):
        settings["http_options"] = types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=max_retries + 1))
    if isinstance(model, str) and model.startswith(GEMINI_3):
        # Google tunes Gemini 3 for its own sampling and warns that a lower temperature can loop or degrade the answer.
        # The declared temperature stays in the Solution. These models run without it.
        for name in ("temperature", "top_p", "top_k"):
            if settings.pop(name, None) is not None:
                if (model, name) not in _DROPPED:
                    _DROPPED.append((model, name))
                _log.warning("The declared %s is not sent to %s", name, model)
    return types.GenerateContentConfig(**settings)
