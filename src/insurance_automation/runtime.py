"""Live wiring: builds a NodeContext backed by the SQL warehouse, Foundation Models and MLflow.

`risk_source` is exposed on the returned tools (`ctx.tools.risk_source`): 'unloaded' until the
first score_risk call, then 'registered' (champion model) or 'trained_in_process' (fallback).
"""
import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from insurance_automation.agents.nodes import NodeContext, Tools
from insurance_automation.agents.prompts import DEFAULT_PROMPTS, LocalPromptStore
from insurance_automation.common.config import Config
from insurance_automation.common.sql import run_sql
from insurance_automation.llm.cached import CachedLLM
from insurance_automation.llm.cost import CostLedger
from insurance_automation.llm.databricks import DatabricksLLM
from insurance_automation.tools.retrieval import retrieve_policy
from insurance_automation.tools.risk_model import ReasonCode, RiskScore, train_risk_model

_INT = {'age', 'children', 'deductible', 'coverage_limit', 'waiting_period_days'}
_FLOAT = {'bmi', 'charges', 'amount'}
_BOOL = {'seeded_fraud', 'has_injection'}
_ID = {'claim': re.compile(r'^C\d{5}$'), 'policy': re.compile(r'^P\d{4}$'),
       'applicant': re.compile(r'^A\d{4}$')}


def _check_id(kind: str, value: str) -> str:
    if not isinstance(value, str) or not _ID[kind].fullmatch(value):
        raise ValueError(f'invalid {kind} id: {value!r}')
    return value


def _convert(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        if value is None:
            out[key] = None
        elif key in _INT:
            out[key] = int(float(value))
        elif key in _FLOAT:
            out[key] = float(value)
        elif key in _BOOL:
            out[key] = str(value).lower() == 'true'
        else:
            out[key] = value
    return out


def _load_registered_model(cfg: Config):
    import mlflow
    import mlflow.pyfunc
    mlflow.set_tracking_uri('databricks')
    mlflow.set_registry_uri('databricks-uc')
    return mlflow.pyfunc.load_model(f'models:/{cfg.schema("models")}.risk_classifier@champion')


class RiskScorer:
    """Scores with the registered model; falls back to in-process training. `source` says which."""

    def __init__(self, cfg: Config, sql: Callable[[str], list[dict]], load_risk_model: Callable | None):
        self._cfg, self._sql = cfg, sql
        self._load = load_risk_model or (lambda: _load_registered_model(cfg))
        self._model = None
        self.source = 'unloaded'

    def _ensure(self) -> None:
        if self._model is not None:
            return
        try:
            self._model = self._load()
            self.source = 'registered'
        except Exception:  # noqa: BLE001 - any load failure means fall back
            rows = self._sql(
                'SELECT age, sex, bmi, children, smoker, region, charges '
                f'FROM {self._cfg.schema("curated")}.applicants')
            self._model = train_risk_model([_convert(r) for r in rows])
            self.source = 'trained_in_process'

    def __call__(self, features: dict) -> RiskScore:
        self._ensure()
        if self.source == 'trained_in_process':
            return self._model.score(features)
        keys = ('age', 'bmi', 'children', 'smoker', 'region')
        out = self._model.predict(pd.DataFrame([{k: features[k] for k in keys}])).iloc[0]
        codes = [ReasonCode(c['feature'], c['direction'], float(c['contribution']))
                 for c in json.loads(out['reason_codes'])]
        return RiskScore(float(out['probability']), out['band'], codes)


@dataclass
class LiveTools(Tools):
    @property
    def risk_source(self) -> str:
        return self.score_risk.source


def build_live_context(cfg: Config, *, cache_dir: str = '.local_cache/llm',
                       llm_model: str | None = None, sql=run_sql, load_risk_model=None,
                       prompts=None, ledger=None) -> NodeContext:
    model = llm_model or cfg.fm_model
    llm = CachedLLM(DatabricksLLM(model), cache_dir, model_id=model)
    cur = cfg.schema('curated')

    def q(statement: str) -> list[dict]:
        return sql(statement, cfg.warehouse_id)

    def one(table: str, key: str, kind: str):
        def get(value: str) -> dict | None:
            rows = q(f"SELECT * FROM {cur}.{table} WHERE {key} = '{_check_id(kind, value)}'")
            return _convert(rows[0]) if rows else None
        return get

    def get_history(applicant_id: str) -> list[dict]:
        rows = q('SELECT claim_id, applicant_id, loss_date '
                 f"FROM {cur}.claims WHERE applicant_id = '{_check_id('applicant', applicant_id)}' "
                 'ORDER BY loss_date')
        return [_convert(r) for r in rows]

    docs: list[dict] = []

    def search_policy(query: str, k: int = 3):
        if not docs:
            docs.extend(q(f'SELECT doc_id, title, section, body FROM {cur}.policy_docs'))
        return retrieve_policy(query, docs, k)

    tools = LiveTools(
        run_query=q, search_policy=search_policy,
        get_claim=one('claims', 'claim_id', 'claim'),
        get_policy=one('policies', 'policy_id', 'policy'),
        get_applicant=one('applicants', 'applicant_id', 'applicant'),
        get_history=get_history, score_risk=RiskScorer(cfg, q, load_risk_model))
    return NodeContext(llm=llm, tools=tools, ledger=ledger or CostLedger(model),
                       prompts=prompts or LocalPromptStore(DEFAULT_PROMPTS))


def _cli(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def _databricks_host(profile: str) -> str:
    from databricks.sdk.core import Config as SdkConfig
    return SdkConfig(profile=profile).host


def refresh_token_env(run: Callable[[list[str]], str] = _cli) -> None:
    """Export DATABRICKS_HOST/DATABRICKS_TOKEN from `databricks auth token --profile
    $DATABRICKS_CONFIG_PROFILE` for long runs (CLI token refresh is flaky, see ADR-001).
    The token is only written to the environment, never printed or logged."""
    profile = os.environ.get('DATABRICKS_CONFIG_PROFILE', 'DEFAULT')
    token = json.loads(run(['databricks', 'auth', 'token', '--profile', profile]))['access_token']
    os.environ['DATABRICKS_HOST'] = _databricks_host(profile)
    os.environ['DATABRICKS_TOKEN'] = token
