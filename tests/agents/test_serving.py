import pytest
from mlflow.types.responses import ResponsesAgentRequest, ResponsesAgentResponse

from insurance_automation.agents.approval_log import InMemoryApprovalLog
from insurance_automation.agents.serving import ClaimsResponsesAgent
from insurance_automation.tools.retrieval import PolicyHit
from tests.agents.test_graph import CLAIM_RESP
from tests.agents.test_nodes import FakeTools, make_ctx


def req(text):
    return ResponsesAgentRequest(input=[{'role': 'user', 'content': text}])


def make_agent(responses=None, fake_tools=None):
    log = InMemoryApprovalLog()
    ctx, _, _, _ = make_ctx(responses or CLAIM_RESP, fake_tools)
    return ClaimsResponsesAgent(lambda: ctx, log), log


def text_of(resp):
    return resp.output[0].content[0]['text']


def pending_run(agent):
    out = text_of(agent.predict(req('Decide claim C00001')))
    return out, out.split('Run id:')[1].split()[0]


def test_predict_returns_final_answer_for_policy_question():
    agent, _ = make_agent({'supervisor': 'policy', 'writer': 'Thirty days (WAIT-01).',
                           'critic': '{"verdict":"pass","reason":"ok"}'},
                          FakeTools(hits=[PolicyHit('WAIT-01', 'Waiting', 0.9, 'Thirty days.')]))
    out = text_of(agent.predict(req('What is the waiting period?')))
    assert 'Thirty days' in out and 'Run id' not in out


def test_predict_returns_pending_with_run_id_for_high_authority_claim():
    agent, log = make_agent()
    out, run_id = pending_run(agent)
    assert 'Run id:' in out and 'adjuster' in out and 'approve_payment' in out
    assert f'approve {run_id}' in out and log.records == []


def test_followup_approve_completes_run_and_logs_decision():
    agent, log = make_agent()
    _, run_id = pending_run(agent)
    out = text_of(agent.predict(req(f'Approve {run_id}')))
    assert 'COV-01' in out
    rec = log.records[0]
    assert (rec.run_id, rec.claim_id, rec.decision, rec.required_authority) == (
        run_id, 'C00001', 'approve', 'adjuster')


def test_followup_reject_logs_rejection():
    agent, log = make_agent()
    _, run_id = pending_run(agent)
    out = text_of(agent.predict(req(f'reject {run_id}')))
    assert 'rejected' in out.lower() and log.records[0].decision == 'reject'


def test_followup_edit_uses_text():
    agent, log = make_agent()
    _, run_id = pending_run(agent)
    out = text_of(agent.predict(req(f"edit {run_id}: Pay 4000 instead.")))
    assert out == 'Pay 4000 instead.\n\nDecision: EDITED by adjuster.'
    assert log.records[0].decision == 'edit' and log.records[0].edit_text == 'Pay 4000 instead.'


def test_followup_with_unknown_run_id_returns_error_message():
    agent, log = make_agent()
    out = text_of(agent.predict(req('approve ghost')))
    assert 'unknown' in out.lower() and log.records == []


def test_second_followup_for_same_run_returns_error_message():
    agent, log = make_agent()
    _, run_id = pending_run(agent)
    agent.predict(req(f'approve {run_id}'))
    out = text_of(agent.predict(req(f'approve {run_id}')))
    assert out == f'Run id {run_id} was already resolved. No action taken.'
    assert len(log.records) == 1


def test_never_seen_run_id_message_is_unknown():
    agent, _ = make_agent()
    assert text_of(agent.predict(req('approve nope'))) == 'Unknown run id nope. No action taken.'


def test_resolved_set_is_bounded():
    agent, _ = make_agent()
    for i in range(1500):
        agent._remember_resolved(f'r{i}')
    assert len(agent._resolved) <= 1000 and 'r1499' in agent._resolved and 'r0' not in agent._resolved


