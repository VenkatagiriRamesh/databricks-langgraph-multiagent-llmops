import hashlib
import json
import os
import tempfile

from insurance_automation.llm.base import LLM, LLMResult


class CachedLLM:
    def __init__(self, inner: LLM, cache_dir: str, model_id: str):
        self.inner = inner
        self.cache_dir = cache_dir
        self.model_id = model_id
        self.cache_hits = 0
        self.cache_misses = 0
        os.makedirs(cache_dir, exist_ok=True)

    def _path(self, prompt: str, system: str) -> str:
        key = hashlib.sha256(f'{self.model_id}\0{system}\0{prompt}'.encode()).hexdigest()
        return os.path.join(self.cache_dir, f'{key}.json')

    def _load(self, path: str) -> LLMResult | None:
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            return LLMResult(text=data['text'], tokens_in=int(data['tokens_in']),
                             tokens_out=int(data['tokens_out']))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _store(self, path: str, result: LLMResult) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.cache_dir, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump({'text': result.text, 'tokens_in': result.tokens_in,
                           'tokens_out': result.tokens_out}, f)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def invoke(self, prompt: str, *, system: str = '', node: str = '') -> LLMResult:
        path = self._path(prompt, system)
        cached = self._load(path)
        if cached is not None:
            self.cache_hits += 1
            return cached
        self.cache_misses += 1
        result = self.inner.invoke(prompt, system=system, node=node)
        self._store(path, result)
        return result
