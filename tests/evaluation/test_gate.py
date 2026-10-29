
from insurance_automation.evaluation.gate import Thresholds, gate_decision
from insurance_automation.evaluation.harness import EvalReport, MetricResult
from scripts.gate_release import main

GOOD = {
    'route_accuracy': 0.95, 'tool_trajectory': 0.9, 'citation_valid': 0.9, 'sql_exec_match': 0.9,
    'safety_pass': 1.0, 'authority_match': 0.95, 'fraud_referral_match': 0.95, 'groundedness': 0.9,
    'correctness': 0.9, 'within_cost_budget': 1.0,
}


def report(spread=0.02, cost=0.01, **over):
    vals = {**GOOD, **over}
    return EvalReport(
        metrics={k: MetricResult(v, v - spread, v + spread) for k, v in vals.items()},
        failures=[], by_failure_mode={}, cost_usd_median=cost, latency_p95_s=1.0, stp_rate=0.5,
        escalation_rate=0.1, fraud_precision=None, fraud_recall=None, n_items=5, n_runs=3,
        graph_hash='h',
    )


def test_pass_no_champion():
    assert gate_decision(None, report(), Thresholds()).passed


def test_fail_below_absolute_names_metric():
    r = gate_decision(None, report(route_accuracy=0.8), Thresholds())
    assert not r.passed and 'route_accuracy' in r.reasons[0] and '0.8' in r.reasons[0]


def test_fail_on_cost():
    assert not gate_decision(None, report(cost=0.05), Thresholds()).passed


def test_safety_must_be_perfect():
    r = gate_decision(None, report(safety_pass=0.99), Thresholds())
    assert not r.passed and 'safety_pass' in r.reasons[0]


def test_fail_on_regression_beyond_noise():
    r = gate_decision(report(), report(correctness=0.8), Thresholds())
    assert not r.passed and any('correctness' in x for x in r.reasons)


def test_pass_within_noise():
    assert gate_decision(report(), report(correctness=0.88), Thresholds()).passed


def write(tmp_path, name, rep):
    p = tmp_path / name
    p.write_text(rep.to_json())
    return str(p)


def test_gate_release_exit_codes(tmp_path, capsys):
    good = write(tmp_path, 'g.json', report())
    bad = write(tmp_path, 'b.json', report(route_accuracy=0.5))
    assert main(['--report', good, '--offline']) == 0
    assert main(['--report', bad, '--offline']) == 1
    assert 'route_accuracy' in capsys.readouterr().out
    assert main(['--report', good, '--champion-report', good, '--offline']) == 0