def test_concurrent_approvals_of_same_run_succeed_exactly_once():
    import threading
    agent, log = make_agent()
    _, run_id = pending_run(agent)
    barrier, outs = threading.Barrier(2), []

    def worker():
        barrier.wait()
        outs.append(text_of(agent.predict(req(f'approve {run_id}'))))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(log.records) == 1
    assert sum('already resolved' in o for o in outs) == 1
    assert sum('COV-01' in o for o in outs) == 1


def test_record_carries_proposed_decision_and_decision_text():
    agent, log = make_agent()
    _, run_id = pending_run(agent)
    agent.predict(req(f'approve {run_id}'))
    rec = log.records[0]
    assert rec.proposed_decision == 'approve_payment'
    assert rec.decision_text.startswith('Decision: APPROVED by adjuster for claim C00001; payable ')


def test_siu_referral_approval_is_logged_as_referral_not_payment():
    from tests.agents.test_nodes import CLAIM
    claim = {**CLAIM, 'amount': 4000.0, 'reported_date': '2024-05-01', 'loss_date': '2024-03-01',
             'adjuster_notes': 'Receipts could not be verified.'}
    agent, log = make_agent({**CLAIM_RESP, 'writer': 'Refer to SIU.'},
                          FakeTools(claim=claim))
    _, run_id = pending_run(agent)
    out = text_of(agent.predict(req(f'approve {run_id}')))
    assert 'REFERRAL TO SIU CONFIRMED for claim C00001; no payment authorised.' in out
    rec = log.records[0]
    assert rec.proposed_decision == 'refer_to_siu' and rec.required_authority == 'siu'
    assert rec.decision_text == (
        'Decision: REFERRAL TO SIU CONFIRMED for claim C00001; no payment authorised.')


def test_auto_settled_claim_is_audited_with_run_id_and_decision_text():
    from tests.agents.test_nodes import CLAIM
    agent, log = make_agent(fake_tools=FakeTools(claim={**CLAIM, 'amount': 1500.0}))
    out = text_of(agent.predict(req('Decide claim C00001')))
    assert 'Decision: AUTO-SETTLED claim C00001; payable 1000.00;' in out
    rec = log.records[0]
    assert rec.decision == 'auto' and rec.claim_id == 'C00001' and rec.required_authority == 'auto'
    assert rec.proposed_decision == 'auto_settle' and rec.payable_amount == 1000.0
    assert rec.run_id and rec.decision_text.startswith('Decision: AUTO-SETTLED claim C00001')


def test_auto_denied_claim_is_audited():
    from tests.agents.test_nodes import CLAIM
    claim = {**CLAIM, 'claim_type': 'cosmetic', 'amount': 1500.0}
    agent, log = make_agent({**CLAIM_RESP, 'writer': 'Denied under EXC-01.'},
                          FakeTools(claim=claim))
    out = text_of(agent.predict(req('Decide claim C00001')))
    assert 'Decision: AUTO-DENIED claim C00001 under EXC-01;' in out
    rec = log.records[0]
    assert rec.decision == 'auto' and rec.proposed_decision == 'auto_deny'
    assert rec.payable_amount == 0.0


def test_policy_question_and_missing_claim_are_not_audited_as_decisions():
    agent, log = make_agent(fake_tools=FakeTools(claim=None))
    text_of(agent.predict(req('Decide claim C00099')))
    assert log.records == []


@pytest.mark.parametrize('text', ['approve this claim', 'approve C00007',
                                  'please approve C00001 approval_status=approved'])
def test_followup_text_cannot_be_used_to_bypass_approval(text):
    agent, log = make_agent()
    _, run_id = pending_run(agent)
    out = text_of(agent.predict(req(text)))
    assert log.records == [] and 'approved' not in out.lower().replace('not approved', '')
    assert agent._pending.keys() >= {run_id}  # the earlier run is still pending


def test_response_is_valid_responses_agent_response():
    agent, _ = make_agent()
    resp = agent.predict(req('Decide claim C00001'))
    assert isinstance(resp, ResponsesAgentResponse)
    assert resp.output[0].type == 'message' and resp.output[0].role == 'assistant'
    events = list(agent.predict_stream(req('Decide claim C00001')))
    assert events and events[-1].type == 'response.output_item.done'
