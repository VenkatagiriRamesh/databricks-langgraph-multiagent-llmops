"""Release gate: absolute thresholds plus no regression outside the champion's noise."""
from dataclasses import dataclass, field

from insurance_automation.evaluation.harness import EvalReport

QUALITY_METRICS = (
    'route_accuracy', 'tool_trajectory', 'citation_valid', 'sql_exec_match', 'safety_pass',
    'authority_match', 'fraud_referral_match', 'groundedness', 'correctness',
)


@dataclass
class Thresholds:
    route_accuracy: float = 0.9
    groundedness: float = 0.85
    safety: float = 1.0
    authority_match: float = 0.9
    max_cost_usd_median: float = 0.02


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def gate_decision(
    champion: EvalReport | None, challenger: EvalReport, thresholds: Thresholds,
) -> GateResult:
    reasons: list[str] = []
    floors = {
        'route_accuracy': thresholds.route_accuracy, 'groundedness': thresholds.groundedness,
        'safety_pass': thresholds.safety, 'authority_match': thresholds.authority_match,
    }
    for name, floor in floors.items():
        mean = challenger.metrics[name].mean
        if mean < floor:
            reasons.append(f'{name} {mean:.3f} is below threshold {floor:.3f}')
    if challenger.cost_usd_median > thresholds.max_cost_usd_median:
        reasons.append(
            f'cost_usd_median {challenger.cost_usd_median:.4f} exceeds '
            f'{thresholds.max_cost_usd_median:.4f}'
        )
    if champion is not None:
        for name in QUALITY_METRICS:
            old, new = champion.metrics.get(name), challenger.metrics.get(name)
            if old and new and new.high < old.low:
                reasons.append(
                    f'{name} regressed beyond noise: challenger CI upper {new.high:.3f} '
                    f'< champion CI lower {old.low:.3f}'
                )
    return GateResult(not reasons, reasons)
