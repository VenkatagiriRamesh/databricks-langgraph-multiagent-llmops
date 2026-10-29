"""Deterministic coverage verification against policy terms, citing clause ids."""
from dataclasses import dataclass, field
from datetime import date

COVER_CLAUSE = {
    'inpatient': 'COV-01', 'outpatient': 'COV-02', 'emergency': 'COV-03',
    'pharmacy': 'COV-04', 'dental': 'COV-05',
}
EXCLUDED_BY = {'cosmetic': 'EXC-01', 'experimental': 'EXC-02', 'dental': 'EXC-05'}
REPORTING_DEADLINE_DAYS = 45


@dataclass(frozen=True)
class CoverageDecision:
    covered: bool
    reasons: list[str] = field(default_factory=list)
    clause_ids: list[str] = field(default_factory=list)
    payable_amount: float = 0.0


def _days(later: str, earlier: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def check_coverage(claim: dict, policy: dict) -> CoverageDecision:
    claim_type = claim['claim_type']
    exclusions = {c for c in policy['exclusions'].split('|') if c}

    clause = EXCLUDED_BY.get(claim_type)
    if clause in exclusions:
        return CoverageDecision(False, [f'{claim_type} is excluded by {clause}'], [clause])

    cover = COVER_CLAUSE.get(claim_type)
    if cover is None:
        return CoverageDecision(False, [f'no coverage clause applies to {claim_type}'], [])

    if claim_type != 'emergency' and _days(claim['loss_date'], policy['inception_date']) < policy['waiting_period_days']:
        return CoverageDecision(
            False, ['loss falls inside the waiting period (WAIT-01)'], ['WAIT-01']
        )

    payable = round(max(min(claim['amount'] - policy['deductible'], policy['coverage_limit']), 0.0), 2)
    reasons = [f'covered under {cover}', f'deductible {policy["deductible"]} and limit {policy["coverage_limit"]} applied (DED-01)']
    clauses = [cover, 'DED-01']
    if _days(claim['reported_date'], claim['loss_date']) > REPORTING_DEADLINE_DAYS:
        reasons.append(f'reported after the {REPORTING_DEADLINE_DAYS}-day deadline (RPT-01); review advised')
        clauses.append('RPT-01')
    return CoverageDecision(True, reasons, clauses, payable)
