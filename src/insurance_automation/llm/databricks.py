import time
from collections.abc import Callable

from insurance_automation.llm.base import LLMResult, QuotaExceededError


def _status(exc: Exception) -> int | None:
    status = getattr(exc, 'status_code', None)
    return status if isinstance(status, int) else None


def _is_quota(exc: Exception) -> bool:
    text = str(exc).lower()
    return _status(exc) == 429 or 'quota' in text or 'rate limit' in text


def _is_transient(exc: Exception) -> bool:
    status = _status(exc)
    if status is not None:
        return status >= 500
    return isinstance(exc, (ConnectionError, TimeoutError)) or any(
        w in type(exc).__name__ for w in ('Connection', 'Timeout'))


class DatabricksLLM:
    def __init__(self, model: str, max_retries: int = 3, max_tokens: int = 1024, client=None,
                 sleep: Callable[[float], None] = time.sleep):
        self.model = model
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self._client = client
        self._sleep = sleep

    def _get_client(self):
        if self._client is None:
            from databricks.sdk import WorkspaceClient
            self._client = WorkspaceClient().serving_endpoints.get_open_ai_client()
        return self._client

    def invoke(self, prompt: str, *, system: str = '', node: str = '') -> LLMResult:
        messages = [{'role': 'system', 'content': system}] if system else []
        messages.append({'role': 'user', 'content': prompt})
        attempt = 0
        while True:
            try:
                resp = self._get_client().chat.completions.create(
                    model=self.model, messages=messages, max_tokens=self.max_tokens,
                    temperature=0)
                usage = resp.usage
                return LLMResult(
                    text=resp.choices[0].message.content or '',
                    tokens_in=getattr(usage, 'prompt_tokens', 0) or 0,
                    tokens_out=getattr(usage, 'completion_tokens', 0) or 0)
            except Exception as exc:
                if _is_quota(exc):
                    raise QuotaExceededError(str(exc)) from exc
                if not _is_transient(exc) or attempt >= self.max_retries:
                    raise
                self._sleep(2 ** attempt)
                attempt += 1
