"""Which model the agents of this Solution call, and with which key. This module owns that choice.

A Solution works on its own. Its settings come from `deploy/.env` (or the environment), and nothing here needs
the Specificity platform.

    SOLUTION_LLM_PROVIDER   gemini (default), vertex, openai, anthropic, openrouter, azure, litellm-proxy
    SOLUTION_LLM_MODEL      the model name of that provider. Optional for Gemini: the Precord names the model.
    SOLUTION_LLM_API_KEY    the key of the provider. The native name also works (OPENAI_API_KEY and the like).
    SOLUTION_LLM_API_BASE   an address other than the default, for a proxy or a private endpoint
    SOLUTION_LLM_USE_PINNED_DEFAULT   true runs the pinned Gemini default in place of an older declared Gemini model
    GOOGLE_CLOUD_LOCATION   the Vertex region. No default. The Q9 region in deploy/environment.json wins; a different value is refused.

When Specificity serves this Solution for a preview or from the platform, it sets `SOLUTION_ADK_PLATFORM=gateway-codex` or `gateway-claude`
and `SOLUTION_PREVIEW=true`, with a model route of its own. That route is used only while the Solution is served by
Specificity. A copy of those settings on a customer host is ignored, because `SOLUTION_PREVIEW` is not set there.

The module reads settings and names what is missing. It imports nothing from ADK, so it can be tested alone."""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TRUE = {"1", "true", "yes", "on"}
DEFAULT_PROVIDER = "gemini"
# The successor that a customer may choose with SOLUTION_LLM_USE_PINNED_DEFAULT=true. Google limits gemini-2.5-flash to
# accounts that already used it, so a new key may not reach it. This is Google's stable successor of 2.5 Flash.
# The Solution never uses it unless the customer asks. The declared model runs by default (BUG-064).
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
# Gemini models that the pinned default replaces when the Precord declares one of them and the customer asks for the
# pinned default. A customer can also choose any model with SOLUTION_LLM_MODEL.
SUPERSEDED_GEMINI = frozenset({
    "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.0-flash-001", "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001", "gemini-1.5-flash", "gemini-1.5-flash-001", "gemini-1.5-flash-002",
})
# Providers that ADK reaches with a plain model name. Every other provider goes through LiteLLM.
NATIVE = {"gemini", "vertex"}
# The key of each provider by its native name. SOLUTION_LLM_API_KEY takes the place of any of them.
KEY_NAMES = {
    "gemini": ("GOOGLE_API_KEY", "GEMINI_API_KEY"), "openai": ("OPENAI_API_KEY",), "anthropic": ("ANTHROPIC_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",), "azure": ("AZURE_API_KEY",), "litellm-proxy": ("LITELLM_PROXY_API_KEY",),
}
# LiteLLM names a model with its provider in front.
PREFIX = {"openai": "openai/", "anthropic": "anthropic/", "openrouter": "openrouter/", "azure": "azure/",
          "litellm-proxy": "openai/"}
LEGACY_PLATFORM = {"gemini": "gemini", "google": "gemini", "google-gemini": "gemini", "litellm": "litellm-proxy",
                   "litellm-openai": "litellm-proxy", "litellm-proxy": "litellm-proxy", "openai": "litellm-proxy",
                   "proxy": "litellm-proxy"}
GATEWAY_PLATFORMS = {"gateway-codex", "gateway-claude", "gateway"}
LEGACY_MODEL_NAMES = ("PLAYGROUND_ADK_MODEL", "SOLUTION_ADK_MODEL", "CODEX_ADK_MODEL")
_log = logging.getLogger(__name__)
_loaded: set[str] = set()


class LlmConfigError(RuntimeError):
    """The settings are missing or wrong. The message names the setting to fix."""


@dataclass(frozen=True)
class LlmConfig:
    mode: str                  # "platform" (served by Specificity) or "customer" (this Solution's own settings)
    provider: str
    model: str                 # the model name that the provider receives
    adk_model: str | None      # the LiteLLM model name. None: ADK takes `model` as a plain name (Gemini).
    api_key: str = ""
    api_base: str = ""
    region: str = ""          # the Vertex region. Empty for every other provider.
    extra: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        """Say what is set, without a key."""
        return {"mode": self.mode, "provider": self.provider, "model": self.model, "api_key_set": bool(self.api_key),
                "api_base": self.api_base or None,
                "region": self.region or None}


