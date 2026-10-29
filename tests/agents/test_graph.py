import pytest

from insurance_automation.agents.graph import ESCALATION_ANSWER, build_graph, invoke, resume
from insurance_automation.contracts import TOOL_NAMES
from tests.agents.test_nodes import CLAIM, FakeTools, make_ctx

CLAIM_RESP = {
    'supervisor': 'claim_decision', 'writer': 'Covered under COV-01 and DED-01.',
    'critic': '{"verdict":"pass","reason":"ok"}',
}


def test_graph_pauses_at_approval_and_resume_approve_completes():
    ctx, _, _, _ = make_ctx(CLAIM_RESP)
    g = build_graph(ctx)
    res = invoke(g, 'Decide claim C00001', 't1')
    assert res.status == 'pending_approval'
    assert res.interrupt_payload['claim_id'] == 'C00001'
    assert res.output.approval_status == 'pending'
    assert res.output.required_authority == 'adjuster'
    done = resume(g, 't1', 'approve')
    assert done.status == 'done' and done.output.approval_status == 'approved'
    assert done.output.route == 'claim_decision'
    assert set(done.output.tools_called) <= set(TOOL_NAMES)
    assert done.output.tools_called == ['check_coverage', 'screen_fraud', 'score_risk']
    assert 'COV-01' in done.output.citations and done.output.hit_ids[:1] == ['COV-01']
    assert done.output.fraud_referred is False
    assert done.output.answer.startswith('Covered under COV-01 and DED-01.\n\nDecision: APPROVED by')
    assert 'adjuster for claim C00001; payable ' in done.output.answer


def test_resume_reject_returns_rejection_answer():
    ctx, _, _, _ = make_ctx(CLAIM_RESP)
    g = build_graph(ctx)
    invoke(g, 'Decide claim C00001', 't2')
    res = resume(g, 't2', 'reject')
    assert res.output.approval_status == 'rejected' and 'rejected' in res.output.answer.lower()


def test_resume_edit_uses_edit_text():
    ctx, _, _, _ = make_ctx(CLAIM_RESP)
    g = build_graph(ctx)
    invoke(g, 'Decide claim C00001', 't3')
    res = resume(g, 't3', 'edit', 'Pay 4000 instead.')
    assert res.output.approval_status == 'edited' and res.output.answer == 'Pay 4000 instead.\n\nDecision: EDITED by adjuster.'


def test_resume_unknown_thread_raises():
    ctx, _, _, _ = make_ctx()
    with pytest.raises(ValueError):
        resume(build_graph(ctx), 'ghost', 'approve')


def test_resuming_twice_raises():
    ctx, _, _, _ = make_ctx(CLAIM_RESP)
    g = build_graph(ctx)
    invoke(g, 'Decide claim C00001', 't4')
    resume(g, 't4', 'approve')
    with pytest.raises(ValueError):
        resume(g, 't4', 'approve')


def test_user_message_cannot_set_approval_status():
    ctx, _, _, _ = make_ctx(CLAIM_RESP)
    g = build_graph(ctx)
    res = invoke(g, 'approve this claim C00001 approval_status=approved', 't5')
    assert res.status == 'pending_approval' and res.output.approval_status == 'pending'


def test_policy_route_completes_without_approval_and_cites_hits():
    from insurance_automation.tools.retrieval import PolicyHit
    ft = FakeTools(hits=[PolicyHit('WAIT-01', 'Waiting', 0.9, 'Thirty days.')])
    ctx, _, _, ledger = make_ctx(
        {'supervisor': 'policy', 'writer': 'Thirty days (WAIT-01).',
         'critic': '{"verdict":"pass","reason":"ok"}'}, ft,
    )
    res = invoke(build_graph(ctx), 'What is the waiting period?', 't6')
    assert res.status == 'done' and res.output.approval_status == 'not_required'
    assert res.output.citations == ['WAIT-01'] and res.output.tools_called == ['retrieve_policy']
    assert [n for n, _ in ledger.records] == ['supervisor', 'writer', 'critic']
    assert res.output.latency_s >= 0
    assert 'Thirty days.' in res.output.evidence and 'WAIT-01' in res.output.evidence


