import json

import pytest

from insurance_automation.agents.graph import ESCALATION_ANSWER, GraphResult
from insurance_automation.contracts import AgentOutput
from insurance_automation.evaluation.harness import (
    EvalReport,
    compute_graph_hash,
    make_runner,
    run_eval,
)
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
    assert 'safety_pass' not in report.metrics  # no safety items: not applicable


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
    assert report.escalation_rate == 0.25  # only c3 was escalated by the critic loop
    assert report.fraud_precision == 0.5  # tp=1, fp=1
    assert report.fraud_recall == 0.5  # tp=1, fn=1


def test_judge_cost_latency_and_json_roundtrip():
    items = [item('a')]
    report = run_eval(
        lambda it, r: out(cost_usd=0.01 * (r + 1), latency_s=r + 1.0), items, n_runs=3,
        judge=lambda it, o: {'groundedness': 0.75, 'correctness': 1.0},
    )
    assert report.metrics['groundedness'].mean == 0.75
    assert report.cost_usd_median == pytest.approx(0.01)  # first run only
    assert report.latency_p95_s == pytest.approx(1.0)
    assert EvalReport.from_json(report.to_json()) == report


def test_ci_clipped_to_unit_interval():
    items = [item(str(i)) for i in range(6)]
    outputs = {str(i): out(route='policy' if i < 5 else 'risk') for i in range(6)}
    outputs['5'] = out(route='risk')
    report = run_eval(lambda it, r: outputs[it.id], items, n_runs=1)
    for m in report.metrics.values():
        assert 0.0 <= m.low <= m.high <= 1.0


def test_ci_clipped_high_variance_near_one():
    items = [item(str(i)) for i in range(30)]
    judged = {str(i): (0.0 if i == 0 else 1.0) for i in range(30)}
    report = run_eval(
        lambda it, r: out(), items, n_runs=1,
        judge=lambda it, o: {'groundedness': judged[it.id], 'correctness': 1.0},
    )
    m = report.metrics['groundedness']
    assert m.mean == pytest.approx(29 / 30) and m.high <= 1.0 and m.low >= 0.0


def test_report_none_fraud_roundtrip_and_denominator():
    report = run_eval(lambda it, r: out(), [item('a')], n_runs=1)
    assert report.fraud_precision is None and report.fraud_recall is None
    assert report.n_fraud_positive == 0
    text = report.to_json()
    assert json.loads(text)['fraud_precision'] is None
    assert EvalReport.from_json(text) == report
    items = [item('c', 'claim_decision', expected_fraud_referral=True)]
    rep = run_eval(lambda it, r: out(route='claim_decision', fraud_referred=True), items, n_runs=2)
    assert rep.n_fraud_positive == 1  # first run only


def test_make_runner_approves_normal_items_but_not_safety_items():
    calls = []

    def invoke_fn(graph, question, thread):
        calls.append(('invoke', thread))
        return GraphResult('pending_approval', out(approval_status='pending'))

    def resume_fn(graph, thread, decision):
        calls.append(('resume', thread, decision))
        return GraphResult('done', out(approval_status='approved'))

    runner = make_runner('g', invoke_fn, resume_fn)
    assert runner(item('n1'), 1).approval_status == 'approved'
    assert runner(item('s1', safety_case=True), 0).approval_status == 'pending'
    assert calls == [('invoke', 'n1-1'), ('resume', 'n1-1', 'approve'), ('invoke', 's1-0')]
    done = make_runner('g', lambda g, q, t: GraphResult('done', out()), resume_fn)
    assert done(item('x'), 0).approval_status == 'not_required'


def test_escalation_rate_counts_only_critic_escalations_not_pending_approvals():
    items = [item('a'), item('b')]
    outputs = {'a': out(approval_status='pending'), 'b': out(answer=ESCALATION_ANSWER)}
    report = run_eval(lambda it, r: outputs[it.id], items, n_runs=1)
    assert report.escalation_rate == pytest.approx(0.5)


def test_aggregation_excludes_not_applicable_and_reports_n_items():
    items = [item(str(i)) for i in range(27)]
    items += [item(f'q{i}', 'analytics', reference_rows=[{'x': 1}]) for i in range(4)]
    outputs = {it.id: out(route=it.expected_route, rows=[{'x': 1}]) for it in items}
    outputs['q0'] = out(route='analytics', rows=[{'x': 2}])
    report = run_eval(lambda it, r: outputs[it.id], items, n_runs=2)
    sql = report.metrics['sql_exec_match']
    assert sql.n_items == 4 and sql.mean == pytest.approx(0.75)
    assert report.metrics['route_accuracy'].n_items == 31
    assert 'safety_pass' not in report.metrics
    assert 'authority_match' not in report.metrics
    assert 'citation_valid' not in report.metrics
    assert {f['metric'] for f in report.failures} == {'sql_exec_match'}
    assert sum(report.by_failure_mode.values()) == 2


def test_single_applicable_item_interval_is_the_value_but_n_items_shows_thinness():
    items = [item('a'), item('s', safety_case=True, forbidden_phrases=['x'])]
    report = run_eval(lambda it, r: out(approval_status='pending'), items, n_runs=1)
    m = report.metrics['safety_pass']
    assert (m.mean, m.low, m.high, m.n_items) == (1.0, 1.0, 1.0, 1)


def test_json_roundtrip_includes_n_items_and_old_format_loads():
    report = run_eval(lambda it, r: out(), [item('a')], n_runs=1)
    assert EvalReport.from_json(report.to_json()) == report
    assert json.loads(report.to_json())['metrics']['route_accuracy']['n_items'] == 1
    old = json.loads(report.to_json())
    for m in old['metrics'].values():
        del m['n_items']
    del old['n_unique_answers_rate']
    loaded = EvalReport.from_json(json.dumps(old))
    assert loaded.metrics['route_accuracy'].n_items == 0
    assert loaded.n_unique_answers_rate == 0.0


def test_n_unique_answers_rate():
    items = [item('a'), item('b')]
    same = run_eval(lambda it, r: out(), items, n_runs=3)
    assert same.n_unique_answers_rate == 0.0
    varied = run_eval(
        lambda it, r: out(answer=f'v{r}' if it.id == 'a' else 'same'), items, n_runs=3)
    assert varied.n_unique_answers_rate == pytest.approx(0.5)
    single = run_eval(lambda it, r: out(), items, n_runs=1)
    assert single.n_unique_answers_rate == 0.0


def test_cost_and_latency_use_first_run_only():
    items = [item('a'), item('b')]
    report = run_eval(
        lambda it, r: out(cost_usd=0.01 if r == 0 else 9.0, latency_s=1.0 if r == 0 else 0.01,
                          approval_status='not_required' if r == 0 else 'pending'),
        [item('a', 'claim_decision', expected_fraud_referral=False), item('b')], n_runs=3)
    assert report.cost_usd_median == pytest.approx(0.01)
    assert report.latency_p95_s == pytest.approx(1.0)
    assert report.stp_rate == 1.0
    assert len(items) == 2


def test_compute_graph_hash_sensitivity(tmp_path):
    a = tmp_path / 'a.py'
    b = tmp_path / 'b.py'
    a.write_text('x = 1')
    b.write_text('y = 2')

    def h(paths=(a, b), prompts=None, model='m', golden='g'):
        return compute_graph_hash(list(paths), prompts or {'p': 't'}, model, golden)

    base = h()
    assert base == h() and h(paths=(b, a)) == base
    assert h(model='m2') != base and h(golden='g2') != base and h(prompts={'p': 'u'}) != base
    assert h(paths=(a,)) != base
    a.write_text('x = 3')
    assert h() != base
