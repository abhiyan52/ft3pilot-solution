"""Orchestrator for the Solution (orchestration.yaml, version 1): trigger, agent, checkpoint and output.

The declared graph is held here as data and lookups. ADK composes and runs the agents; this module writes no router,
no retry loop and no tracing. `solution.agent_runtime.enter_case` reads TRIGGERS, case_route and pauses_at.
A sub-agent (BLK_01.1, BLK_01.2) runs inside its parent through ADK composition and is never on a case route.

Ownership names S6 twice: in the BLK_02 segment and in a person segment. S6 is in the not-automated register
(EX_01, regulatory), so the person segment wins and S6 never goes to an agent. The conflict is reported as a
contradiction and a deviation for Module 1 to settle."""
from __future__ import annotations

from typing import Any

REQUIREMENT_REFS: tuple[str, ...] = (
    "orchestration.yaml",
    "precord_agents",
    "agent_human_checkpoints",
    "agent_channels",
    "not_automated_register",
)

# Copied from orchestration.yaml.
TRIGGERS: list[dict[str, Any]] = [
    {"channel": "Incoming prospect registration submission", "kind": "Inbound channel message", "starts": "BLK_01"},
]

EDGES: list[dict[str, Any]] = [
    {"from": "BLK_01", "on": "done", "to": "BLK_02"},
    {"from": "BLK_01", "on": "agent_tool", "to": "BLK_01.1"},
    {"from": "BLK_01", "on": "agent_tool", "to": "BLK_01.2"},
]

OWNERSHIP: list[dict[str, Any]] = [
    {"owner": "BLK_01", "segment": ["S1", "S2", "S3", "S4"]},
    {"owner": "BLK_02", "segment": ["S5", "S6", "S7"]},
    {"owner": "person", "segment": ["S6", "S8"]},
]

CHECKPOINTS: list[dict[str, Any]] = [
    {"agent_id": "BLK_01", "checkpoint_id": "CHK_01", "trigger": "Completion of bank details verification"},
    {"agent_id": "BLK_02", "checkpoint_id": "CHK_02", "trigger": "Generation of QC draft recommendation"},
]

OUTPUTS: list[dict[str, Any]] = [
    {"agent_id": "BLK_01", "channel": "InsureBuddy · Create and update agent record / profile"},
    {"agent_id": "BLK_02", "channel": "InsureBuddy Document Center · Upload, crop, and validate documents"},
]

# Built from parent_agent_id in agents.yaml.
SUB_AGENTS: dict[str, list[str]] = {
    "BLK_01": ["BLK_01.1", "BLK_01.2"],
}

PERSON = "person"


def owner_of(step: str) -> str:
    """Give the owner of the segment that holds the step: an agent ID or "person".

    A person segment wins over an agent segment that also names the step (S6), so a person-owned step never goes
    to an agent. Raise KeyError for an unknown step."""
    for entry in OWNERSHIP:
        if entry["owner"] == PERSON and step in entry["segment"]:
            return PERSON
    for entry in OWNERSHIP:
        if step in entry["segment"]:
            return entry["owner"]
    raise KeyError(step)


def is_person_step(step: str) -> bool:
    return owner_of(step) == PERSON


def agent_for_step(step: str) -> str | None:
    """Give the agent ID for the step, or None for a person-owned step."""
    owner = owner_of(step)
    return None if owner == PERSON else owner


def next_agent(agent_id: str, outcome: str) -> str | list[str] | None:
    """Give the target of the edge from agent_id on outcome. A fan-out gives the list of targets in edge order."""
    targets = [edge["to"] for edge in EDGES if edge["from"] == agent_id and edge["on"] == outcome]
    if not targets:
        return None
    return targets[0] if len(targets) == 1 else targets


def entry_agent(trigger_kind: str) -> str:
    """Give the agent that the trigger of that kind starts. Raise KeyError for an unknown kind."""
    for trigger in TRIGGERS:
        if trigger["kind"] == trigger_kind:
            return trigger["starts"]
    raise KeyError(trigger_kind)


def pauses_at(agent_id: str) -> list[str]:
    """Give the checkpoint IDs at which a case pauses after that agent."""
    return [checkpoint["checkpoint_id"] for checkpoint in CHECKPOINTS if checkpoint["agent_id"] == agent_id]


def case_route(trigger_kind: str) -> list[str]:
    """Give the agent IDs that a case of that trigger kind runs, in order. Sub-agents are never on the route."""
    route = [entry_agent(trigger_kind)]
    while True:
        last = route[-1]
        children = SUB_AGENTS.get(last, [])
        following = next(
            (edge["to"] for edge in EDGES
             if edge["from"] == last and edge["to"] not in children and edge["to"] not in route),
            None,
        )
        if following is None:
            return route
        route.append(following)