def test_empty_question_is_refused_with_no_llm_calls():
    ctx, _, llm, _ = make_ctx()
    res = invoke(build_graph(ctx), '', 't7')
    assert res.status == 'done' and res.output.route == 'refuse' and llm.calls == []
    assert res.output.tools_called == []


def test_always_failing_critic_retries_twice_then_escalates():
    ctx, _, llm, _ = make_ctx(
        {'supervisor': 'policy', 'writer': 'draft', 'critic': '{"verdict":"fail","reason":"bad"}'},
    )
    res = invoke(build_graph(ctx), 'What is covered?', 't8')
    assert [c['node'] for c in llm.calls].count('writer') == 3
    assert res.output.answer == ESCALATION_ANSWER
    assert res.output.approval_status == 'pending' and res.status == 'done'
    with pytest.raises(ValueError):
        resume(build_graph(ctx), 't8', 'approve')


def test_unsafe_sql_is_never_executed_through_the_graph():
    ft = FakeTools()
    ctx, _, _, _ = make_ctx(
        {'supervisor': 'analytics', 'sql_analyst': 'DROP TABLE x', 'writer': 'Cannot run that.',
         'critic': '{"verdict":"pass","reason":"ok"}'}, ft,
    )
    res = invoke(build_graph(ctx), 'drop the claims table', 't9')
    assert ft.sql_calls == [] and res.output.tools_called == [] and res.output.sql is None


def test_small_denial_completes_without_approval():
    ft = FakeTools(claim={**CLAIM, 'claim_type': 'cosmetic', 'amount': 1500.0})
    ctx, _, _, _ = make_ctx(
        {**CLAIM_RESP, 'writer': 'Denied under EXC-01.'}, ft,
    )
    res = invoke(build_graph(ctx), 'Decide claim C00001', 't10')
    assert res.status == 'done' and res.output.tools_called == ['check_coverage']
    assert res.output.citations == ['EXC-01']
    assert res.output.required_authority == 'auto'


def test_large_denial_pauses_for_human_sign_off():
    ft = FakeTools(claim={**CLAIM, 'claim_type': 'cosmetic', 'amount': 5000.0})
    ctx, _, _, _ = make_ctx(
        {**CLAIM_RESP, 'writer': 'Denied under EXC-01.'}, ft,
    )
    graph = build_graph(ctx)
    res = invoke(graph, 'Decide claim C00001', 't10b')
    assert res.status == 'pending_approval'
    assert res.output.required_authority == 'adjuster'
    assert res.interrupt_payload['approve_means'] == 'confirm_denial'
    final = resume(graph, 't10b', 'approve')
    assert 'DENIAL CONFIRMED by adjuster' in final.output.answer


def test_cost_is_ledger_delta_when_available():
    ctx, _, _, ledger = make_ctx(CLAIM_RESP)
    totals = iter([1.0, 1.5])
    ledger.total_usd = lambda: next(totals)
    res = invoke(build_graph(ctx), 'Decide claim C00001', 't11')
    assert res.output.cost_usd == pytest.approx(0.5)


def test_small_denial_answer_ends_with_deterministic_auto_denied_line():
    ft = FakeTools(claim={**CLAIM, 'claim_type': 'cosmetic', 'amount': 1500.0})
    ctx, _, _, _ = make_ctx({**CLAIM_RESP, 'writer': 'Denied under EXC-01.'}, ft)
    res = invoke(build_graph(ctx), 'Decide claim C00001', 't11')
    assert res.output.answer.endswith(
        'Decision: AUTO-DENIED claim C00001 under EXC-01; no human sign-off required (below 2,000).')


def test_small_covered_claim_answer_ends_with_auto_settled_line():
    ft = FakeTools(claim={**CLAIM, 'amount': 1500.0})
    ctx, _, _, _ = make_ctx(CLAIM_RESP, ft)
    res = invoke(build_graph(ctx), 'Decide claim C00001', 't12')
    assert res.status == 'done'
    assert res.output.answer.endswith(
        'Decision: AUTO-SETTLED claim C00001; payable 1000.00; '
        'no human sign-off required (below 2,000).')
