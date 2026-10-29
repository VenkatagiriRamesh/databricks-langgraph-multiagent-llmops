"""MLflow pyfunc wrapper so the risk model can be registered in Unity Catalog and loaded by alias."""
import mlflow.pyfunc
import pandas as pd

from insurance_automation.tools.risk_model import RiskModel


class RiskModelPyfunc(mlflow.pyfunc.PythonModel):
    def __init__(self, model: RiskModel):
        self.model = model

    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        scores = [self.model.score(row) for row in model_input.to_dict(orient='records')]
        return pd.DataFrame({
            'probability': [s.probability for s in scores],
            'band': [s.band for s in scores],
            'top_reason': [s.reason_codes[0].feature if s.reason_codes else '' for s in scores],
        })
