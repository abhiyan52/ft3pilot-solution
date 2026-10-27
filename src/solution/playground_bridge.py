"""Wire Playground HTTP routes to agents, checkpoints, and KPIs."""
from __future__ import annotations

import importlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _paths() -> Any:
    # Imported late, so a test can load this file alone.
    return importlib.import_module("solution.playground_paths")


def _precord() -> dict[str, Any]:
    # BUG-109: package data first, then the source tree. A missing file raises a clear error.
    return _paths().precord()


def _durable() -> Any:
    """Give the PostgreSQL state store when the Solution has a database, else None (C1-3)."""
    if not os.environ.get("DATABASE_URL"):
        return None
    try:
        from solution.state import StateStore
    except ModuleNotFoundError:
        return None
    return StateStore("playground")


def _state(data: Path, key: str, default: Any) -> Any:
    durable = _durable()
    if durable is not None:
        return durable.get(key, default)
    data.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(data / "preview.sqlite") as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default


def _write(data: Path, key: str, value: Any) -> None:
    durable = _durable()
    if durable is not None:
        durable.put(key, value)
        return
    data.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(data / "preview.sqlite") as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        db.execute(
            "INSERT INTO state VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )


def _module_name(identity: str) -> str:
    return identity.lower().replace("-", "_")


def _agents(meta: dict[str, Any]) -> list[dict[str, Any]]:
    return list(meta["files"]["spec/agents.yaml"])


def _checkpoints(meta: dict[str, Any]) -> list[dict[str, Any]]:
    return list(meta["files"]["spec/checkpoints.yaml"])


def _tools(meta: dict[str, Any]) -> list[dict[str, Any]]:
    return list(meta["files"].get("spec/tools.yaml") or [])


def _top_agents(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """The agents a case runs. A sub-agent runs inside its parent and has no stage of its own."""
    return [agent for agent in _agents(meta) if not agent.get("parent_agent_id")]


def _orchestration(meta: dict[str, Any]) -> dict[str, Any]:
    rows = meta["files"].get("spec/orchestration.yaml") or []
    return rows[0] if rows and isinstance(rows[0], dict) else {}


def _orchestrator() -> Any:
    """Give the built orchestrator module, or None when C3 has not built it."""
    try:
        return importlib.import_module("orchestrator.orchestrator")
    except ModuleNotFoundError as error:
        if error.name in {"orchestrator", "orchestrator.orchestrator"}:
            return None
        raise ValueError(f"The orchestrator cannot load. Missing dependency: {error.name}") from error


def _declared_route(meta: dict[str, Any], kind: Any) -> list[str]:
    """Same rule as `solution_builder.components.c3.v2.case_route`. Keep the copies identical."""
    orchestration = _orchestration(meta)
    subs: dict[str, list[str]] = {}
    for agent in _agents(meta):
        if agent.get("parent_agent_id"):
            subs.setdefault(str(agent["parent_agent_id"]), []).append(str(agent["agent_id"]))
    entry = next((t.get("starts") for t in orchestration.get("triggers", []) if t.get("kind") == kind), None)
    route = [entry] if entry else []
    while route:
        step = next((e.get("to") for e in orchestration.get("edges", []) if e.get("from") == route[-1]
                     and e.get("to") not in subs.get(route[-1], []) and e.get("to") not in route), None)
        if step is None:
            break
        route.append(step)
    return route


def case_route(meta: dict[str, Any]) -> list[str]:
    """The agents of one case, in order. The orchestrator gives them. Without it, the Precord orchestration does."""
    triggers = _orchestration(meta).get("triggers") or []
    if not triggers:
        return [agent["agent_id"] for agent in _top_agents(meta)]
    kind = triggers[0].get("kind")
    module = _orchestrator()
    route = module.case_route(kind) if module is not None and hasattr(module, "case_route") else _declared_route(meta, kind)
    return list(route)


def _pauses(meta: dict[str, Any], agent_id: str) -> list[str]:
    known = {row["checkpoint_id"] for row in _checkpoints(meta)}
    module = _orchestrator()
    if module is not None and hasattr(module, "pauses_at"):
        return [cid for cid in module.pauses_at(agent_id) if cid in known]
    return [row["checkpoint_id"] for row in _checkpoints(meta) if row.get("agent_id") == agent_id]


def process_order(meta: dict[str, Any]) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    for agent_id in case_route(meta):
        stages.append({"kind": "agent", "agentId": agent_id})
        for checkpoint_id in _pauses(meta, agent_id):
            stages.append({"kind": "review", "checkpointId": checkpoint_id})
    return stages


def declared_triggers(meta: dict[str, Any] | None = None) -> list[dict[str, str]]:
    if meta is None:
        try:
            meta = _precord()
        except FileNotFoundError:
            return []
    rows = []
    for agent in _top_agents(meta):
        cue = str(agent.get("trigger") or "").strip()
        rows.append(
            {
                "id": f"agent:{agent['agent_id']}",
                "agent_id": agent["agent_id"],
                "cue": cue or "The Precord does not name a live trigger endpoint.",
            }
        )
    return rows


def _agent_name(meta: dict[str, Any], agent_id: str) -> str:
    for agent in _agents(meta):
        if agent["agent_id"] == agent_id:
            return str(agent.get("name") or agent_id)
    return agent_id


# Same definition as `solution_builder.components.c5.planner` (REJECT_WORDS, is_reject, declared_actions,
# approving_action). A pack template runs in the generated solution, so it keeps its own copy. Keep the copies identical.
REJECT_WORDS = {"reject", "rejected", "decline", "declined", "deny", "denied", "refuse", "refused", "return",
                "discard", "dismiss"}


def is_reject(action: Any) -> bool:
    """A reject action starts with a reject word. "Reject draft" and "Dismiss" are rejects, "Release" is not."""
    words = str(action).strip().lower().split()
    return bool(words) and words[0] in REJECT_WORDS


def declared_actions(checkpoint: dict[str, Any]) -> list[Any]:
    """C5-4: v2 offers exactly `decisions[].action`, even when the list is empty (BUG-094).

    Only a v1 row, which has no `decisions` key, lists `actions`. A v2 row never falls back to `actions`."""
    if "decisions" in checkpoint:
        return [d.get("action") if isinstance(d, dict) else d for d in checkpoint["decisions"] or []]
    return list(checkpoint.get("actions") or [])


def approving_action(actions: list) -> str | None:
    """Give the FIRST declared action, or None when the row declares none or the first is a reject word (BUG-094, U4)."""
    return str(actions[0]) if actions and not is_reject(actions[0]) else None


def _checkpoint(meta: dict[str, Any], checkpoint_id: str) -> dict[str, Any]:
    for row in _checkpoints(meta):
        if row["checkpoint_id"] == checkpoint_id:
            return row
    raise ValueError(f"Unknown checkpoint {checkpoint_id}")


def _stage_name(meta: dict[str, Any], stage: dict[str, Any]) -> str:
    if stage["kind"] == "agent":
        return _agent_name(meta, stage["agentId"])
    return _checkpoint(meta, stage["checkpointId"]).get("checkpoint_id", "review")


def _fidelity(meta: dict[str, Any]) -> str:
    return meta["build"].get("systemFidelity", "mock system")


def _output(agent_id: str, payload: dict[str, str], *, invoked: bool) -> dict[str, Any]:
    fields = [
        {"label": key, "value": value}
        for key, value in payload.items()
        if value != ""
    ]
    body = {"agent": agent_id, "input": payload, "output": payload, "invoked": invoked}
    note = "" if invoked else "; agent not invoked"
    return {
        "fields": fields,
        "raw": {"json": json.dumps(body, indent=2)},
        "summary": f"read {len(fields)} {'field' if len(fields) == 1 else 'fields'}{note}",
        "invoked": invoked,
    }


def _short_error(error: BaseException) -> str:
    line = str(error).split("\n", 1)[0].strip()
    if len(line) > 160:
        return line[:157] + "..."
    return line


def _run_agent(agent_id: str, payload: dict[str, str], *, case_id: str = "") -> dict[str, Any]:
    name = _module_name(agent_id)
    try:
        module = importlib.import_module(f"agents.{name}")
    except ModuleNotFoundError as error:
        if error.name in {"agents", f"agents.{name}"}:
            return _output(agent_id, payload, invoked=False)
        raise ValueError(f"Agent {agent_id} cannot load. Missing dependency: {error.name}") from error
    validate = getattr(module, "validate_input", None) or getattr(module, "validate_agent_input", None)
    if callable(validate):
        try:
            validate(payload)
        except Exception as error:
            raise ValueError(
                f"Agent {agent_id} rejected the case input. {_short_error(error)}"
            ) from error
    run = getattr(module, "run", None)
    if callable(run):
        result = run(payload)
        if isinstance(result, dict) and "summary" in result:
            result.setdefault("invoked", True)
            return result
    entry, early, payload = _enter(agent_id, module, payload, case_id)
    if early is not None:
        early["entry"] = entry
        return early
    make_agent = getattr(module, "make_agent", None)
    if callable(make_agent):
        from solution.preview_adk import invoke_make_agent

        try:
            result = invoke_make_agent(module, agent_id, payload, case_id=case_id)
        except RuntimeError as error:
            raise ValueError(_short_error(error)) from error
        result["entry"] = entry
        return result
    result = _output(agent_id, payload, invoked=False)
    result["entry"] = entry
    return result


def _enter(agent_id: str, module: Any, payload: dict[str, Any], case_id: str) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    """BUG-082: enter the agent as the orchestrator does. The runtime owns the rules: trigger, checkpoints, run_case.

    The bridge imports `solution.agent_runtime` at call time and calls `describe_entry` and `start_stage`. It keeps no copy.
    Give the entry record, the stage result when run_case ends the stage (routed, or a deterministic answer; else None),
    and the payload for the model, which holds the action writes. An older Solution without agent_runtime is recorded
    in `entry.fallback`: no action path ran."""
    try:
        from solution import agent_runtime
    except ModuleNotFoundError as error:
        if error.name not in {"solution", "solution.agent_runtime"}:
            raise
        return {"orchestrated": False, "trigger": None, "checkpoints": [], "run_case": None,
                "fallback": ["The Solution has no agent_runtime (an older build). No orchestrator entry and no run_case ran."]}, None, payload
    entry = agent_runtime.describe_entry(agent_id)
    entry = {**entry, "fallback": [entry["fallback"]] if entry.get("fallback") else [], "run_case": None}
    identity = str(payload.get("case_id") or case_id or "preview")
    try:
        started = agent_runtime.start_stage(module, payload, identity, agent_id)
    except Exception as error:
        raise ValueError(f"Agent {agent_id} run_case failed. {_short_error(error)}") from error
    if started is None:
        entry["fallback"].append("The agent module has no run_case with ACTIONS. No action path ran.")
        return entry, None, payload
    entry["run_case"] = started["run_case"]
    answer = started["answer"]
    if started["run_case"]["outcome"] != "completed":
        body = {"agent": agent_id, "input": payload, "run_case": started["run_case"], "output": answer}
        early = {"fields": [{"label": key, "value": json.dumps(value, default=str)} for key, value in (answer or {}).items()],
                 "raw": {"json": json.dumps(body, indent=2, default=str)}, "invoked": True, "outcome": "routed",
                 "summary": f"run_case routed the case after {started['run_case']['trace']}; the agent was not asked"}
        if answer is not None:
            early["output"] = answer
        return entry, early, payload
    if answer is not None:
        early = {"fields": [{"label": key, "value": json.dumps(value, default=str)} for key, value in answer.items()],
                 "raw": {"json": json.dumps({"agent": agent_id, "output": answer}, indent=2, default=str)},
                 "summary": f"run_case completed {started['run_case']['trace']}; a deterministic agent needs no model",
                 "output": answer, "invoked": True}
        return entry, early, payload
    return entry, None, started["case"]


def _synthetic_cases(meta: dict[str, Any]) -> list[dict[str, Any]]:
    cases = _state_cases_from_evals(meta)
    if not cases:
        inputs = {agent["agent_id"]: {} for agent in _top_agents(meta)}
        cases = [{
            "id": "DEV-01",
            "description": "Development case from the Closed Precord",
            "inputs": inputs,
        }]
    schemas = meta["files"].get("inputSchemas") or {}
    runnable = []
    for case in cases:
        try:
            if all(
                Draft202012Validator(schemas[agent["agent_id"]]).is_valid(
                    case.get("inputs", {}).get(agent["agent_id"], {})
                )
                for agent in _top_agents(meta)
            ):
                runnable.append(case)
        except (KeyError, TypeError, ValueError):
            continue
    return runnable


def _state_cases_from_evals(meta: dict[str, Any]) -> list[dict[str, Any]]:
    # A v2 Precord carries its eval cases in the frozen data (evals/cases.jsonl). Its `input` is prose, so it is the description.
    frozen = meta["files"].get("evalCases") or []
    if frozen:
        return [
            {
                "id": str(row["case_id"]),
                "description": str(row.get("input") or row["case_id"]),
                "inputs": {str(row["agent_id"]): {}} if row.get("agent_id") else {},
            }
            for row in frozen
            if row.get("case_id")
        ]
    path = _root() / "evals" / "cases.csv"
    if not path.is_file():
        return []
    lines = path.read_text().splitlines()
    if len(lines) < 2:
        return []
    header = [part.strip() for part in lines[0].split(",")]
    rows = []
    for line in lines[1:]:
        parts = [part.strip() for part in line.split(",")]
        record = dict(zip(header, parts, strict=False))
        case_id = record.get("case_id") or record.get("id")
        if not case_id:
            continue
        agent_id = record.get("agent_id") or _agents(meta)[0]["agent_id"]
        rows.append(
            {
                "id": case_id,
                "description": record.get("input") or record.get("description") or case_id,
                "inputs": {agent_id: {}},
            }
        )
    return rows


def _walks(data: Path) -> list[dict[str, Any]]:
    return _state(data, "walks", [])


def _runs(data: Path) -> list[dict[str, Any]]:
    return _state(data, "runs", [])


def _new_walk(meta: dict[str, Any], body: dict[str, Any], data: Path) -> dict[str, Any]:
    source = body.get("source") or {}
    cases = _synthetic_cases(meta)
    if source.get("kind") == "synthetic":
        case_id = source.get("caseId")
        found = next((row for row in cases if row["id"] == case_id), None)
        if found is None:
            raise ValueError(f"Unknown case {case_id}")
        description = found["description"]
        kind = "synthetic"
    else:
        files = source.get("files") or []
        names = [str(item.get("name") or "") for item in files]
        case_id = f"UP-{len(_walks(data)) + 1:04d}"
        description = source.get("description") or ", ".join(names) or "uploaded case"
        kind = "uploaded"
    order = process_order(meta)
    steps = [
        {
            "index": index + 1,
            "stage": stage,
            "name": _stage_name(meta, stage),
            "status": "next",
            "built": True,
        }
        for index, stage in enumerate(order)
    ]
    at = _now()
    walk = {
        "id": f"walk-{case_id}-{at}",
        "caseId": case_id,
        "caseKind": kind,
        "description": description,
        "startedAt": at,
        "updatedAt": at,
        "fidelity": ["synthetic case" if kind == "synthetic" else "uploaded case", _fidelity(meta)],
        "steps": steps,
        "status": "running",
        "decisions": [],
    }
    walks = [walk, *_walks(data)]
    _write(data, "walks", walks)
    return walk


def _find_walk(data: Path, walk_id: str) -> dict[str, Any]:
    for walk in _walks(data):
        if walk["id"] == walk_id:
            return walk
    raise ValueError(f"Unknown walk {walk_id}")


def _save_walk(data: Path, walk: dict[str, Any]) -> None:
    walks = [walk if row["id"] == walk["id"] else row for row in _walks(data)]
    _write(data, "walks", walks)


def _review(meta: dict[str, Any], walk: dict[str, Any], checkpoint_id: str) -> dict[str, Any]:
    row = _checkpoint(meta, checkpoint_id)
    output = next(((step.get("output") or {}).get("output") for step in reversed(walk["steps"])
                   if isinstance((step.get("output") or {}).get("output"), dict)), {})
    fields = {key: output[key] for key in row.get("shown") or [] if key in output}
    store = _checkpoint_store()
    try:
        record = store.read(walk["caseId"])
    except LookupError:
        try:
            record = store.create(walk["caseId"], fields, checkpoint_id=checkpoint_id)
        except TypeError:
            record = store.create(walk["caseId"], fields)  # an older store opens at the first checkpoint
    values = record.get("fields") or {}
    shown = [{"label": key, "value": json.dumps(values[key]) if isinstance(values.get(key), (dict, list))
              else str(values[key]) if values.get(key) is not None else "unknown"}
             for key in row.get("shown") or []]
    return {
        "walkId": walk["id"],
        "checkpointId": checkpoint_id,
        "name": row.get("checkpoint_id"),
        "reason": row.get("reason", ""),
        "reviewerRole": row.get("reviewer_role") or None,
        "shown": shown,
        "actions": declared_actions(row),
        "capture": row.get("capture") or [],
        "caseId": walk["caseId"],
        "version": record["version"],
    }


def _reviewer(body: dict[str, Any], data: Path) -> str:
    """Name the person who decides a review: the body, else the user of the Playground session."""
    if body.get("actor"):
        return str(body["actor"])
    user = _state(data, "user", None) or {}
    return str(user.get("id") or "preview-operator")


def _checkpoint_store() -> Any:
    """Give the one CheckpointStore of this process. A new store for each call lost the state."""
    from solution.tool_policy import checkpoint_store
    return checkpoint_store()


def _apply_checkpoint(case_id: str, action: str, actor: str = "playground", reason: str = "",
                      *, expected_version: int | None = None, role: str | None = None) -> dict[str, Any]:
    """Apply a review decision to the C5 store. Give the result. A failure is visible, not swallowed."""
    try:
        store = _checkpoint_store()
    except ModuleNotFoundError:
        return {"applied": False, "error": "C5 checkpoints are not built"}
    try:
        if expected_version is not None:
            version = expected_version
        else:
            try:
                version = store.read(case_id).get("version", 1)
            except LookupError:
                store.create(case_id, {})
                version = store.read(case_id).get("version", 1)
        try:
            store.apply(case_id, version, action, {}, actor=actor, reason=reason, role=role)
        except TypeError:
            store.apply(case_id, version, action, {})  # an older store takes no actor
    except Exception as error:
        return {"applied": False, "error": f"{type(error).__name__}: {error}"}
    return {"applied": True, "error": None}


def _advance(meta: dict[str, Any], walk: dict[str, Any], data: Path, pass_overrides: bool) -> bool:
    step = next((row for row in walk["steps"] if row["status"] not in ("done", "skipped")), None)
    if step is None:
        walk["status"] = "done"
        walk["pendingReview"] = None
        walk["updatedAt"] = _now()
        walk["finalState"] = [
            field
            for row in walk["steps"]
            for field in (row.get("output") or {}).get("fields") or []
        ]
        return False
    walk["updatedAt"] = _now()
    stage = step["stage"]
    if stage["kind"] == "agent":
        cases = {row["id"]: row for row in _synthetic_cases(meta)}
        payload = (cases.get(walk["caseId"]) or {}).get("inputs", {}).get(stage["agentId"], {})
        step["output"] = _run_agent(stage["agentId"], payload, case_id=walk["caseId"])
        step["summary"] = step["output"]["summary"]
        step["status"] = "done"
        if step["output"].get("outcome") == "routed":
            # The agent run_case routed the case (BUG-082). The walk ends here. Later stages do not run.
            for later in walk["steps"]:
                if later["status"] not in ("done", "skipped"):
                    later["status"] = "skipped"
                    later["summary"] = "not run: the case was routed"
            walk["routed"] = step["output"].get("output")
        return True
    row = _checkpoint(meta, stage["checkpointId"])
    mode = row.get("mode") or "pause"
    if mode == "override" and pass_overrides:
        step["status"] = "done"
        step["summary"] = "continued, can be overridden later"
        return True
    step["status"] = "waiting"
    walk["status"] = "waiting"
    walk["pendingReview"] = _review(meta, walk, stage["checkpointId"])
    return False


def _kpis(meta: dict[str, Any], data: Path) -> dict[str, Any]:
    fidelity = ["this environment", _fidelity(meta)]
    dashboard: dict[str, Any] = {"kind": "not_built"}
    try:
        service = importlib.import_module("kpis.service")
    except ModuleNotFoundError:
        return {
            "fidelity": fidelity,
            "dashboard": dashboard,
            "casesWalked": len(_walks(data)),
        }
    store_cls = getattr(service, "KpiEventStore", None)
    payload_fn = getattr(service, "playground_kpis_payload", None)
    html = _root() / "ui" / "kpis" / "index.html"
    if html.is_file():
        dashboard = {"kind": "url", "src": "/ui/kpis/index.html"}
    if store_cls is None or payload_fn is None:
        return {"fidelity": fidelity, "dashboard": dashboard, "casesWalked": len(_walks(data))}
    try:
        # BUG-085: the generated store keeps memory when it gets no path. Open the file that the producer feeds.
        try:
            store = store_cls(data / "kpis.sqlite")
        except TypeError:
            store = store_cls()
        snap = payload_fn(store)
    except TypeError:
        return {"fidelity": fidelity, "dashboard": dashboard, "casesWalked": len(_walks(data))}
    if not isinstance(snap, dict):
        snap = {}
    src = (snap.get("dashboard") or {}).get("src") or dashboard.get("src") or "/ui/kpis/index.html"
    payload = dict(snap)
    payload["fidelity"] = snap.get("fidelity") or fidelity
    payload["dashboard"] = {"kind": "url", "src": src} if html.is_file() or snap.get("dashboard") else dashboard
    payload["casesWalked"] = len(_walks(data))
    return payload


def _request_meta() -> dict[str, Any]:
    try:
        return dict(_precord()["files"].get("informationRequest") or {})
    except (FileNotFoundError, KeyError):
        return {}


def _status(meta: dict[str, Any], probed: bool) -> dict[str, Any]:
    statuses = []
    for tool in _tools(meta):
        mocked = bool(tool.get("mock")) or "__MOCK__" in str(tool.get("endpoint") or "")
        statuses.append(
            {
                "integrationId": tool.get("tool_id"),
                "status": "MOCKED" if mocked else "LIVE",
                "reason": tool.get("mock_reason") if mocked else None,
            }
        )
    # D-5: the schema version and the request hash make a repeated information request detectable.
    request = _request_meta()
    return {"schemaVersion": 1, "requestHash": request.get("content_hash"), "probedAt": _now() if probed else "",
            "statuses": statuses}


def _shown(report: dict[str, Any]) -> dict[str, Any]:
    """BUG-109: add the problems that exist now. A saved report never keeps them, so a fixed problem goes away."""
    shown = {key: value for key, value in report.items() if key != "problems"}
    if _paths().problems():
        shown["problems"] = _paths().problems()
    return shown


def _evals(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "datasetSize": 0,
        "datasetSource": meta["files"].get("evalsSource"),
        "perAgent": [],
        "wholeSolution": [],
        "fidelity": ["this environment", _fidelity(meta)],
    }


def _pending(data: Path) -> list[dict[str, Any]]:
    rows = []
    for walk in _walks(data):
        review = walk.get("pendingReview")
        if not review:
            continue
        rows.append(
            {
                "walkId": walk["id"],
                "caseId": walk["caseId"],
                "caseLabel": walk["description"],
                "checkpointId": review["checkpointId"],
                "reason": review.get("reason", ""),
                "at": walk["updatedAt"],
            }
        )
    return rows


def dispatch(method: str, route: str, body: dict[str, Any], data_dir: Path) -> Any:
    """Serve one Playground route. Raise LookupError when the path is unknown."""
    meta = _precord()
    data = Path(data_dir)
    parts = [part for part in route.split("/") if part]
    if not parts:
        raise LookupError(route)

    if parts[0] == "agents" and len(parts) >= 3:
        agent_id = parts[1]
        leaf = parts[2]
        if leaf == "runs" and method == "GET":
            return [row for row in _runs(data) if row.get("agentId") == agent_id][:5]
        if leaf == "runs" and method == "POST":
            payload = dict(body.get("input") or {})
            source = body.get("source") or {"kind": "synthetic", "caseId": "DEV-01"}
            output = _run_agent(agent_id, payload, case_id=str(source.get('caseId') or ''))
            fidelity = ["uploaded case" if source.get("kind") == "uploaded" else "synthetic case", _fidelity(meta)]
            if not output.get("invoked"):
                fidelity.append("agent not invoked")
            run = {
                "runNumber": len(_runs(data)) + 1,
                "agentId": agent_id,
                "startedAt": _now(),
                "input": payload,
                "source": source
                if source.get("kind") == "synthetic"
                else {"kind": "uploaded", "fileNames": [str(item.get("name") or "") for item in source.get("files") or []]},
                "output": output,
                "fidelity": fidelity,
            }
            _write(data, "runs", [run, *_runs(data)])
            return run
        if leaf == "evals" and method == "GET":
            return {"agentId": agent_id, "measures": []}
        if leaf == "example" and method == "GET":
            cases = _synthetic_cases(meta)
            return cases[0] if cases else None
        raise LookupError(route)

    if parts == ["cases"] and method == "GET":
        return _synthetic_cases(meta)
    if parts == ["walks"] and method == "GET":
        return [
            {"id": row["id"], "caseId": row["caseId"], "caseKind": row["caseKind"], "updatedAt": row["updatedAt"]}
            for row in _walks(data)[:10]
        ]
    if parts == ["walks"] and method == "POST":
        return _new_walk(meta, body, data)
    if len(parts) == 2 and parts[0] == "walks" and method == "GET":
        return _find_walk(data, parts[1])
    if len(parts) == 3 and parts[0] == "walks" and parts[2] == "step" and method == "POST":
        walk = _find_walk(data, parts[1])
        _advance(meta, walk, data, False)
        _save_walk(data, walk)
        return walk
    if len(parts) == 3 and parts[0] == "walks" and parts[2] == "run" and method == "POST":
        walk = _find_walk(data, parts[1])
        while walk["status"] == "running":
            if not _advance(meta, walk, data, True):
                break
            if all(step["status"] in ("done", "skipped") for step in walk["steps"]):
                walk["status"] = "done"
                walk["pendingReview"] = None
                walk["updatedAt"] = _now()
                break
        _save_walk(data, walk)
        return walk
    if len(parts) == 3 and parts[0] == "walks" and parts[2] == "decisions" and method == "POST":
        if body.get("walkId") and body["walkId"] != parts[1]:
            raise ValueError("The decision belongs to a different walk")
        walk = _find_walk(data, parts[1])
        action = str(body.get("action") or "")
        checkpoint_id = str(body.get("checkpointId") or "")
        step = next((row for row in walk["steps"] if row["status"] == "waiting"), None)
        if step is None:
            raise ValueError("No waiting review")
        review = walk.get("pendingReview") or {}
        if checkpoint_id != step["stage"]["checkpointId"] or checkpoint_id != review.get("checkpointId"):
            raise ValueError("The decision belongs to a different checkpoint")
        declared = declared_actions(_checkpoint(meta, checkpoint_id))
        if action not in declared:
            raise ValueError("Undeclared checkpoint action")
        if not isinstance(review.get("version"), int):
            raise ValueError("The checkpoint review has no version. Open a new review.")
        walk["checkpointApply"] = _apply_checkpoint(walk["caseId"], action, _reviewer(body, data),
                                                    str(body.get("note") or ""), expected_version=review["version"],
                                                    role=review.get("reviewerRole"))
        if not walk["checkpointApply"]["applied"]:
            _save_walk(data, walk)
            return walk
        if action != approving_action(declared):
            review["version"] += 1
            walk["updatedAt"] = _now()
            _save_walk(data, walk)
            return walk
        step["status"] = "done"
        step["decision"] = {
            "checkpointId": checkpoint_id,
            "action": action,
            "note": body.get("note"),
            "at": _now(),
        }
        walk["decisions"] = [*walk["decisions"], step["decision"]]
        walk["pendingReview"] = None
        walk["status"] = "running"
        walk["updatedAt"] = _now()
        _save_walk(data, walk)
        return walk
    if parts == ["evals"] and method == "GET":
        return _evals(meta)
    if parts == ["evals", "run"] and method == "POST":
        return _evals(meta)
    if parts == ["kpis"] and method == "GET":
        return _kpis(meta, data)
    if parts == ["status"] and method == "GET":
        last = _state(data, "status", None)
        return _shown(last if last is not None else _status(meta, False))
    if parts == ["status", "probe"] and method == "POST":
        report = _status(meta, True)
        _write(data, "status", report)
        return _shown(report)
    if parts == ["status", "export"] and method == "GET":
        report = _shown(_state(data, "status", None) or _status(meta, False))
        text = json.dumps(report, indent=2)
        return {"fileName": "solution-status.json", "mimeType": "application/json", "content": text}
    if parts == ["status", "information-request"] and method == "GET":
        request = dict(meta["files"].get("informationRequest") or {})
        return {"fileName": f"information-request-v{request.get('schema_version', 1)}.json",
                "mimeType": "application/json", "content": json.dumps(request, indent=2)}
    if parts == ["reviews", "pending"] and method == "GET":
        return _pending(data)
    if parts == ["triggers"] and method == "GET":
        return declared_triggers(meta)
    raise LookupError(route)
