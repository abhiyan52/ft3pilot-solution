"""Protect declared writes with the recorded C5 decision and approved field values."""
from __future__ import annotations

import contextlib
import inspect
import importlib
import json
from pathlib import Path
from typing import Any, Callable


_STORES: dict[int, Any] = {}

# Same definition as `solution_builder.components.c5.planner` (REJECT_WORDS, is_reject, declared_actions,
# approving_action). A pack template runs in the generated solution, so it keeps its own copy. Keep the copies identical.
REJECT_WORDS = {'reject', 'rejected', 'decline', 'declined', 'deny', 'denied', 'refuse', 'refused', 'return',
                'discard', 'dismiss'}


def is_reject(action: Any) -> bool:
    """A reject action starts with a reject word. "Reject draft" and "Dismiss" are rejects, "Release" is not."""
    words = str(action).strip().lower().split()
    return bool(words) and words[0] in REJECT_WORDS


def declared_actions(checkpoint: dict[str, Any]) -> list[Any]:
    """C5-4: v2 offers exactly `decisions[].action`, even when the list is empty (BUG-094).

    Only a v1 row, which has no `decisions` key, lists `actions`. A v2 row never falls back to `actions`."""
    if "decisions" in checkpoint:
        return [d.get('action') if isinstance(d, dict) else d for d in checkpoint["decisions"] or []]
    return list(checkpoint.get('actions') or [])


def approving_action(actions: list) -> str | None:
    """Give the FIRST declared action, or None when the row declares none or the first is a reject word (BUG-094, U4)."""
    return str(actions[0]) if actions and not is_reject(actions[0]) else None


def metadata() -> dict[str, Any]:
    return json.loads(Path(__file__).with_name('tool_policy.json').read_text())


def checkpoint_store() -> Any:
    module = importlib.import_module('checkpoints.service')
    if id(module) not in _STORES:
        _STORES[id(module)] = module.CheckpointStore()
    return _STORES[id(module)]


def checkpoint_record(case_id: str) -> dict[str, Any] | None:

    try:
        store = checkpoint_store()
        record = store.read(case_id)
        if not isinstance(record, dict):
            return None
        return {**record, 'decisions': store.decisions(case_id)}
    except (ModuleNotFoundError, LookupError):
        return None


def _context(agent_id: str, metadata: dict[str, Any]) -> tuple[set[str], dict[str, Any], list[dict[str, Any]], bool]:
    """The declared tools of one agent, every tool contract, the required checkpoints and whether a write needs review."""
    files = metadata['files']
    declaration = next((row for row in files['spec/agents.yaml'] if row['agent_id'] == agent_id), None)
    if declaration is None:
        raise ValueError(f'The agent {agent_id!r} has no row in spec/agents.yaml, so its tool calls have no policy')
    tool_ids = set(declaration.get('tools') or [])
    # A stub or mock has no tools.yaml row. Its contract comes from spec/stubs.yaml (BUG-080). tools.yaml wins.
    tools = {row['tool_id']: row for row in files.get('spec/stubs.yaml') or []}
    tools.update({row['tool_id']: row for row in files['spec/tools.yaml']})
    checkpoints = [row for row in files['spec/checkpoints.yaml']
                   if row.get('agent_id') == agent_id and row.get('required', True)]
    return tool_ids, tools, checkpoints, bool(checkpoints) or declaration.get('autonomy') == 'draft_for_approval'


def _require_approval(case_id: str, checkpoints: list[dict[str, Any]], read_record: Callable[[str], dict[str, Any] | None],
                      args: dict[str, Any]) -> None:
    """Raise PermissionError unless the case has a recorded human approval that matches the payload (one policy, BUG-117)."""
    record = read_record(case_id) if case_id else None
    if not checkpoints or not record or record.get('state') != 'approved':
        raise PermissionError('A protected write requires recorded human approval for this case')
    decisions = record.get('decisions') or []
    latest = decisions[-1] if decisions else {}
    row = next((r for r in checkpoints if r['checkpoint_id'] == latest.get('checkpoint_id')), {})
    approve = approving_action(declared_actions(row))
    if approve is None:
        raise PermissionError('The checkpoint declares no approving decision, so no write is released')
    if not latest.get('actor') or latest.get('action') != approve \
            or latest.get('version_after') != record.get('version'):
        raise PermissionError('The human approval does not match the current case version')
    if any(row['checkpoint_id'] != latest.get('checkpoint_id') for row in checkpoints):
        raise PermissionError('The approval belongs to a different checkpoint')
    payload = args.get('payload')
    if not isinstance(payload, dict):
        raise PermissionError('The protected tool has no structured payload to compare with approval')
    fields = record.get('fields') or {}
    # Legacy generated code reads this claim. The claim grants no permission here.
    proposed = {key: value for key, value in payload.items() if key != 'checkpoint'}
    if not proposed or any(key not in fields or fields[key] != value for key, value in proposed.items()):
        raise PermissionError('The proposed write differs from the approved fields')


