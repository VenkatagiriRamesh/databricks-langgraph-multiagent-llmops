"""Explainable fraud screening. Flags justify referral for review, never automatic denial."""
import re
from dataclasses import dataclass
from datetime import date

REFER_THRESHOLD = 0.4
AUTHORITY_LIMITS = (2000, 10000, 25000)
_WEIGHTS = {
    'LATE_REPORT': 0.35, 'NEAR_INCEPTION': 0.30, 'ROUND_AMOUNT': 0.20,
    'JUST_UNDER_LIMIT': 0.25, 'REPEAT_CLAIMANT': 0.25, 'INCONSISTENT_NOTES': 0.20,
}
_NOTE_PATTERN = re.compile(r'could not|differ|cannot be verified', re.IGNORECASE)


@dataclass(frozen=True)
class FraudFlag:
    code: str
    evidence: str


@dataclass(frozen=True)
class FraudScreen:
    flags: list[FraudFlag]
    score: float
    refer_to_siu: bool


def _days(later: str, earlier: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def screen_fraud(claim: dict, policy: dict, history: list[dict]) -> FraudScreen:
    flags: list[FraudFlag] = []
    lag = _days(claim['reported_date'], claim['loss_date'])
    if lag > 45:
        flags.append(FraudFlag('LATE_REPORT', f'reported {lag} days after the loss'))
    since_inception = _days(claim['loss_date'], policy['inception_date'])
    if since_inception <= 30:
        flags.append(FraudFlag('NEAR_INCEPTION', f'loss {since_inception} days after policy inception'))
    amount = claim['amount']
    if amount >= 3000 and amount % 1000 == 0:
        flags.append(FraudFlag('ROUND_AMOUNT', f'amount {amount:.0f} is a round number'))
    for limit in AUTHORITY_LIMITS:
        if limit * 0.98 <= amount < limit:
            flags.append(FraudFlag('JUST_UNDER_LIMIT', f'amount {amount:.2f} is just under the {limit} authority limit'))
            break
    prior = [
        h for h in history
        if h['applicant_id'] == claim['applicant_id'] and h['claim_id'] != claim['claim_id']
        and 0 <= _days(claim['loss_date'], h['loss_date']) <= 365
    ]
    if len(prior) >= 3:
        flags.append(FraudFlag('REPEAT_CLAIMANT', f'{len(prior)} prior claims in the last 12 months'))
    if _NOTE_PATTERN.search(claim.get('adjuster_notes', '')):
        flags.append(FraudFlag('INCONSISTENT_NOTES', 'adjuster notes record unverified or inconsistent documentation'))
    score = round(min(sum(_WEIGHTS[f.code] for f in flags), 1.0), 2)
    return FraudScreen(flags, score, score >= REFER_THRESHOLD)
