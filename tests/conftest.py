from collections.abc import Callable

import pytest

from insurance_automation.llm.base import LLMResult


class FakeLLM:
    """Offline LLM. `responses` is a dict keyed by node name or a callable (prompt, system, node) -> str."""

    def __init__(self, responses: dict[str, str] | Callable[[str, str, str], str] | None = None,
                 default: str = 'OK'):
        self.responses = responses or {}
        self.default = default
        self.calls: list[dict] = []

    def invoke(self, prompt: str, *, system: str = '', node: str = '') -> LLMResult:
        self.calls.append({'prompt': prompt, 'system': system, 'node': node})
        if callable(self.responses):
            text = self.responses(prompt, system, node)
        else:
            text = self.responses.get(node, self.default)
        return LLMResult(text=text, tokens_in=max(1, len(prompt) // 4), tokens_out=max(1, len(text) // 4))


class FakeLedger:
    def __init__(self):
        self.records: list[tuple[str, LLMResult]] = []

    def record(self, node: str, result: LLMResult) -> None:
        self.records.append((node, result))


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def fake_ledger():
    return FakeLedger()
