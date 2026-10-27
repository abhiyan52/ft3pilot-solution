"""Run one declared agent through the ADK Runner. The module needs C3 output only. It reads no Playground file.

invoke_agent validates the input against INPUT_SCHEMA, runs the agent, and validates the answer against OUTPUT_SCHEMA.
It never fills a missing field and never repairs an answer. A failure raises an error that names the schema path.
The SDK usage events of each call stay apart from the answer. `usage_events` gives them to the measurement code.
The tool calls of each call stay apart too. `tool_calls` gives the declared tool IDs in call order to the G-04 grader.
"""
from __future__ import annotations

import importlib
import json
import os
import re
from collections import defaultdict, deque
from typing import Any, Callable

APP_NAME = "specificity_solution"
USER_ID = "solution-runtime"
_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_USAGE: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=1000))
_TOOLS: dict[str, list[str]] = {}


class AgentRuntimeError(Exception):
    """Base of every error that invoke_agent raises on its own."""


class AgentNotFound(AgentRuntimeError):
    """No module under agents/ matches the agent ID."""


class AgentInputInvalid(AgentRuntimeError):
    """The payload does not fit INPUT_SCHEMA. The agent was not run."""


class AgentOutputInvalid(AgentRuntimeError):
    """The agent answer is not JSON, or it does not fit OUTPUT_SCHEMA. Nothing was filled in."""


def module_name(agent_id: str) -> str:
    return "agents." + agent_id.lower().replace("-", "_").replace(".", "_")


def load_agent_module(agent_id: str) -> Any:
    try:
        return importlib.import_module(module_name(agent_id))
    except ModuleNotFoundError as error:
        if error.name and module_name(agent_id).startswith(error.name):
            raise AgentNotFound(f"No agent module for {agent_id}") from error
        raise


def _validator(schema: dict[str, Any], store: dict[str, Any] | None) -> Any:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    registry = Registry().with_resources(
        [(name, Resource.from_contents(value, default_specification=DRAFT202012)) for name, value in (store or {}).items()])
    return Draft202012Validator(schema, registry=registry)


def validate(value: Any, schema: dict[str, Any], store: dict[str, Any] | None, error: type[AgentRuntimeError]) -> None:
    problems = sorted(_validator(schema, store).iter_errors(value), key=lambda item: list(item.absolute_path))
    if problems:
        first = problems[0]
        where = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise error(f"{where}: {first.message}")


def _final_text(events: list[Any]) -> str:
    for event in reversed(events):
        parts = getattr(getattr(event, "content", None), "parts", None) or []
        text = "".join(part.text for part in parts if getattr(part, "text", None) and not getattr(part, "thought", False))
        if text.strip() and event.is_final_response():
            return text
    raise AgentOutputInvalid("The agent gave no final answer")


def parse_answer(text: str) -> Any:
    body = text.strip()
    fenced = _FENCE.match(body)
    try:
        return json.loads(fenced.group(1) if fenced else body)
    except ValueError as error:
        raise AgentOutputInvalid(f"The final answer is not JSON: {error}") from error


def _usage_row(event: Any, agent_id: str, correlation_id: str) -> dict[str, Any] | None:
    usage = getattr(event, "usage_metadata", None)
    if usage is None:
        return None
    return {"agent_id": agent_id, "correlation_id": correlation_id, "event_id": getattr(event, "id", ""),
            "author": getattr(event, "author", ""), "model": getattr(event, "model_version", None),
            "prompt_tokens": getattr(usage, "prompt_token_count", None),
            "output_tokens": getattr(usage, "candidates_token_count", None),
            "total_tokens": getattr(usage, "total_token_count", None)}


def usage_events(correlation_id: str) -> list[dict[str, Any]]:
    """Give the SDK usage events recorded for one correlation ID. The list is a copy."""
    return list(_USAGE.get(correlation_id, ()))


def forget_usage(correlation_id: str) -> None:
    _USAGE.pop(correlation_id, None)
    _TOOLS.pop(correlation_id, None)


