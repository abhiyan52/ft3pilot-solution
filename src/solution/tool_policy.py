"""Protect declared writes with the recorded C5 decision and approved field values."""
from __future__ import annotations

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


def install(agent: Any, agent_id: str, case_id: str, metadata: dict[str, Any],
            read_record: Callable[[str], dict[str, Any] | None] = checkpoint_record,
            bindings: dict[str, str] | None = None) -> None:
    files = metadata['files']
    declaration = next(row for row in files['spec/agents.yaml'] if row['agent_id'] == agent_id)
    tool_ids = set(declaration.get('tools') or [])
    # A stub or mock has no tools.yaml row. Its contract comes from spec/stubs.yaml (BUG-080). tools.yaml wins.
    tools = {row['tool_id']: row for row in files.get('spec/stubs.yaml') or []}
    tools.update({row['tool_id']: row for row in files['spec/tools.yaml']})
    checkpoints = [row for row in files['spec/checkpoints.yaml']
                   if row.get('agent_id') == agent_id and row.get('required', True)]
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
    needs_review = bool(checkpoints) or declaration.get('autonomy') == 'draft_for_approval'

    def before_tool(*, tool: Any, args: dict[str, Any], tool_context: Any) -> None:
        if tool.name not in mapped:
            return None  # ADK also uses its own structured response tool.
        if tool.name in protected and needs_review:
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
