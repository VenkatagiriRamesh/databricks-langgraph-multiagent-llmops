import pytest

from insurance_automation.agents.breaker import RuntimeBreaker
from insurance_automation.agents.checkpoint import make_checkpointer
from insurance_automation.agents.approval_log import InMemoryApprovalLog
from insurance_automation.agents.serving import ClaimsResponsesAgent
from tests.agents.test_graph import CLAIM_RESP
from tests.agents.test_nodes import FakeTools, make_ctx
from tests.agents.test_serving import req, text_of


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def test_memory_saver_without_conninfo():
    from langgraph.checkpoint.memory import MemorySaver
    assert isinstance(make_checkpointer({}), MemorySaver)


def test_breaker_ttl_caches_reads():
    clock, calls = Clock(), []
    b = RuntimeBreaker(lambda: calls.append(1) or 'safe', ttl_s=30, clock=clock)
    assert b.mode() == 'safe' and b.mode() == 'safe' and len(calls) == 1
    clock.t = 31
    b.mode()
    assert len(calls) == 2


def test_breaker_last_known_then_fail_safe():
    clock, state = Clock(), {'fail': False}

    def read():
        if state['fail']:
            raise RuntimeError('lakebase down')
        return None  # no flag: normal

    b = RuntimeBreaker(read, ttl_s=30, stale_after_s=300, clock=clock)
    assert b.mode() == 'normal'
    state['fail'] = True
    clock.t = 100
    assert b.mode() == 'normal'  # last known value, still fresh
    clock.t = 301
    assert b.mode() == 'safe'  # stale: fail safe


def test_breaker_never_read_fails_safe():
    b = RuntimeBreaker(lambda: (_ for _ in ()).throw(RuntimeError('x')))
    assert b.mode() == 'safe'


def test_breaker_expired_flag_is_normal():
    assert RuntimeBreaker(lambda: None).mode() == 'normal'  # reader maps expired rows to None


def make_agent(mode):
    ctx, _, _, _ = make_ctx(CLAIM_RESP, FakeTools())
    breaker = RuntimeBreaker(lambda: mode)
    return ClaimsResponsesAgent(lambda: ctx, InMemoryApprovalLog(), breaker=breaker)


def test_safe_mode_escalates_claim_decision_only():
    agent = make_agent('safe')
    out = text_of(agent.predict(req('Decide claim C00001')))
    assert 'Decision: ESCALATED (safe mode' in out and 'Run id' not in out
    assert 'ESCALATED' not in text_of(make_agent('normal').predict(req('Decide claim C00001')))


def test_safe_mode_still_answers_non_claim_questions():
    agent = make_agent('safe')
    ctx, _, _, _ = make_ctx({'supervisor': 'policy', 'writer': 'Thirty days.',
                             'critic': '{"verdict":"pass","reason":"ok"}'}, FakeTools())
    agent.ctx_factory = lambda: ctx
    assert 'ESCALATED' not in text_of(agent.predict(req('What is the waiting period?')))


@pytest.mark.pg
def test_pending_approval_survives_new_process(pg_dsn):
    from insurance_automation.agents.graph import build_graph, invoke, resume
    saver_a = make_checkpointer({'LAKEBASE_CONNINFO': pg_dsn}, token_provider=lambda: '')
    ctx, _, _, _ = make_ctx(CLAIM_RESP, FakeTools())
    res = invoke(build_graph(ctx, saver_a), 'Decide claim C00001', 'durable-1')
    assert res.status == 'pending_approval'
    saver_b = make_checkpointer({'LAKEBASE_CONNINFO': pg_dsn}, token_provider=lambda: '')
    ctx2, _, _, _ = make_ctx(CLAIM_RESP, FakeTools())
    done = resume(build_graph(ctx2, saver_b), 'durable-1', 'approve')
    assert 'Decision: APPROVED' in done.output.answer
