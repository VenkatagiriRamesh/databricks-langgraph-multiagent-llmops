import pytest

from insurance_automation.llm.base import LLMResult, QuotaExceededError
from insurance_automation.llm.cached import CachedLLM
from tests.conftest import FakeLLM


def test_cache_hit_avoids_inner_call(tmp_path):
    inner = FakeLLM()
    llm = CachedLLM(inner, str(tmp_path), 'm')
    first = llm.invoke('hello', system='s')
    second = llm.invoke('hello', system='s', node='other')
    assert first == second
    assert len(inner.calls) == 1
    assert (llm.cache_hits, llm.cache_misses) == (1, 1)


def test_cache_persists_across_instances(tmp_path):
    inner = FakeLLM()
    CachedLLM(inner, str(tmp_path), 'm').invoke('hello')
    again = CachedLLM(inner, str(tmp_path), 'm')
    again.invoke('hello')
    assert len(inner.calls) == 1
    assert again.cache_hits == 1


def test_different_system_prompt_is_different_key(tmp_path):
    inner = FakeLLM()
    llm = CachedLLM(inner, str(tmp_path), 'm')
    llm.invoke('hello', system='a')
    llm.invoke('hello', system='b')
    assert len(inner.calls) == 2


def test_different_model_is_different_key(tmp_path):
    inner = FakeLLM()
    CachedLLM(inner, str(tmp_path), 'm1').invoke('hello')
    CachedLLM(inner, str(tmp_path), 'm2').invoke('hello')
    assert len(inner.calls) == 2


def test_quota_error_not_cached(tmp_path):
    class Flaky:
        calls = 0

        def invoke(self, prompt, *, system='', node=''):
            self.calls += 1
            if self.calls == 1:
                raise QuotaExceededError('quota')
            return LLMResult(text='ok', tokens_in=1, tokens_out=1)

    inner = Flaky()
    llm = CachedLLM(inner, str(tmp_path), 'm')
    with pytest.raises(QuotaExceededError):
        llm.invoke('hello')
    assert llm.invoke('hello').text == 'ok'
    assert inner.calls == 2


def test_corrupt_cache_file_is_a_miss(tmp_path):
    inner = FakeLLM()
    llm = CachedLLM(inner, str(tmp_path), 'm')
    llm.invoke('hello')
    for f in tmp_path.iterdir():
        f.write_text('{not json')
    result = llm.invoke('hello')
    assert result.text == 'OK'
    assert len(inner.calls) == 2
    assert llm.cache_misses == 2
