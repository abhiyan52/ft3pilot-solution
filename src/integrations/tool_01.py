"""MOCK of TOOL_01. The Precord declares no tools.yaml entry for it; open item HR-201:BLK_01:TOOL_01 carries it.

Assumption (HR-201:BLK_01:TOOL_01, status open, no answer): "Stub the tool on sample data until it exists".
The Precord ships no sample_data rows, so every response field comes back as None (unknown), never inferred.
This module opens no connection, reads no credential and blocks promotion.
"""
from __future__ import annotations

from typing import Any


REQUIREMENT_REFS = (
    'stub:TOOL_01',
    'open_items@HR-201:BLK_01:TOOL_01',
    'agent_block_actions@row:1',
    'agent_block_actions@row:3',
    'agent_block_actions@row:4',
)
IS_MOCK = True
OPEN_ITEMS = ('HR-201:BLK_01:TOOL_01',)
DEFAULT_ASSUMPTION = 'Stub the tool on sample data until it exists'
ENDPOINT = '__MOCK__'
AGENTS = ('BLK_01', 'BLK_01.1', 'BLK_01.2')

# Request fields are the action's reads; response fields are its writes (stub.actions).
ACTIONS: dict[str, dict[str, tuple[str, ...]]] = {
    'ACT_01': {
        'reads': ('Full Name', 'Mobile Number', 'Email', 'RM Business Code'),
        'writes': ('Application record draft',),
    },
    'ACT_03': {
        'reads': ('Name', 'Gender', 'Date of Birth', 'Address', 'Pincode'),
        'writes': ('Agent profile update',),
    },
    'ACT_04': {
        'reads': ('IFSC Code', 'Bank Account Number', 'Name As In Bank Account'),
        'writes': ('Bank Name', 'Bank City', 'Branch Name', 'Bank verification status'),
    },
}

# context sample_data is empty in the Precord, so there is no row to seed a response from.
SAMPLE_DATA: tuple[dict[str, Any], ...] = ()


def _seed(action_id: str) -> dict[str, Any]:
    """Take each write from the first sample row that names it; a field no row names stays None."""
    writes = ACTIONS[action_id]['writes']
    response: dict[str, Any] = {field: None for field in writes}
    for row in SAMPLE_DATA:
        for field in writes:
            if response[field] is None and row.get(field) not in (None, ''):
                response[field] = row[field]
    return response


def invoke(payload: dict[str, Any], correlation_id: str, *, endpoint: str | None = None,
           credential: Any = None) -> dict[str, Any]:
    """Answer one TOOL_01 call from embedded literals. `endpoint` and `credential` are accepted and ignored.

    `payload['action_id']` selects ACT_01, ACT_03 or ACT_04; the other keys are that action's reads.
    """
    action_id = payload.get('action_id')
    if action_id not in ACTIONS:
        return {
            'mock': True, 'tool_id': 'TOOL_01', 'endpoint': ENDPOINT, 'correlation_id': correlation_id,
            'status': 'error', 'error': f'unknown action_id {action_id!r}; expected one of {sorted(ACTIONS)}',
        }
    reads = ACTIONS[action_id]['reads']
    missing = [field for field in reads if payload.get(field) in (None, '')]
    return {
        'mock': True,
        'tool_id': 'TOOL_01',
        'endpoint': ENDPOINT,
        'correlation_id': correlation_id,
        'action_id': action_id,
        'assumption': DEFAULT_ASSUMPTION,
        'status': 'ok',
        'request': {field: payload.get(field) for field in reads},
        'missing_request_fields': missing,
        'response': _seed(action_id),
    }
