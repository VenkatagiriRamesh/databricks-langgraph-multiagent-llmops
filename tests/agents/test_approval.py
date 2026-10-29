import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from insurance_automation.agents.approval import approval_gate, needs_approval
from insurance_automation.agents.state import ClaimsState


@pytest.mark.parametrize('authority,expected', [
    ('auto', False), ('adjuster', True), ('senior_adjuster', True), ('manager', True), ('siu', True),
    (None, False),
])
def test_needs_approval_by_authority(authority, expected):
    state = {} if authority is None else {'authority': authority}
    assert needs_approval(state) is expected


def _gate_graph():
    g = StateGraph(ClaimsState)
    g.add_node('gate', approval_gate)
    g.add_edge(START, 'gate')
    g.add_edge('gate', END)
    return g.compile(checkpointer=MemorySaver())


def _state():
    return {
        'claim_id': 'C00001', 'authority': 'adjuster', 'draft': 'Pay 4500.',
        'coverage': {'payable_amount': 4500.0}, 'fraud': {'flags': [{'code': 'X'}]},
        'risk': {'reason_codes': [{'feature': 'age'}]},
    }


def test_gate_without_approval_requirement_finalises_draft():
    out = approval_gate({'authority': 'auto', 'draft': 'Denied.'})
    assert out == {'approval_status': 'not_required', 'answer': 'Denied.'}


@pytest.mark.parametrize('decision,status', [('approve', 'approved'), ('reject', 'rejected'), ('edit', 'edited')])
def test_gate_interrupts_with_payload_then_applies_decision(decision, status):
    from langgraph.types import Command
    graph = _gate_graph()
    cfg = {'configurable': {'thread_id': 't'}}
    res = graph.invoke(_state(), cfg)
    payload = res['__interrupt__'][0].value
    assert payload['required_authority'] == 'adjuster' and payload['payable_amount'] == 4500.0
    assert payload['fraud_flags'] == ['X'] and payload['reason_codes'] == ['age']
    final = graph.invoke(Command(resume={'decision': decision, 'edit_text': 'Edited.'}), cfg)
    assert final['approval_status'] == status
    expected = {
        'approve': 'Pay 4500.\n\nDecision: APPROVED by adjuster for claim C00001; payable 4500.00.',
        'edit': 'Edited.\n\nDecision: EDITED by adjuster.',
    }.get(decision)
    if expected:
        assert final['answer'] == expected
    else:
        assert 'rejected' in final['answer'].lower()
        assert 'C00001' in final['answer'] and 'adjuster' in final['answer']
