import pytest

from insurance_automation.llm.base import LLMResult
from insurance_automation.llm.cost import PRICE_PER_MILLION_TOKENS_USD, CostLedger

MODEL = 'databricks-meta-llama-3-3-70b-instruct'


def test_ledger_aggregates_by_node():
    ledger = CostLedger(MODEL)
    ledger.record('a', LLMResult('x', 10, 5))
    ledger.record('a', LLMResult('x', 20, 5))
    ledger.record('b', LLMResult('x', 1, 1))
    summary = ledger.summary()
    assert summary['a'].calls == 2
    assert (summary['a'].tokens_in, summary['a'].tokens_out) == (30, 10)
    assert summary['b'].calls == 1
    ledger.reset()
    assert ledger.summary() == {}


def test_total_cost_uses_price_table():
    price_in, price_out = PRICE_PER_MILLION_TOKENS_USD[MODEL]
    ledger = CostLedger(MODEL)
    ledger.record('a', LLMResult('x', 1_000_000, 2_000_000))
    assert ledger.priced is True
    assert ledger.total_usd() == pytest.approx(price_in + 2 * price_out)


def test_unknown_model_prices_at_zero():
    ledger = CostLedger('mystery-model')
    ledger.record('a', LLMResult('x', 1_000_000, 1_000_000))
    assert ledger.priced is False
    assert ledger.total_usd() == 0.0
