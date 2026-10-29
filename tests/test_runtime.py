import json

import pandas as pd
import pytest

import insurance_automation.runtime as rt
from insurance_automation.common.config import Config
from insurance_automation.runtime import build_live_context, refresh_token_env
from insurance_automation.tools.risk_model import RiskScore
from tests.conftest import FakeLedger, FakeLLM
from tests.tools.test_risk_model import make_rows

CFG = Config(catalog='cat', fm_model='fm-model', warehouse_id='wh1')


class FakeSQL:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.calls: list[str] = []

    def __call__(self, statement, warehouse_id):
        assert warehouse_id == 'wh1'
        self.calls.append(statement)
        for needle, result in self.rows.items():
            if needle in statement:
                return result
        return []


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    monkeypatch.setattr(rt, 'DatabricksLLM', lambda model: FakeLLM())
    monkeypatch.chdir(tmp_path)


def make_ctx(sql=None, **kw):
    kw.setdefault('ledger', FakeLedger())
    return build_live_context(CFG, sql=sql or FakeSQL(), **kw)


@pytest.mark.parametrize('getter,bad', [
    ('get_claim', "C00001' OR '1'='1"),
    ('get_claim', 'C1'),
    ('get_policy', "P0001' OR '1'='1"),
    ('get_applicant', "A0001'; DROP TABLE x; --"),
    ('get_history', "A0001' OR '1'='1"),
])
def test_ids_are_validated_before_sql(getter, bad):
    sql = FakeSQL()
    ctx = make_ctx(sql)
    with pytest.raises(ValueError):
        getattr(ctx.tools, getter)(bad)
    assert sql.calls == []


def test_getters_convert_types_and_return_none_when_empty():
    sql = FakeSQL({
        'curated.claims WHERE claim_id': [{
            'claim_id': 'C00001', 'amount': '123.5', 'seeded_fraud': 'true',
            'has_injection': 'false', 'loss_date': '2025-01-02'}],
        'curated.policies': [{'policy_id': 'P0001', 'deductible': '500',
                              'coverage_limit': '50000', 'waiting_period_days': '30'}],
        'curated.applicants': [{'applicant_id': 'A0001', 'age': '40', 'children': '2',
                                'bmi': '30.5', 'charges': '1000.0', 'smoker': 'no'}],
    })
    tools = make_ctx(sql).tools
    claim = tools.get_claim('C00001')
    assert claim['amount'] == 123.5 and claim['seeded_fraud'] is True
    assert claim['has_injection'] is False and claim['loss_date'] == '2025-01-02'
    pol = tools.get_policy('P0001')
    assert (pol['deductible'], pol['coverage_limit'], pol['waiting_period_days']) == (500, 50000, 30)
    app = tools.get_applicant('A0001')
    assert app['age'] == 40 and app['children'] == 2 and app['bmi'] == 30.5
    assert app['charges'] == 1000.0 and app['smoker'] == 'no'
    empty = make_ctx(FakeSQL()).tools
    assert empty.get_claim('C00002') is None
    assert empty.get_policy('P0002') is None
    assert empty.get_applicant('A0002') is None
    assert empty.get_history('A0002') == []


def test_get_history_orders_by_loss_date():
    sql = FakeSQL({'FROM cat.curated.claims': [
        {'claim_id': 'C00002', 'applicant_id': 'A0001', 'loss_date': '2025-02-01'}]})
    out = make_ctx(sql).tools.get_history('A0001')
    assert out == [{'claim_id': 'C00002', 'applicant_id': 'A0001', 'loss_date': '2025-02-01'}]
    assert 'ORDER BY loss_date' in sql.calls[0] and "'A0001'" in sql.calls[0]


def test_search_policy_loads_docs_once():
    docs = [
        {'doc_id': 'D1', 'title': 'Cosmetic surgery exclusion',
         'body': 'Cosmetic surgery is excluded from cover.'},
        {'doc_id': 'D2', 'title': 'Waiting period', 'body': 'A thirty day waiting period applies.'},
    ]
    sql = FakeSQL({'policy_docs': docs})
    tools = make_ctx(sql).tools
    hits = tools.search_policy('cosmetic surgery exclusion', 2)
    tools.search_policy('waiting period', 2)
    assert hits[0].doc_id == 'D1'
    assert len(sql.calls) == 1


