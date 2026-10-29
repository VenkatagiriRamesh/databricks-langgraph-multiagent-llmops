"""Evaluation harness with resumable JSONL progress.

Runner signature: `runner(item: GoldenItem, run_index: int) -> AgentOutput`. The live script
builds the graph, calls `invoke` with a unique thread id per (item, run) and auto-approves any
pending approval (except safety items) via `make_runner`, so every run finishes.
"""
import json
import math
import statistics
from collections.abc import Callable
from dataclasses import asdict, dataclass

from insurance_automation.agents.graph import ESCALATION_ANSWER
from insurance_automation.contracts import AgentOutput
from insurance_automation.evaluation import scorers
from insurance_automation.evaluation.stats import mean_ci
from insurance_automation.evaluation.types import GoldenItem

SCORERS = {
    'route_accuracy': scorers.route_accuracy, 'tool_trajectory': scorers.tool_trajectory,
    'citation_valid': scorers.citation_valid, 'sql_exec_match': scorers.sql_exec_match,
    'safety_pass': scorers.safety_pass, 'authority_match': scorers.authority_match,
    'fraud_referral_match': scorers.fraud_referral_match,
    'within_cost_budget': scorers.within_cost_budget,
}
JUDGE_METRICS = ('groundedness', 'correctness')
MODES = ('routing', 'retrieval', 'sql', 'grounding', 'safety', 'authority')
_MODE_OF = {
    'route_accuracy': 'routing', 'tool_trajectory': 'routing', 'sql_exec_match': 'sql',
    'safety_pass': 'safety', 'authority_match': 'authority', 'fraud_referral_match': 'authority',
    'groundedness': 'grounding',
}
JUDGE_PASS = 0.75

Runner = Callable[[GoldenItem, int], AgentOutput]
Judge = Callable[[GoldenItem, AgentOutput], dict[str, float]]


@dataclass
class MetricResult:
    mean: float
    low: float
    high: float


@dataclass
class EvalReport:
    metrics: dict[str, MetricResult]
    failures: list[dict]
    by_failure_mode: dict[str, int]
    cost_usd_median: float
    latency_p95_s: float
    stp_rate: float
    escalation_rate: float
    fraud_precision: float | None
    fraud_recall: float | None
    n_items: int
    n_runs: int
    graph_hash: str
    n_fraud_positive: int = 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, text: str) -> 'EvalReport':
        data = json.loads(text)
        data.setdefault('n_fraud_positive', 0)
        data['metrics'] = {k: MetricResult(**v) for k, v in data['metrics'].items()}
        return cls(**data)


def _load(path: str | None, graph_hash: str) -> dict[tuple[str, int], dict]:
    done: dict[tuple[str, int], dict] = {}
    if not path:
        return done
    try:
        with open(path, encoding='utf-8') as handle:
            for line in handle:
                if line.strip():
                    rec = json.loads(line)
                    if rec['graph_hash'] == graph_hash:
                        done[(rec['id'], rec['run'])] = rec
    except FileNotFoundError:
        pass
    return done


def _clipped(mean: float, low: float, high: float) -> MetricResult:
    """All current metrics live in [0, 1], so the interval is clipped to it."""
    return MetricResult(mean, min(1.0, max(0.0, low)), min(1.0, max(0.0, high)))


def make_runner(graph, invoke_fn, resume_fn) -> Runner:
    """Build the live runner. Safety items stop at the human gate; others are auto-approved."""
    def runner(item: GoldenItem, run_index: int) -> AgentOutput:
        thread = f'{item.id}-{run_index}'
        result = invoke_fn(graph, item.question, thread)
        if result.status == 'pending_approval' and not item.safety_case:
            result = resume_fn(graph, thread, 'approve')
        return result.output
    return runner


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def _citation_mode(output: AgentOutput) -> str:
    fabricated = any(c not in output.hit_ids for c in output.citations)
    return 'grounding' if fabricated else 'retrieval'


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def run_eval(
    runner: Runner, items: list[GoldenItem], *, n_runs: int = 3, judge: Judge | None = None,
    results_path: str | None = None, graph_hash: str = 'dev',
) -> EvalReport:
    done = _load(results_path, graph_hash)
    for run in range(n_runs):
        for item in items:
            if (item.id, run) in done:
                continue
            output = runner(item, run)  # QuotaExceededError propagates; progress is already saved
            judged = judge(item, output) if judge else {}
            rec = {'id': item.id, 'run': run, 'graph_hash': graph_hash,
                   'output': asdict(output), 'judge': judged}
            done[(item.id, run)] = rec
            if results_path:
                with open(results_path, 'a', encoding='utf-8') as handle:
                    handle.write(json.dumps(rec) + '\n')
    return _aggregate(items, n_runs, graph_hash, done)


def _aggregate(items, n_runs, graph_hash, done) -> EvalReport:
    per_item: dict[str, dict[str, list[float]]] = {}
    failures: list[dict] = []
    modes = dict.fromkeys(MODES, 0)
    outputs: list[tuple[GoldenItem, AgentOutput]] = []
    for item in items:
        for run in range(n_runs):
            rec = done[(item.id, run)]
            output = AgentOutput(**rec['output'])
            outputs.append((item, output))
            scores = {name: fn(item, output) for name, fn in SCORERS.items()}
            scores.update({k: float(v) for k, v in rec['judge'].items() if k in JUDGE_METRICS})
            for name, score in scores.items():
                per_item.setdefault(name, {}).setdefault(item.id, []).append(score)
                passed = score >= JUDGE_PASS if name in JUDGE_METRICS else score >= 1.0
                if passed:
                    continue
                failures.append({'id': item.id, 'run': run, 'metric': name,
                                 'reason': f'{name} scored {score:.2f}'})
                mode = _citation_mode(output) if name == 'citation_valid' else _MODE_OF.get(name)
                if mode:
                    modes[mode] += 1
    # Per-item mean across runs first, then mean and 95% CI across items, so the interval
    # reflects item-to-item variation rather than treating repeat runs as independent.
    metrics = {
        name: _clipped(*mean_ci([statistics.fmean(v) for v in by_id.values()]))
        for name, by_id in per_item.items()
    }
    claims = [o for i, o in outputs if i.expected_route == 'claim_decision']
    stp = sum(o.approval_status == 'not_required' for o in claims) / len(claims) if claims else 0.0
    escalated = sum(o.answer == ESCALATION_ANSWER for _, o in outputs)
    tp = fp = fn = 0
    n_pos = 0
    for i, o in outputs:
        if i.expected_route != 'claim_decision' or i.expected_fraud_referral is None:
            continue
        predicted = bool(o.fraud_referred)
        n_pos += bool(i.expected_fraud_referral)
        tp += predicted and i.expected_fraud_referral
        fp += predicted and not i.expected_fraud_referral
        fn += (not predicted) and i.expected_fraud_referral
    return EvalReport(
        metrics=metrics, failures=failures, by_failure_mode=modes,
        cost_usd_median=statistics.median(o.cost_usd for _, o in outputs),
        latency_p95_s=_percentile([o.latency_s for _, o in outputs], 0.95),
        stp_rate=stp, escalation_rate=escalated / len(outputs),
        fraud_precision=_ratio(tp, tp + fp), fraud_recall=_ratio(tp, tp + fn),
        n_items=len(items), n_runs=n_runs, graph_hash=graph_hash,
        n_fraud_positive=n_pos,
    )
