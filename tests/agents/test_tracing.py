import mlflow
import pytest

from insurance_automation.agents.graph import build_graph, invoke
from insurance_automation.agents.tracing import enable_tracing, traced_node
from insurance_automation.llm.base import LLMResult
from tests.agents.test_graph import CLAIM_RESP
from tests.agents.test_nodes import make_ctx
from tests.conftest import FakeLedger


@pytest.fixture(autouse=True)
def local_mlflow(tmp_path):
    mlflow.set_tracking_uri(f'sqlite:///{tmp_path}/mlflow.db')
    mlflow.set_experiment('test-tracing')
    yield


def _spans():
    mlflow.flush_trace_async_logging()
    return mlflow.get_trace(mlflow.get_last_active_trace_id()).data.spans


def test_enable_tracing_is_idempotent():
    enable_tracing()
    enable_tracing()


def test_each_node_emits_span():
    ctx, _, _, _ = make_ctx(CLAIM_RESP)
    invoke(build_graph(ctx), 'Decide claim C00001', 't1')
    names = {s.name for s in _spans()}
    assert {'supervisor', 'coverage_checker', 'fraud_screener', 'risk_scorer', 'writer',
            'critic', 'approval_gate'} <= names


def test_span_has_token_attributes():
    ctx, _, _, ledger = make_ctx(CLAIM_RESP)
    invoke(build_graph(ctx), 'Decide claim C00001', 't2')
    by_name = {s.name: s for s in _spans()}
    for node in ('supervisor', 'writer', 'critic'):
        recs = [r for n, r in ledger.records if n == node]
        span = by_name[node]
        assert span.attributes['node'] == node
        assert span.attributes['tokens_in'] == sum(r.tokens_in for r in recs)
        assert span.attributes['tokens_out'] == sum(r.tokens_out for r in recs)
    assert by_name['risk_scorer'].attributes['tokens_in'] == 0


def test_exception_recorded_on_span_and_reraised():
    ledger = FakeLedger()

    def boom(state):
        ledger.record('boom', LLMResult('x', 3, 2))
        raise RuntimeError('kaput')

    with mlflow.start_span('root'), pytest.raises(RuntimeError, match='kaput'):
        traced_node('boom', boom, ledger)({})
    span = next(s for s in _spans() if s.name == 'boom')
    assert span.status.status_code.name == 'ERROR'
    assert any(e.name == 'exception' for e in span.events)
    assert span.attributes['tokens_in'] == 3


def test_tracing_off_emits_no_spans_and_same_answer():
    ctx, _, _, _ = make_ctx(CLAIM_RESP)
    off = invoke(build_graph(ctx, tracing=False), 'Decide claim C00001', 't3')
    assert mlflow.search_traces(return_type='list') == []
    ctx2, _, _, _ = make_ctx(CLAIM_RESP)
    on = invoke(build_graph(ctx2), 'Decide claim C00001', 't4')
    assert off.output.answer == on.output.answer and off.status == on.status
