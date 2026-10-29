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


def _denial_state(**kw):
    return {
        'claim_id': 'C00024', 'authority': 'adjuster', 'draft': 'Denied under EXC-01.',
        'claim': {'amount': 5000.0},
        'coverage': {'covered': False, 'payable_amount': 0.0}, **kw,
    }


def test_denial_gate_payload_says_deny_claim_and_confirm_denial():
    from langgraph.types import Command
    graph = _gate_graph()
    cfg = {'configurable': {'thread_id': 'd'}}
    res = graph.invoke(_denial_state(), cfg)
    payload = res['__interrupt__'][0].value
    assert payload['proposed_decision'] == 'deny_claim'
    assert payload['approve_means'] == 'confirm_denial'
    final = graph.invoke(Command(resume={'decision': 'approve'}), cfg)
    assert final['approval_status'] == 'approved'
    assert final['answer'].endswith('Decision: DENIAL CONFIRMED by adjuster for claim C00024.')


def test_payment_gate_payload_says_approve_means_approve_payment():
    graph = _gate_graph()
    res = graph.invoke(_state(), {'configurable': {'thread_id': 'p'}})
    payload = res['__interrupt__'][0].value
    assert payload['proposed_decision'] == 'approve_payment'
    assert payload['approve_means'] == 'approve_payment'


def _siu_state(**kw):
    return {
        'claim_id': 'C00031', 'authority': 'siu', 'draft': 'Suspicious pattern.',
        'claim': {'amount': 7000.0},
        'coverage': {'covered': True, 'payable_amount': 6927.31},
        'fraud': {'refer_to_siu': True, 'flags': [{'code': 'LATE'}]}, **kw,
    }


def test_siu_gate_payload_is_a_referral_not_a_payment():
    graph = _gate_graph()
    res = graph.invoke(_siu_state(), {'configurable': {'thread_id': 's0'}})
    payload = res['__interrupt__'][0].value
    assert payload['proposed_decision'] == 'refer_to_siu'
    assert payload['approve_means'] == 'confirm_referral'


@pytest.mark.parametrize('decision,status,text', [
    ('approve', 'approved',
     'Decision: REFERRAL TO SIU CONFIRMED for claim C00031; no payment authorised.'),
    ('reject', 'rejected',
     'Decision: SIU REFERRAL REJECTED by siu for claim C00031; return to claims handling.'),
])
def test_siu_referral_decisions_never_read_as_payment(decision, status, text):
    from langgraph.types import Command
    graph = _gate_graph()
    cfg = {'configurable': {'thread_id': f's-{decision}'}}
    graph.invoke(_siu_state(), cfg)
    final = graph.invoke(Command(resume={'decision': decision}), cfg)
    assert final['approval_status'] == status
    assert final['answer'].endswith(text)
    assert 'payable' not in final['answer'] and 'APPROVED' not in final['answer']


def test_siu_edit_keeps_existing_form():
    from langgraph.types import Command
    graph = _gate_graph()
    cfg = {'configurable': {'thread_id': 's-edit'}}
    graph.invoke(_siu_state(), cfg)
    final = graph.invoke(Command(resume={'decision': 'edit', 'edit_text': 'Edited.'}), cfg)
    assert final['answer'] == 'Edited.\n\nDecision: EDITED by siu.'


def test_auto_settle_appends_deterministic_decision_line():
    out = approval_gate({
        'authority': 'auto', 'claim_id': 'C00009', 'draft': 'Looks fine.',
        'coverage': {'covered': True, 'payable_amount': 1234.5, 'clause_ids': ['COV-01']},
    })
    assert out['approval_status'] == 'not_required'
    assert out['answer'] == (
        'Looks fine.\n\nDecision: AUTO-SETTLED claim C00009; payable 1234.50; '
        'no human sign-off required (below 2,000).')


def test_auto_deny_appends_deterministic_decision_line():
    out = approval_gate({
        'authority': 'auto', 'claim_id': 'C00010', 'draft': 'Not covered.',
        'coverage': {'covered': False, 'payable_amount': 0.0, 'clause_ids': ['EXC-01', 'WAIT-01']},
    })
    assert out['answer'] == (
        'Not covered.\n\nDecision: AUTO-DENIED claim C00010 under EXC-01, WAIT-01; '
        'no human sign-off required (below 2,000).')


def test_missing_claim_gets_clear_answer_and_no_approval():
    out = approval_gate({'authority': None, 'claim_id': 'C00099', 'draft': 'LLM waffle',
                         'lookup_error': 'claim_not_found'})
    assert out == {'approval_status': 'not_required', 'answer': 'Claim C00099 was not found.'}