def _env(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def is_preview(env: Mapping[str, str]) -> bool:
    """True while Specificity serves the Solution. The platform sets SOLUTION_PREVIEW. A customer host does not."""
    return _env(env, "SOLUTION_PREVIEW").lower() in TRUE


def load_env_file(env: MutableMapping[str, str] | None = None, path: Path | None = None) -> Path | None:
    """Read `.env` into the environment. A value that is already set stays. Give the file that was read.

    The file is `SOLUTION_ENV_FILE`, or `.env` in the folder where the process runs, or `deploy/.env`, or `.env`
    at the root of the Solution."""
    target = os.environ if env is None else env
    root = Path(__file__).resolve().parents[2]
    named = _env(target, "SOLUTION_ENV_FILE")
    candidates = [path] if path else ([Path(named)] if named else [Path.cwd() / ".env", root / "deploy" / ".env", root / ".env"])
    for candidate in candidates:
        if candidate and candidate.is_file():
            if str(candidate) in _loaded and env is None:
                return candidate
            for line in candidate.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if not text or text.startswith("#") or "=" not in text:
                    continue
                name, _, value = text.partition("=")
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if name.strip() and name.strip() not in target:
                    target[name.strip()] = value
            _loaded.add(str(candidate))
            return candidate
    return None


def planned_residency() -> tuple[bool, str]:
    """BUG-098: what the builder wrote to `deploy/environment.json` about the model call: (cross-border forbidden, region).

    The region is set only from a Google Cloud location id in a client answer to Q9. The builder never picks one.
    A file that is absent or unreadable gives (False, "")."""
    try:
        text = (Path(__file__).resolve().parents[2] / "deploy" / "environment.json").read_text(encoding="utf-8")
        plan = json.loads(text)
        residency = plan.get("model_residency") if isinstance(plan.get("model_residency"), dict) else {}
        region = plan.get("model_region") if isinstance(plan.get("model_region"), dict) else {}
        return bool(residency.get("cross_border_forbidden")), str(region.get("region") or "").strip()
    except (OSError, ValueError, AttributeError):
        return False, ""


def _secret(name: str, env: Mapping[str, str]) -> str:
    """C1-4, F31-44: a name that runtime.yaml.secrets declares comes from its declared store. Any other name comes from env."""
    try:
        from solution import secret_store
    except ImportError:  # the module is loaded alone, for example by the builder at readiness
        return _env(env, name)
    return secret_store.value(name, env) or _env(env, name)


def _key(provider: str, env: Mapping[str, str]) -> str:
    return next((_secret(n, env) for n in ("SOLUTION_LLM_API_KEY", *KEY_NAMES.get(provider, ())) if _secret(n, env)), "")


def _provider(env: Mapping[str, str]) -> str:
    named = _env(env, "SOLUTION_LLM_PROVIDER").lower()
    if named:
        if named not in NATIVE | set(PREFIX):
            raise LlmConfigError(f"SOLUTION_LLM_PROVIDER={named!r} is not supported. Use one of: "
                                 + ", ".join(sorted(NATIVE | set(PREFIX))) + ".")
        return named
    legacy = _env(env, "SOLUTION_ADK_PLATFORM").lower()
    if legacy and legacy not in GATEWAY_PLATFORMS:
        if legacy not in LEGACY_PLATFORM:
            raise LlmConfigError(f"SOLUTION_ADK_PLATFORM={legacy!r} is not supported. Set SOLUTION_LLM_PROVIDER in the "
                                 "settings of the Solution.")
        return LEGACY_PLATFORM[legacy]
    if _env(env, "ADK_MODEL_BACKEND").lower() in {"litellm", "proxy"} or _env(env, "LITELLM_PROXY_API_BASE"):
        return "litellm-proxy"
    return DEFAULT_PROVIDER


def resolve(declared_model: str, env: Mapping[str, str] | None = None) -> LlmConfig:
    """Choose the provider, model, and key. Raise `LlmConfigError` that names what to set when something is missing."""
    if env is None:
        load_env_file()
    values: Mapping[str, str] = os.environ if env is None else env
    if _env(values, "SOLUTION_ADK_PLATFORM").lower() in GATEWAY_PLATFORMS:
        if is_preview(values):
            return _platform(values)
        _log.warning("The model route of the Specificity platform is set, but this Solution is not served by it. "
                     "The route is ignored. The Solution uses its own settings.")
    return _customer(declared_model, values)


def _platform(env: Mapping[str, str]) -> LlmConfig:
    model = _env(env, "SOLUTION_ADK_GATEWAY_MODEL")
    if not model:
        raise LlmConfigError("The Specificity model route gave no model. The Solution was not served with a model route.")
    if _env(env, "SOLUTION_ADK_PLATFORM") == "gateway-claude":
        base, token = _env(env, "ANTHROPIC_BASE_URL"), _env(env, "ANTHROPIC_AUTH_TOKEN")
        if not base or not token:
            raise LlmConfigError("The Specificity Claude route is incomplete: its address or token is missing.")
        return LlmConfig(mode="platform", provider="gateway-claude", model=model, adk_model=f"claude-code/{model}",
                         api_key=token, api_base=base)
    base, token_dir = _env(env, "CHATGPT_API_BASE"), _env(env, "CHATGPT_TOKEN_DIR")
    if not base or not (Path(token_dir or "/nonexistent") / "auth.json").is_file():
        raise LlmConfigError("The Specificity model route is incomplete: CHATGPT_API_BASE or its token file is missing.")
    return LlmConfig(mode="platform", provider="gateway-codex", model=model, adk_model=f"chatgpt/{model}", api_base=base)


def _customer(declared: str, env: Mapping[str, str]) -> LlmConfig:
    provider = _provider(env)
    forbidden, planned = planned_residency()
    if forbidden and not (provider == "vertex" and planned):
        raise LlmConfigError(f"The residency answers forbid a cross-border model call, but the provider is {provider} "
                             + ("and no model region is chosen in deploy/environment.json (model_region). Client IT answers Q9 with a "
                                "Google Cloud region id." if provider == "vertex" else
                                "which does not keep the call in the country. Set SOLUTION_LLM_PROVIDER=vertex."))
    test_mode = _env(env, "SOLUTION_TEST_MODE").lower() in TRUE
    legacy = next((_env(env, n) for n in LEGACY_MODEL_NAMES if test_mode and _env(env, n)), "")
    chosen = _env(env, "SOLUTION_LLM_MODEL") or legacy
    model = chosen or ("" if provider not in NATIVE and provider != "litellm-proxy" else declared)
    # A model that the customer names always wins. The declared model runs unless the customer asks for the pinned
    # default, and the pin replaces only a declared model that Google has superseded.
    if (not chosen and provider in NATIVE and declared in SUPERSEDED_GEMINI
            and _env(env, "SOLUTION_LLM_USE_PINNED_DEFAULT").lower() in TRUE):
        model = DEFAULT_GEMINI_MODEL
    if not model:
        raise LlmConfigError(f"Set SOLUTION_LLM_MODEL. The Precord declares {declared!r}, which {provider} does not serve.")
    key = _key(provider, env)
    base = _env(env, "SOLUTION_LLM_API_BASE") or (_env(env, "LITELLM_PROXY_API_BASE") if provider == "litellm-proxy" else "")
    extra: dict[str, Any] = {}
    region = ""
    if provider == "gemini" and not key:
        raise LlmConfigError("Set GOOGLE_API_KEY (or SOLUTION_LLM_API_KEY) for the Gemini provider.")
    if provider == "vertex":
        if not _env(env, "GOOGLE_CLOUD_PROJECT"):
            raise LlmConfigError("Set GOOGLE_CLOUD_PROJECT for the Vertex provider. Vertex signs in with "
                                 "Application Default Credentials.")
        # No default region: a default would move client data across a border (FT3Pilot Q9). The client chooses it.
        # The Q9 region of deploy/environment.json wins. A different GOOGLE_CLOUD_LOCATION is refused (BUG-098).
        named = _env(env, "GOOGLE_CLOUD_LOCATION")
        if planned and named and named != planned:
            raise LlmConfigError(f"GOOGLE_CLOUD_LOCATION={named!r} differs from the model region {planned!r} that the client "
                                 "chose in deploy/environment.json (model_region). Remove it or set the same region.")
        region = planned or named
        if not region:
            raise LlmConfigError("Set GOOGLE_CLOUD_LOCATION for the Vertex provider. The Solution does not guess a model "
                                 "region. Use the region that the residency answer allows (model_region in deploy/environment.json).")
    elif provider in {"openai", "anthropic", "openrouter", "azure", "litellm-proxy"} and not key:
        raise LlmConfigError(f"Set {KEY_NAMES[provider][0]} (or SOLUTION_LLM_API_KEY) for the {provider} provider.")
    if provider == "litellm-proxy" and not base:
        raise LlmConfigError("Set LITELLM_PROXY_API_BASE (or SOLUTION_LLM_API_BASE) for the litellm-proxy provider.")
    if provider == "azure":
        extra = {"api_version": _env(env, "AZURE_API_VERSION")}
        base = base or _env(env, "AZURE_API_BASE")
        if not base or not extra["api_version"]:
            raise LlmConfigError("Set AZURE_API_BASE and AZURE_API_VERSION for the azure provider. SOLUTION_LLM_MODEL is the deployment name.")
    adk = None if provider in NATIVE else f"{PREFIX[provider]}{model}"
    return LlmConfig(mode="customer", provider=provider, model=model, adk_model=adk, api_key=key, api_base=base, region=region, extra=extra)


def problem(declared_model: str = "", env: Mapping[str, str] | None = None) -> str:
    """Give what is wrong with the settings in one sentence, or an empty text when the agents can call a model."""
    try:
        resolve(declared_model or "gemini-2.5-flash", env)
    except LlmConfigError as error:
        return str(error)
    return ""
