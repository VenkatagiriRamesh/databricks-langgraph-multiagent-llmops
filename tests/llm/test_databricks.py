from types import SimpleNamespace

import pytest

from insurance_automation.llm.base import QuotaExceededError
from insurance_automation.llm.databricks import DatabricksLLM


class HttpError(Exception):
    def __init__(self, status_code, msg='boom'):
        super().__init__(msg)
        self.status_code = status_code


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _response(text='hi', pt=7, ct=3):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(prompt_tokens=pt, completion_tokens=ct),
    )


def _llm(outcomes, **kw):
    client = FakeClient(outcomes)
    sleeps = []
    return DatabricksLLM('ep', client=client, sleep=sleeps.append, **kw), client, sleeps


def test_maps_usage_to_result():
    llm, client, _ = _llm([_response()])
    result = llm.invoke('q', system='sys')
    assert (result.text, result.tokens_in, result.tokens_out) == ('hi', 7, 3)
    call = client.calls[0]
    assert call['model'] == 'ep'
    assert call['temperature'] == 0
    assert call['messages'] == [
        {'role': 'system', 'content': 'sys'}, {'role': 'user', 'content': 'q'}]


def test_no_system_message_when_empty():
    llm, client, _ = _llm([_response()])
    llm.invoke('q')
    assert client.calls[0]['messages'] == [{'role': 'user', 'content': 'q'}]


def test_429_raises_quota_without_retry():
    llm, client, _ = _llm([HttpError(429), _response()])
    with pytest.raises(QuotaExceededError):
        llm.invoke('q')
    assert len(client.calls) == 1


def test_quota_text_raises_quota():
    llm, client, _ = _llm([HttpError(403, 'Workspace Quota exceeded')])
    with pytest.raises(QuotaExceededError):
        llm.invoke('q')
    assert len(client.calls) == 1


def test_500_retries_then_succeeds():
    llm, client, sleeps = _llm([HttpError(500), HttpError(503), _response()])
    assert llm.invoke('q').text == 'hi'
    assert len(client.calls) == 3
    assert sleeps == [1, 2]


def test_500_beyond_max_retries_raises():
    llm, client, _ = _llm([HttpError(500)] * 3, max_retries=2)
    with pytest.raises(HttpError):
        llm.invoke('q')
    assert len(client.calls) == 3


def test_non_transient_error_not_retried():
    llm, client, _ = _llm([HttpError(400, 'bad request')])
    with pytest.raises(HttpError):
        llm.invoke('q')
    assert len(client.calls) == 1
