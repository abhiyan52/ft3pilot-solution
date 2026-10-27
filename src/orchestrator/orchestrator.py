"""Orchestrator: trigger, agent, checkpoint and output for the whole solution.

Plain Python. It holds the declared graph (orchestration.yaml) as data and lookups. ADK composes and runs the agents;
this module writes no router, retry loop or tracer. A person-owned step is handed back to a human, never to an agent.
"""

from __future__ import annotations

REQUIREMENT_REFS = ("orchestration.yaml",)

TRIGGERS = [
    {"channel": "Incoming prospect registration submission", "kind": "Inbound channel message", "starts": "BLK_01"},
]

EDGES = [
    {"from": "BLK_01", "on": "done", "to": "BLK_02"},
    {"from": "BLK_01", "on": "agent_tool", "to": "BLK_01.1"},
    {"from": "BLK_01", "on": "agent_tool", "to": "BLK_01.2"},
]

OWNERSHIP = [
    {"owner": "BLK_01", "segment": ["S1", "S2", "S3", "S4"]},
    {"owner": "BLK_02", "segment": ["S5", "S6", "S7"]},
    {"owner": "person", "segment": ["S6", "S8"]},
]

CHECKPOINTS = [
    {"agent_id": "BLK_01", "checkpoint_id": "CHK_01", "trigger": "Completion of bank details verification"},
    {"agent_id": "BLK_02", "checkpoint_id": "CHK_02", "trigger": "Generation of QC draft recommendation"},
]

OUTPUTS = [
    {"agent_id": "BLK_01", "channel": "InsureBuddy · Create and update agent record / profile"},
    {"agent_id": "BLK_02", "channel": "InsureBuddy Document Center · Upload, crop, and validate documents"},
]

# Parent agent ID -> its sub-agent IDs (from parent_agent_id in the agents list).
SUB_AGENTS = {
    "BLK_01": ["BLK_01.1", "BLK_01.2"],
}


def owner_of(step):
    """Owner of the segment that holds the step: an agent ID or "person". KeyError for an unknown step.

    A step that a person segment holds is person-owned even when an agent segment lists it too (S6 in this Precord):
    a person-owned step never goes to an agent.
    """
    owners = [segment["owner"] for segment in OWNERSHIP if step in segment["segment"]]
    if not owners:
        raise KeyError(step)
    if "person" in owners:
        return "person"
    return owners[0]


def is_person_step(step):
    return owner_of(step) == "person"


def agent_for_step(step):
    """Agent ID for the step, or None for a person-owned step."""
    owner = owner_of(step)
    return None if owner == "person" else owner


def next_agent(agent_id, outcome):
    """Target of the edge from agent_id on outcome. A list on a fan-out, None when no edge matches."""
    targets = [edge["to"] for edge in EDGES if edge["from"] == agent_id and edge["on"] == outcome]
    if not targets:
        return None
    if len(targets) == 1:
        return targets[0]
    return targets


def entry_agent(trigger_kind):
    """Agent that the trigger of that kind starts."""
    for trigger in TRIGGERS:
        if trigger["kind"] == trigger_kind:
            return trigger["starts"]
    raise KeyError(trigger_kind)


def pauses_at(agent_id):
    """Checkpoint IDs at which a case pauses after the agent."""
    return [checkpoint["checkpoint_id"] for checkpoint in CHECKPOINTS if checkpoint["agent_id"] == agent_id]


def case_route(trigger_kind):
    """Agent IDs that a case of that trigger kind runs, in order. A sub-agent runs inside its parent, never on the route."""
    route = [entry_agent(trigger_kind)]
    while True:
        last = route[-1]
        subs = SUB_AGENTS.get(last, [])
        step = None
        for edge in EDGES:
            if edge["from"] != last:
                continue
            if edge["to"] in subs or edge["to"] in route:
                continue
            step = edge["to"]
            break
        if step is None:
            return route
        route.append(step)
