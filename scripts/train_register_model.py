"""Train the underwriting risk model, audit it for fairness, register it in Unity Catalog.

Run: python -m scripts.train_register_model
Registers insurance_automation.models.risk_classifier and sets alias `champion`.
"""
import json
import os

import mlflow
import pandas as pd
from mlflow import MlflowClient
from sklearn.metrics import roc_auc_score

from insurance_automation.common.config import load_config
from insurance_automation.common.sql import run_sql
from insurance_automation.tools.risk_model import fairness_report, train_risk_model
from insurance_automation.tools.risk_pyfunc import RiskModelPyfunc

HOLDOUT_EVERY = 5  # every 5th applicant is held out for evaluation
FAIRNESS_ATTRIBUTES = ('sex', 'region')


def load_applicants(cfg) -> list[dict]:
    rows = run_sql(
        f'SELECT applicant_id, age, sex, bmi, children, smoker, region, charges '
        f'FROM {cfg.schema("curated")}.applicants ORDER BY applicant_id',
        cfg.warehouse_id,
    )
    return [
        {'applicant_id': r['applicant_id'], 'age': int(r['age']), 'sex': r['sex'],
         'bmi': float(r['bmi']), 'children': int(r['children']), 'smoker': r['smoker'],
         'region': r['region'], 'charges': float(r['charges'])}
        for r in rows
    ]


def main() -> None:
    cfg = load_config(require_warehouse=True)
    rows = load_applicants(cfg)
    train = [r for i, r in enumerate(rows) if i % HOLDOUT_EVERY]
    holdout = [r for i, r in enumerate(rows) if i % HOLDOUT_EVERY == 0]

    model = train_risk_model(train)
    y = [r['charges'] > model.charge_cutoff for r in holdout]
    auc = roc_auc_score(y, [model.score(r).probability for r in holdout])
    fairness = {a: fairness_report(model, holdout, a) for a in FAIRNESS_ATTRIBUTES}
    print(f'holdout AUC {auc:.3f} on {len(holdout)} applicants')
    for attr, rep in fairness.items():
        print(f'fairness[{attr}] ratio={rep.disparate_impact_ratio:.3f} '
              f'four_fifths={rep.passes_four_fifths} groups={rep.groups}')

    mlflow.set_tracking_uri('databricks')
    mlflow.set_registry_uri('databricks-uc')
    user = os.environ.get('USER_EMAIL', 'venkatagiriramesh11@gmail.com')
    mlflow.set_experiment(f'/Users/{user}/insurance_automation_risk_model')
    name = f'{cfg.schema("models")}.risk_classifier'
    example = pd.DataFrame([{k: holdout[0][k] for k in ('age', 'bmi', 'children', 'smoker', 'region')}])
    with mlflow.start_run(run_name='risk_classifier'):
        mlflow.log_params({'model': 'logistic_regression', 'features_exclude': 'sex',
                           'high_cost_quantile': 0.75, 'train_rows': len(train)})
        mlflow.log_metric('holdout_auc', auc)
        for attr, rep in fairness.items():
            mlflow.log_metric(f'disparate_impact_{attr}', rep.disparate_impact_ratio)
        mlflow.log_text(json.dumps(
            {a: {'groups': r.groups, 'ratio': r.disparate_impact_ratio, 'passes': r.passes_four_fifths}
             for a, r in fairness.items()}, indent=2), 'fairness_report.json')
        mlflow.pyfunc.log_model(
            name='model', python_model=RiskModelPyfunc(model), input_example=example,
            code_paths=['src/insurance_automation'], registered_model_name=name,
            pip_requirements=['mlflow', 'scikit-learn', 'numpy', 'pandas'],
        )
    client = MlflowClient()
    latest = max(client.search_model_versions(f"name='{name}'"), key=lambda v: int(v.version))
    client.set_registered_model_alias(name, 'champion', latest.version)
    loaded = mlflow.pyfunc.load_model(f'models:/{name}@champion')
    print('loaded by alias, sample:', loaded.predict(example).to_dict(orient='records'))


if __name__ == '__main__':
    main()