def install(agent: Any, agent_id: str, case_id: str, metadata: dict[str, Any],
            read_record: Callable[[str], dict[str, Any] | None] = checkpoint_record,
            bindings: dict[str, str] | None = None) -> None:
    tool_ids, tools, checkpoints, needs_review = _context(agent_id, metadata)
    names = [getattr(tool, 'name', None) or getattr(tool, '__name__', '') for tool in agent.tools]
    if any(not name for name in names):
        raise ValueError('The runtime cannot identify a declared tool')
    mapped = dict(bindings or {})
    if len(tool_ids) == 1 and bindings is None:
        mapped = {name: next(iter(tool_ids)) for name in names}
    if set(mapped) != set(names) or not set(mapped.values()) <= tool_ids:
        raise ValueError('TOOL_BINDINGS must map each registered callable to its declared tool ID')
    if tool_ids - set(tools):
        raise ValueError('A registered tool has no declared contract')
    protected = {name for name, identity in mapped.items() if tools[identity].get('kind') in {'write', 'read_write'}}

    def before_tool(*, tool: Any, args: dict[str, Any], tool_context: Any) -> None:
        if tool.name not in mapped:
            return None  # ADK also uses its own structured response tool.
        if tool.name in protected and needs_review:
            _require_approval(case_id, checkpoints, read_record, args)
        function = getattr(tool, 'func', None)
        if function is not None and 'correlation_id' in inspect.signature(function).parameters:
            correlation_id = getattr(tool_context, 'invocation_id', None)
            if not correlation_id:
                raise ValueError('The host invocation has no correlation ID')
            args['correlation_id'] = correlation_id
        return None

    existing = getattr(agent, 'before_tool_callback', None)
    callbacks = existing if isinstance(existing, list) else [existing] if existing else []
    agent.before_tool_callback = [*callbacks, before_tool]


@contextlib.contextmanager
def guarded_actions(module: Any, agent_id: str, case_id: str, metadata: dict[str, Any] | None = None,
                    read_record: Callable[[str], dict[str, Any] | None] = checkpoint_record):
    """Put the tool policy in front of every tool call that the actions of `run_case` make (BUG-117).

    `install` guards the ADK tool calls only. An action calls its tool itself: through a TOOL_BINDINGS callable of the
    agent module, or through `invoke` of `integrations.<tool id>`. While the block runs, each such callable is a
    wrapper that applies the same rule as `install` (same `_require_approval`, no second copy). A write or read_write
    tool without a recorded approval raises PermissionError. A read tool passes. The block restores every original."""
    actions = getattr(module, 'ACTIONS', None) or {}
    bindings = getattr(module, 'TOOL_BINDINGS', None) or {}
    action_tools = {str(t) for a in actions.values() if isinstance(a, dict) for t in a.get('tool_ids') or []}
    if not bindings and not action_tools:
        yield
        return
    tool_ids, tools, checkpoints, needs_review = _context(agent_id, metadata if metadata is not None else globals()['metadata']())
    unknown = (action_tools | set(map(str, bindings.values()))) - set(tools)
    if unknown:
        raise ValueError(f'A tool of an action has no declared contract: {sorted(unknown)}')
    scope = vars(module)
    swaps: list[tuple[dict[str, Any], str, Any]] = []
    made: dict[int, Callable[..., Any]] = {}

    def wrap(original: Callable[..., Any], tool_id: str) -> Callable[..., Any]:
        if id(original) in made:
            return made[id(original)]
        protected = tools[tool_id].get('kind') in {'write', 'read_write'} and needs_review

        def guarded(*args: Any, **kwargs: Any) -> Any:
            if protected:
                payload = kwargs['payload'] if 'payload' in kwargs else args[0] if args else None
                _require_approval(case_id, checkpoints, read_record, {'payload': payload})
            return original(*args, **kwargs)

        guarded.__name__ = getattr(original, '__name__', 'guarded')
        made[id(original)] = guarded
        return guarded

    def swap(holder: dict[str, Any], name: str, tool_id: str) -> None:
        original = holder.get(name)
        if callable(original) and not getattr(original, '__wrapped_by_policy__', False):
            swaps.append((holder, name, original))
            holder[name] = wrap(original, tool_id)
            holder[name].__wrapped_by_policy__ = True

    for name, identity in bindings.items():
        swap(scope, name, str(identity))
    originals: dict[int, str] = {}
    for tool_id in sorted(action_tools):
        try:
            integration = importlib.import_module('integrations.' + tool_id.lower().replace('-', '_').replace('.', '_'))
        except ModuleNotFoundError:
            continue
        invoke = getattr(integration, 'invoke', None)
        if not callable(invoke):
            continue
        originals[id(invoke)] = tool_id
        swap(vars(integration), 'invoke', tool_id)
    # An action may import invoke at module level: the module global then holds the same function.
    for name, value in list(scope.items()):
        if id(value) in originals and not getattr(value, '__wrapped_by_policy__', False):
            swap(scope, name, originals[id(value)])
    try:
        yield
    finally:
        for holder, name, original in reversed(swaps):
            holder[name] = original