def _called_tools(event: Any, bindings: dict[str, str] | None) -> list[str]:
    """Give the declared tool IDs that one model event asks for, in order. A partial streaming chunk is not a call.

    When TOOL_BINDINGS is a dict, only a bound callable counts, as in `tool_policy.before_tool`. An ADK framework tool
    (set_model_response, transfer_to_agent) or any unbound name is not a declared tool, so G-04 never sees it.
    When the module has no TOOL_BINDINGS dict, the names stay as they are, so the grader reports the mismatch."""
    if getattr(event, "partial", False):
        return []
    parts = getattr(getattr(event, "content", None), "parts", None) or []
    names = [getattr(part.function_call, "name", None) for part in parts if getattr(part, "function_call", None)]
    names = [name for name in names if name]
    if isinstance(bindings, dict):
        return [str(bindings[name]) for name in names if name in bindings]
    return [str(name) for name in names]


def tool_calls(correlation_id: str) -> list[str] | None:
    """Give the declared tool IDs that the agent called for one correlation ID, in call order.

    A run that called no tool gives an empty list. An ID that `invoke_agent` never recorded gives None:
    the call is unknown, never an empty list (G-04 reads None as "not measured")."""
    calls = _TOOLS.get(correlation_id)
    return None if calls is None else list(calls)


def default_runner(agent: Any, agent_id: str, case_id: str, bindings: dict[str, str] | None) -> Any:
    """Build the ADK Runner. A database URL gives a persistent session service; without one the sessions stay in memory."""
    from google.adk.runners import Runner

    if os.environ.get("DATABASE_URL"):
        from solution.runtime import make_runner
        return make_runner(agent, agent_id=agent_id, case_id=case_id, tool_bindings=bindings)
    if getattr(agent, "tools", None):
        from solution.tool_policy import install, metadata
        install(agent, agent_id, case_id, metadata(), bindings=bindings)
    from google.adk.sessions import InMemorySessionService
    return Runner(app_name=APP_NAME, agent=agent, session_service=InMemorySessionService())


RunnerFactory = Callable[[Any, str, str, "dict[str, str] | None"], Any]
_factory: RunnerFactory = default_runner


def set_runner_factory(factory: RunnerFactory | None) -> None:
    """Replace the Runner builder. A test or a host uses it. None restores the default."""
    global _factory
    _factory = factory or default_runner


async def invoke_agent(agent_id: str, payload: dict[str, Any], *, correlation_id: str,
                       session_id: str | None = None) -> dict[str, Any]:
    """Run the agent on one payload. Give its answer as a dict that fits OUTPUT_SCHEMA."""
    if not correlation_id:
        raise AgentInputInvalid("A correlation ID is required for every call")
    from google.genai import types

    from solution.telemetry import correlation

    module = load_agent_module(agent_id)
    store = getattr(module, "SCHEMA_STORE", None)
    validate(payload, module.INPUT_SCHEMA, store, AgentInputInvalid)
    case_id = str(payload.get("case_id") or correlation_id) if isinstance(payload, dict) else correlation_id
    agent = module.make_agent()
    runner = _factory(agent, agent_id, case_id, getattr(module, "TOOL_BINDINGS", None))
    with correlation(correlation_id):
        sessions = runner.session_service
        session = await sessions.get_session(app_name=runner.app_name, user_id=USER_ID, session_id=session_id) if session_id else None
        if session is None:
            session = await sessions.create_session(app_name=runner.app_name, user_id=USER_ID, session_id=session_id,
                                                    state={"correlation_id": correlation_id, "agent_id": agent_id})
        message = types.Content(role="user", parts=[types.Part(text=json.dumps(payload, sort_keys=True))])
        events: list[Any] = []
        bindings = getattr(module, "TOOL_BINDINGS", None)
        _TOOLS[correlation_id] = []
        async for event in runner.run_async(user_id=USER_ID, session_id=session.id, new_message=message):
            events.append(event)
            _TOOLS[correlation_id] += _called_tools(event, bindings)
            row = _usage_row(event, agent_id, correlation_id)
            if row is not None:
                _USAGE[correlation_id].append(row)
    answer = parse_answer(_final_text(events))
    validate(answer, module.OUTPUT_SCHEMA, store, AgentOutputInvalid)
    return answer
