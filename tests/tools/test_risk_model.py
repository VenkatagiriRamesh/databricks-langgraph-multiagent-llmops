import random

import pytest
from sklearn.metrics import roc_auc_score

from insurance_automation.tools.risk_model import (
    RiskScore,
    band_for,
    fairness_report,
    train_risk_model,
)


def make_rows(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        age = rng.randint(18, 64)
        bmi = round(rng.uniform(17, 45), 1)
        smoker = rng.choice(('yes', 'no', 'no', 'no'))
        children = rng.randint(0, 4)
        region = rng.choice(('northeast', 'northwest', 'southeast', 'southwest'))
        charges = (
            3000 + 260 * age + (22000 if smoker == 'yes' else 0)
            + 450 * max(bmi - 30, 0) + 400 * children + rng.gauss(0, 2500)
        )
        rows.append({'age': age, 'sex': rng.choice(('male', 'female')), 'bmi': bmi,
                     'children': children, 'smoker': smoker, 'region': region,
                     'charges': charges})
    return rows


@pytest.fixture(scope='module')
def model():
    return train_risk_model(make_rows(1500, seed=1))


def test_risk_band_thresholds():
    assert band_for(0.2) == 'low'
    assert band_for(0.5) == 'medium'
    assert band_for(0.8) == 'high'


def test_risk_model_auc_above_0_8_on_holdout(model):
    holdout = make_rows(600, seed=99)
    cutoff = sorted(r['charges'] for r in holdout)[int(0.75 * len(holdout))]
    y = [r['charges'] > cutoff for r in holdout]
    p = [model.score(r).probability for r in holdout]
    assert roc_auc_score(y, p) > 0.8


def test_score_returns_probability_band_and_three_reason_codes(model):
    s = model.score({'age': 55, 'sex': 'male', 'bmi': 36.0, 'children': 2,
                     'smoker': 'yes', 'region': 'southeast'})
    assert isinstance(s, RiskScore) and 0.0 <= s.probability <= 1.0
    assert s.band == band_for(s.probability)
    assert len(s.reason_codes) == 3
    assert s.reason_codes[0].feature == 'smoker'
    assert s.reason_codes[0].direction == 'increases'


def test_reason_codes_exclude_sex(model):
    assert 'sex' not in model.feature_names
    s = model.score({'age': 30, 'sex': 'female', 'bmi': 22.0, 'children': 0,
                     'smoker': 'no', 'region': 'northwest'})
    assert all(rc.feature != 'sex' for rc in s.reason_codes)


def test_score_ignores_sex_value(model):
    base = {'age': 45, 'bmi': 31.0, 'children': 1, 'smoker': 'no', 'region': 'northeast'}
    a = model.score({**base, 'sex': 'male'}).probability
    b = model.score({**base, 'sex': 'female'}).probability
    assert a == b


class StubModel:
    def __init__(self, favorable_by_group):
        self.favorable = favorable_by_group

    def score(self, features):
        high = not features['_favorable']
        return RiskScore(probability=0.9 if high else 0.1, band='high' if high else 'low',
                         reason_codes=[])


def rows_for(group_counts):
    rows = []
    for group, (favorable, total) in group_counts.items():
        rows += [{'sex': group, '_favorable': i < favorable} for i in range(total)]
    return rows


def test_fairness_report_four_fifths_rule_known_example_fails():
    rep = fairness_report(StubModel(None), rows_for({'male': (8, 10), 'female': (5, 10)}), 'sex')
    assert rep.groups == {'male': 0.8, 'female': 0.5}
    assert rep.disparate_impact_ratio == pytest.approx(0.625)
    assert rep.passes_four_fifths is False


def test_fairness_report_known_example_passes():
    rep = fairness_report(StubModel(None), rows_for({'male': (8, 10), 'female': (7, 10)}), 'sex')
    assert rep.disparate_impact_ratio == pytest.approx(0.875)
    assert rep.passes_four_fifths is True
