from dataclasses import dataclass

from insurance_automation.llm.base import LLMResult

# NOTIONAL estimates in USD per million tokens (input, output), taken from public list
# prices. Databricks Free Edition does not bill per token, so these only size the cost of a
# run. Re-verify against current published prices before quoting them in any document.
PRICE_PER_MILLION_TOKENS_USD: dict[str, tuple[float, float]] = {
    'databricks-meta-llama-3-3-70b-instruct': (0.50, 1.50),
    'databricks-meta-llama-3-1-8b-instruct': (0.15, 0.45),
    'databricks-gpt-oss-120b': (0.15, 0.60),
}


@dataclass
class NodeCost:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0


class CostLedger:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.priced = model_id in PRICE_PER_MILLION_TOKENS_USD
        self._nodes: dict[str, NodeCost] = {}

    def record(self, node: str, result: LLMResult) -> None:
        price_in, price_out = PRICE_PER_MILLION_TOKENS_USD.get(self.model_id, (0.0, 0.0))
        cost = self._nodes.setdefault(node, NodeCost())
        cost.calls += 1
        cost.tokens_in += result.tokens_in
        cost.tokens_out += result.tokens_out
        cost.usd += (result.tokens_in * price_in + result.tokens_out * price_out) / 1_000_000

    def summary(self) -> dict[str, NodeCost]:
        return dict(self._nodes)

    def total_usd(self) -> float:
        return sum(c.usd for c in self._nodes.values())

    def total_tokens(self) -> tuple[int, int]:
        nodes = self._nodes.values()
        return sum(c.tokens_in for c in nodes), sum(c.tokens_out for c in nodes)

    def reset(self) -> None:
        self._nodes.clear()
