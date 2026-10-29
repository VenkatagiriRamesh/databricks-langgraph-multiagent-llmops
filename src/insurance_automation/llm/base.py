from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMResult:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0


class LLM(Protocol):
    def invoke(self, prompt: str, *, system: str = '', node: str = '') -> LLMResult: ...


class LedgerLike(Protocol):
    def record(self, node: str, result: LLMResult) -> None: ...


class QuotaExceededError(RuntimeError):
    """Raised when the platform rejects a call because a Free Edition quota is exhausted."""