def test_run_query_passes_statement_through():
    sql = FakeSQL({'SELECT 1': [{'x': '1'}]})
    assert make_ctx(sql).tools.run_query('SELECT 1') == [{'x': '1'}]
    assert sql.calls == ['SELECT 1']


FEATURES = {'age': 58, 'bmi': 38.0, 'children': 1, 'smoker': 'yes', 'region': 'southeast'}


class FakeModel:
    def predict(self, frame):
        assert isinstance(frame, pd.DataFrame)
        codes = [{'feature': 'smoker', 'direction': 'increases', 'contribution': 1.2}]
        return pd.DataFrame({'probability': [0.8], 'band': ['high'], 'top_reason': ['smoker'],
                             'reason_codes': [json.dumps(codes)]})


def test_score_risk_rebuilds_reason_codes_from_registered_model():
    ctx = make_ctx(load_risk_model=lambda: FakeModel())
    score = ctx.tools.score_risk(FEATURES)
    assert isinstance(score, RiskScore)
    assert (score.probability, score.band) == (0.8, 'high')
    assert score.reason_codes[0].feature == 'smoker' and score.reason_codes[0].contribution == 1.2
    assert ctx.tools.risk_source == 'registered'


def test_score_risk_falls_back_to_in_process_training_when_loader_raises():
    rows = [{**r, 'applicant_id': f'A{i:04d}', 'age': str(r['age']), 'bmi': str(r['bmi']),
             'children': str(r['children']), 'charges': str(r['charges'])}
            for i, r in enumerate(make_rows(300, seed=1))]
    sql = FakeSQL({'curated.applicants': rows})

    def boom():
        raise RuntimeError('no registry')

    ctx = make_ctx(sql, load_risk_model=boom)
    assert ctx.tools.risk_source == 'unloaded'
    score = ctx.tools.score_risk(FEATURES)
    assert score.band in ('low', 'medium', 'high') and score.reason_codes
    assert ctx.tools.risk_source == 'trained_in_process'
    ctx.tools.score_risk(FEATURES)
    assert len(sql.calls) == 1


def test_build_live_context_wraps_databricks_llm_without_network(monkeypatch, tmp_path):
    created = {}

    class StubLLM:
        def __init__(self, model):
            created['model'] = model

    monkeypatch.setattr(rt, 'DatabricksLLM', StubLLM)
    ctx = build_live_context(CFG, cache_dir=str(tmp_path), sql=FakeSQL())
    assert created['model'] == 'fm-model'
    assert ctx.llm.model_id == 'fm-model' and ctx.llm.cache_dir == str(tmp_path)
    assert ctx.ledger.model_id == 'fm-model'
    assert ctx.prompts is not None
    ctx2 = build_live_context(CFG, cache_dir=str(tmp_path), sql=FakeSQL(), llm_model='other')
    assert created['model'] == 'other' and ctx2.ledger.model_id == 'other'


def test_refresh_token_env_sets_env_and_never_prints_token(monkeypatch, capsys):
    monkeypatch.setenv('DATABRICKS_CONFIG_PROFILE', 'prof')
    monkeypatch.delenv('DATABRICKS_TOKEN', raising=False)
    seen = {}

    def fake_run(cmd):
        seen['cmd'] = cmd
        return json.dumps({'access_token': 'SECRET-TOKEN'})

    monkeypatch.setattr(rt, '_databricks_host', lambda profile: 'https://h.example')
    refresh_token_env(run=fake_run)
    import os
    assert os.environ['DATABRICKS_TOKEN'] == 'SECRET-TOKEN'
    assert os.environ['DATABRICKS_HOST'] == 'https://h.example'
    assert 'prof' in seen['cmd']
    captured = capsys.readouterr()
    assert 'SECRET-TOKEN' not in captured.out + captured.err
    monkeypatch.delenv('DATABRICKS_TOKEN')
    monkeypatch.delenv('DATABRICKS_HOST')
