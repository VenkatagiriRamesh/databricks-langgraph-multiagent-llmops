import json

import pandas as pd

from insurance_automation.tools.risk_model import train_risk_model
from insurance_automation.tools.risk_pyfunc import RiskModelPyfunc
from tests.tools.test_risk_model import make_rows


def test_pyfunc_predict_returns_probability_band_and_top_reason():
    wrapper = RiskModelPyfunc(train_risk_model(make_rows(500, seed=3)))
    frame = pd.DataFrame([
        {'age': 58, 'bmi': 38.0, 'children': 1, 'smoker': 'yes', 'region': 'southeast'},
        {'age': 24, 'bmi': 21.0, 'children': 0, 'smoker': 'no', 'region': 'northwest'},
    ])
    out = wrapper.predict(None, frame)
    assert list(out.columns) == ['probability', 'band', 'top_reason', 'reason_codes']
    assert len(out) == 2
    assert out.loc[0, 'probability'] > out.loc[1, 'probability']
    assert out.loc[0, 'top_reason'] == 'smoker'


def test_pyfunc_ignores_sex_column_if_present():
    wrapper = RiskModelPyfunc(train_risk_model(make_rows(500, seed=3)))
    base = {'age': 40, 'bmi': 30.0, 'children': 2, 'smoker': 'no', 'region': 'northeast'}
    a = wrapper.predict(None, pd.DataFrame([{**base, 'sex': 'male'}]))
    b = wrapper.predict(None, pd.DataFrame([{**base, 'sex': 'female'}]))
    assert a.loc[0, 'probability'] == b.loc[0, 'probability']


def test_pyfunc_reason_codes_json_round_trips_to_model_score():
    model = train_risk_model(make_rows(500, seed=3))
    features = {'age': 58, 'bmi': 38.0, 'children': 1, 'smoker': 'yes', 'region': 'southeast'}
    out = RiskModelPyfunc(model).predict(None, pd.DataFrame([features]))
    codes = json.loads(out.loc[0, 'reason_codes'])
    expected = model.score(features).reason_codes
    assert [(c['feature'], c['direction'], c['contribution']) for c in codes] == [
        (c.feature, c.direction, c.contribution) for c in expected]
