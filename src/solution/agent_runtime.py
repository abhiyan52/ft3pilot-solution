"""Run one declared agent through the ADK Runner. The module needs C3 output only. It reads no Playground file.

invoke_agent validates the input against INPUT_SCHEMA, runs the agent, and validates the answer against OUTPUT_SCHEMA.
It never fills a missing field and never repairs an answer. A failure raises an error that names the schema path.
The SDK usage events of each call stay apart from the answer. `usage_events` gives them to the measurement code.
The tool calls of each call stay apart too. `tool_calls` gives the declared tool IDs in call order to the G-04 grader.

`enter_case` is the entry of a case (BUG-082). It goes through the built orchestrator: trigger, agent `run_case`,
checkpoint, output. A process-level case names no agent, so the orchestrator route gives the agents. When the
Solution has no orchestrator, an agent call falls back to `invoke_agent` and the entry says so. It never falls back in silence.
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


class OrchestratorMissing(AgentRuntimeError):
    """A process-level case needs the orchestrator, and the Solution has none."""


def orchestrator_module() -> Any:
    """Give the built orchestrator module, or None when C3 has not built it. A missing library of it is a fault."""
    try:
        return importlib.import_module("orchestrator.orchestrator")
    except ModuleNotFoundError as error:
        if error.name in {"orchestrator", "orchestrator.orchestrator"}:
            return None
        raise


def _entry_trigger(orchestrator: Any, agent_id: str) -> str | None:
    for trigger in getattr(orchestrator, "TRIGGERS", None) or ():
        if isinstance(trigger, dict) and trigger.get("starts") == agent_id:
            return str(trigger.get("kind"))
    return None


def _checkpoints_after(orchestrator: Any, agent_id: str) -> list[str]:
    pauses = getattr(orchestrator, "pauses_at", None)
    return [str(item) for item in pauses(agent_id)] if callable(pauses) else []


def _parent_of(orchestrator: Any, agent_id: str) -> str | None:
    """The parent agent ID when agent_id is a sub-agent, else None."""
    for parent, children in (getattr(orchestrator, "SUB_AGENTS", None) or {}).items():
        if agent_id in [str(child) for child in children]:
            return str(parent)
    return None


def describe_entry(agent_id: str) -> dict[str, Any]:
    """How an agent is entered: the trigger that starts it and the checkpoints after it. Both hosts record this.

    A sub-agent is the target of a direct run (an eval or a Playground run), never a route stage: the orchestrator does
    not route a case to it. The entry then says target "sub_agent" and names the parent. A Solution without the
    orchestrator gives a `fallback` text, never a silent default."""
    orchestrator = orchestrator_module()
    if orchestrator is None:
        return {"orchestrated": False, "trigger": None, "checkpoints": [],
                "fallback": "The Solution has no orchestrator module. The agent ran alone, with no trigger."}
    parent = _parent_of(orchestrator, agent_id)
    if parent is not None:
        return {"orchestrated": True, "trigger": None, "checkpoints": [], "target": "sub_agent", "parent": parent,
                "fallback": None}
    return {"orchestrated": True, "trigger": _entry_trigger(orchestrator, agent_id),
            "checkpoints": _checkpoints_after(orchestrator, agent_id), "fallback": None}


def deterministic_output(module: Any, payload: dict[str, Any], case: dict[str, Any], trace: list[Any]) -> dict[str, Any]:
    """The answer of a deterministic agent: the OUTPUT_SCHEMA fields that its actions wrote into the case.

    A field counts as written when the case value differs from the input, or the input lacked it. An input field is never
    copied as an answer. Without a trace, or without OUTPUT_SCHEMA properties (a $ref), there is no answer: AgentOutputInvalid."""
    properties = (module.OUTPUT_SCHEMA or {}).get("properties")
    if not trace:
        raise AgentOutputInvalid("No action ran, so the deterministic agent wrote no answer")
    if not isinstance(properties, dict) or not properties:
        raise AgentOutputInvalid("OUTPUT_SCHEMA names no properties, so the fields the actions wrote cannot be told apart")
    answer = {key: case[key] for key in properties if key in case and (key not in payload or case[key] != payload[key])}
    validate(answer, module.OUTPUT_SCHEMA, getattr(module, "SCHEMA_STORE", None), AgentOutputInvalid)
    return answer


def routed_answer(route: Any) -> dict[str, Any] | None:
    """The observed answer of a routed case: the route that the exception handler gave. None when it gave no route."""
    if isinstance(route, dict):
        return {"routing": route.get("escalation_route"), **{k: v for k, v in route.items() if k != "escalation_route"}}
    return None if route is None else {"routing": route}


def start_stage(module: Any, payload: dict[str, Any], case_id: str) -> dict[str, Any] | None:
    """Run the agent `run_case` (sync). Give None when the module has no run_case with ACTIONS.

    The result holds `run_case` (trace, outcome, next, route), `case` (the merged case), and `answer`: the routed answer,
    the deterministic answer, or None when the model must still answer. The Playground and `run_stage` both call it."""
    run_case = getattr(module, "run_case", None)
    if not (callable(run_case) and getattr(module, "ACTIONS", None)):
        return None
    validate(payload, module.INPUT_SCHEMA, getattr(module, "SCHEMA_STORE", None), AgentInputInvalid)
    result = run_case(case_id, dict(payload))
    summary = {key: result.get(key) for key in ("trace", "outcome", "next", "route")}
    found: dict[str, Any] = {"run_case": summary, "case": dict(result.get("case") or {}), "answer": None}
    if result.get("outcome") != "completed":
        found["answer"] = routed_answer(result.get("route"))
    elif getattr(module, "DECISION_TYPE", None) == "deterministic":
        found["answer"] = deterministic_output(module, payload, found["case"], list(result.get("trace") or []))
    return found


def _tools_observed(module: Any, started: dict[str, Any] | None) -> bool:
    """True when every tool call of the stage was seen. The model path is seen. An action that declares tools is not."""
    if started is None:
        return True
    actions = getattr(module, "ACTIONS", None) or {}
    return not any((actions.get(a) or {}).get("tool_ids") for a in started["run_case"].get("trace") or [])


async def run_stage(agent_id: str, payload: dict[str, Any], *, correlation_id: str,
                    session_id: str | None = None) -> dict[str, Any]:
    """Run one agent as the orchestrator hands it a case. Give the stage record.

    Keys: `agent_id`, `run_case`, `answer` (None when no answer), `routed`, `carry` (the payload for the next stage:
    the case with the action writes, then the answer) and `tools_observed`. The agent `run_case` runs first. A
    deterministic agent answers from what its actions wrote. Any other agent then calls the model on the merged case."""
    module = load_agent_module(agent_id)
    stage: dict[str, Any] = {"agent_id": agent_id, "run_case": None, "answer": None, "routed": False,
                             "carry": None, "tools_observed": True}
    started = start_stage(module, payload, str(payload.get("case_id") or correlation_id))
    if started is None:
        stage["run_case_fallback"] = "The agent module has no run_case with ACTIONS. The agent runs through invoke_agent only."
        stage["answer"] = await invoke_agent(agent_id, payload, correlation_id=correlation_id, session_id=session_id)
        stage["carry"] = {**payload, **stage["answer"]}
        return stage
    stage["run_case"] = started["run_case"]
    if started["run_case"]["outcome"] != "completed":
        stage.update(routed=True, answer=started["answer"], tools_observed=_tools_observed(module, started))
        return stage
    if started["answer"] is not None:
        stage.update(answer=started["answer"], carry={**started["case"], **started["answer"]},
                     tools_observed=_tools_observed(module, started))
        return stage
    # The model sees the action writes, so it does not run those tools again.
    stage["answer"] = await invoke_agent(agent_id, started["case"], correlation_id=correlation_id, session_id=session_id)
    stage["carry"] = {**started["case"], **stage["answer"]}
    stage["tools_observed"] = _tools_observed(module, started)
    return stage


def _approving_decision(checkpoint_id: str) -> str:
    try:
        from solution.tool_policy import approving_action, declared_actions, metadata
        rows = metadata()["files"]["spec/checkpoints.yaml"]
        row = next(r for r in rows if r.get("checkpoint_id") == checkpoint_id)
        decision = approving_action(declared_actions(row))
    except Exception:  # noqa: BLE001 - the Solution may carry no checkpoint metadata
        return "none recorded (the Solution carries no checkpoint declaration)"
    return decision or "none (the checkpoint declares no approving decision)"


async def enter_case(agent_id: str, payload: dict[str, Any], *, correlation_id: str,
                     session_id: str | None = None, trigger_kind: str | None = None,
                     pass_checkpoints: bool = False) -> dict[str, Any]:
    """The entry of a case: trigger, agent run_case, checkpoint, output. Give {"output", "entry"}.

    A blank agent_id is a process-level case. The orchestrator route for the trigger gives the agents, in order. Each
    agent gets the case with the writes of the agents before it. The output is the answer of the last agent that ran.
    A routed stage ends the case with outcome "routed" and the route as the answer. The case stops with outcome "paused"
    at the first checkpoint after an agent, unless `pass_checkpoints` is true (the evals). A passed checkpoint is
    recorded in `entry` with the approving decision. A sub-agent id runs that unit directly, with no route and no
    parent (entry target 'sub_agent', parent ID); the orchestrator never routes a case to it.
    `entry` records the trigger, the route, each stage, the checkpoints and any fallback."""
    if not correlation_id:
        raise AgentInputInvalid("A correlation ID is required for every call")
    orchestrator = orchestrator_module()
    entry: dict[str, Any] = {"orchestrated": orchestrator is not None, "trigger": trigger_kind, "route": [],
                             "stages": [], "checkpoints": {}, "passed": [], "outcome": "completed", "fallback": None}
    if orchestrator is None:
        if not agent_id:
            raise OrchestratorMissing("The Solution has no orchestrator module. A process-level case cannot start without it.")
        entry["fallback"] = "The Solution has no orchestrator module. The agent ran alone, with no trigger and no route."
        route = [agent_id]
    elif agent_id:
        described = describe_entry(agent_id)
        entry["trigger"] = trigger_kind or described["trigger"]
        if described.get("target") == "sub_agent":
            # A direct run of the sub-agent unit: its own run_case, then the model. No route and no parent.
            entry.update(target="sub_agent", parent=described["parent"])
        route = [agent_id]
    else:
        triggers = getattr(orchestrator, "TRIGGERS", None) or []
        if trigger_kind is None and len(triggers) != 1:
            raise OrchestratorMissing(f"The case names no trigger kind and the orchestrator declares {len(triggers)} triggers.")
        kind = trigger_kind or str(triggers[0].get("kind"))
        entry["trigger"] = kind
        route = [str(item) for item in orchestrator.case_route(kind)]
        if not route:
            raise OrchestratorMissing(f"The orchestrator route for trigger {kind!r} is empty.")
    entry["route"] = route
    output: dict[str, Any] | None = None
    tools: list[str] | None = []
    carry = dict(payload)
    for step in route:
        _TOOLS.pop(correlation_id, None)  # one stage at a time: tool_calls then holds this stage only
        stage = await run_stage(step, carry, correlation_id=correlation_id, session_id=session_id)
        if tools is not None and stage["tools_observed"]:
            tools += _TOOLS.get(correlation_id) or []
        else:
            tools = None  # a tool call that nobody saw is unknown, never an empty list
        entry["stages"].append({k: v for k, v in stage.items() if k not in ("carry", "answer")})
        output = stage["answer"]
        if stage["routed"]:
            entry["outcome"] = "routed"
            break
        pauses = _checkpoints_after(orchestrator, step) if orchestrator is not None else []
        entry["checkpoints"][step] = pauses
        if pauses and not pass_checkpoints:
            entry["outcome"] = "paused"
            entry["paused_at"] = pauses[0]
            break
        for checkpoint in pauses:
            entry["passed"].append(f"checkpoint {checkpoint} passed for the eval with decision {_approving_decision(checkpoint)}")
        carry = stage["carry"]
    if tools is None:
        _TOOLS.pop(correlation_id, None)
    else:
        _TOOLS[correlation_id] = tools
    return {"output": output, "entry": entry}
