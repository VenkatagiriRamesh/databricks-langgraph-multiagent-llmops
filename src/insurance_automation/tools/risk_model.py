"""Interpretable underwriting risk model: logistic regression, reason codes, fairness audit.

Sex is deliberately not a feature (EU gender-neutral pricing, UW-01).
"""
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
from sklearn.linear_model import LogisticRegression

REGIONS = ('northeast', 'northwest', 'southeast', 'southwest')
FEATURE_NAMES = ['age', 'bmi', 'children', 'smoker'] + [f'region_{r}' for r in REGIONS]
HIGH_COST_QUANTILE = 0.75
LOW_BELOW, HIGH_FROM = 0.35, 0.65
Band = Literal['low', 'medium', 'high']


@dataclass(frozen=True)
class ReasonCode:
    feature: str
    direction: Literal['increases', 'decreases']
    contribution: float


def describe_reason(code: ReasonCode, applicant: dict) -> str:
    """Human text for a reason code that states the applicant's ACTUAL value and the direction."""
    effect = 'raises risk' if code.direction == 'increases' else 'lowers risk'
    if code.feature.startswith('region_'):
        return f'region: {applicant.get("region", "unknown")} ({effect})'
    label = 'smoker status' if code.feature == 'smoker' else code.feature
    return f'{label}: {applicant.get(code.feature, "unknown")} ({effect})'


@dataclass(frozen=True)
class RiskScore:
    probability: float
    band: Band
    reason_codes: list[ReasonCode] = field(default_factory=list)


def band_for(probability: float) -> Band:
    if probability < LOW_BELOW:
        return 'low'
    return 'medium' if probability < HIGH_FROM else 'high'


def _vector(features: dict) -> np.ndarray:
    return np.array(
        [float(features['age']), float(features['bmi']), float(features['children']),
         1.0 if features['smoker'] == 'yes' else 0.0]
        + [1.0 if features['region'] == r else 0.0 for r in REGIONS]
    )


@dataclass
class RiskModel:
    feature_names: list[str]
    means: np.ndarray
    scales: np.ndarray
    coef: np.ndarray
    intercept: float
    charge_cutoff: float

    def score(self, features: dict) -> RiskScore:
        z = (_vector(features) - self.means) / self.scales
        contributions = self.coef * z
        probability = float(1.0 / (1.0 + np.exp(-(self.intercept + contributions.sum()))))
        top = np.argsort(-np.abs(contributions))[:3]
        codes = [
            ReasonCode(
                self.feature_names[i],
                'increases' if contributions[i] > 0 else 'decreases',
                round(float(contributions[i]), 4),
            )
            for i in top
        ]
        return RiskScore(round(probability, 4), band_for(probability), codes)


def train_risk_model(rows: list[dict]) -> RiskModel:
    charges = np.array([float(r['charges']) for r in rows])
    cutoff = float(np.quantile(charges, HIGH_COST_QUANTILE))
    X = np.array([_vector(r) for r in rows])
    y = (charges > cutoff).astype(int)
    means = X.mean(axis=0)
    scales = X.std(axis=0)
    scales[scales == 0] = 1.0
    clf = LogisticRegression(max_iter=1000).fit((X - means) / scales, y)
    return RiskModel(list(FEATURE_NAMES), means, scales, clf.coef_[0], float(clf.intercept_[0]), cutoff)


@dataclass(frozen=True)
class FairnessReport:
    attribute: str
    groups: dict[str, float]
    disparate_impact_ratio: float
    passes_four_fifths: bool


def fairness_report(model, rows: list[dict], attribute: str) -> FairnessReport:
    """Favourable outcome = not classified high risk. Ratio = lowest group rate / highest."""
    totals: dict[str, int] = {}
    favourable: dict[str, int] = {}
    for row in rows:
        group = str(row[attribute])
        totals[group] = totals.get(group, 0) + 1
        favourable[group] = favourable.get(group, 0) + (model.score(row).band != 'high')
    rates = {g: favourable[g] / totals[g] for g in totals}
    highest = max(rates.values())
    ratio = min(rates.values()) / highest if highest else 1.0
    return FairnessReport(attribute, rates, ratio, ratio >= 0.8)
