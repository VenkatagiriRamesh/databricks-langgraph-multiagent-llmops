import pytest

from insurance_automation.agents.graph import ESCALATION_ANSWER
from insurance_automation.contracts import AgentOutput
from insurance_automation.evaluation.harness import EvalReport, run_eval
from insurance_automation.evaluation.types import GoldenItem
from insurance_automation.llm.base import QuotaExceededError


def item(i, route='policy', **kw):
    base = {
        'id': i, 'question': 'q', 'expected_route': route, 'expected_tools': [], 'reference_answer': 'a',
        'reference_sql': None, 'reference_rows': None, 'must_cite': False, 'expected_citations': [],
        'safety_case': False,
    }
    base.update(kw)
    return GoldenItem(**base)


def out(**kw):
    base = {'answer': 'ok', 'route': 'policy'}
    base.update(kw)
    return AgentOutput(**base)


def test_aggregates_with_ci():
    items = [item('a'), item('b')]
    outputs = {'a': out(), 'b': out(route='risk')}
    report = run_eval(lambda it, r: outputs[it.id], items, n_runs=3)
    m = report.metrics['route_accuracy']
    assert m.mean == pytest.approx(0.5)
    assert m.low <= m.mean <= m.high
    assert report.n_items == 2 and report.n_runs == 3
    assert report.metrics['safety_pass'].mean == 1.0


def test_resume_skips_finished(tmp_path):
    items = [item('a'), item('b')]
    path = str(tmp_path / 'r.jsonl')
    calls = []

    def runner(it, r):
        calls.append((it.id, r))
        return out()

    run_eval(runner, items, n_runs=2, results_path=path)
    assert len(calls) == 4
    report = run_eval(runner, items, n_runs=2, results_path=path)
    assert len(calls) == 4
    assert report.metrics['route_accuracy'].mean == 1.0


def test_quota_saves_progress_and_reruns_remainder(tmp_path):
    items = [item(str(i)) for i in range(5)]
    path = str(tmp_path / 'r.jsonl')
    calls = []

    def flaky(it, r):
        if it.id == '4':
            raise QuotaExceededError('limit')
        calls.append(it.id)
        return out()

    with pytest.raises(QuotaExceededError):
        run_eval(flaky, items, n_runs=1, results_path=path)
    assert calls == ['0', '1', '2', '3']
    calls.clear()

    def ok(it, r):
        calls.append(it.id)
        return out()

    run_eval(ok, items, n_runs=1, results_path=path)
    assert calls == ['4']


def test_failure_modes_counted():
    items = [
        item('r'), item('s', reference_rows=[{'x': 1}]),
        item('c', must_cite=True, expected_citations=['K1']),
        item('f', safety_case=True, forbidden_phrases=['approved']),
        item('au', expected_authority='manager'),
    ]
    outputs = {
        'r': out(route='risk'), 's': out(rows=[{'x': 2}]), 'c': out(),
        'f': out(answer='claim approved'), 'au': out(required_authority='auto'),
    }
    report = run_eval(lambda it, r: outputs[it.id], items, n_runs=1)
    modes = report.by_failure_mode
    assert modes['routing'] >= 1 and modes['sql'] == 1 and modes['retrieval'] == 1
    assert modes['safety'] == 1 and modes['authority'] == 1
    assert {f['metric'] for f in report.failures} >= {'route_accuracy', 'sql_exec_match'}


def test_stp_escalation_fraud():
    items = [
        item('c1', 'claim_decision', expected_fraud_referral=True),
        item('c2', 'claim_decision', expected_fraud_referral=True),
        item('c3', 'claim_decision', expected_fraud_referral=False),
        item('c4', 'claim_decision', expected_fraud_referral=False),
    ]
    outputs = {
        'c1': out(route='claim_decision', fraud_referred=True, approval_status='pending'),
        'c2': out(route='claim_decision', fraud_referred=False),
        'c3': out(route='claim_decision', fraud_referred=True, answer=ESCALATION_ANSWER),
        'c4': out(route='claim_decision', fraud_referred=False),
    }
    report = run_eval(lambda it, r: outputs[it.id], items, n_runs=1)
    assert report.stp_rate == 0.75
    assert report.escalation_rate == 0.5
    assert report.fraud_precision == 0.5  # tp=1, fp=1
    assert report.fraud_recall == 0.5  # tp=1, fn=1


def test_judge_cost_latency_and_json_roundtrip():
    items = [item('a')]
    report = run_eval(
        lambda it, r: out(cost_usd=0.01 * (r + 1), latency_s=r + 1.0), items, n_runs=3,
        judge=lambda it, o: {'groundedness': 0.75, 'correctness': 1.0},
    )
    assert report.metrics['groundedness'].mean == 0.75
    assert report.cost_usd_median == pytest.approx(0.02)
    assert report.latency_p95_s == pytest.approx(2.9)
    assert EvalReport.from_json(report.to_json()) == report
