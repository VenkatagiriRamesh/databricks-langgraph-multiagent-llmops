import mlflow.genai
import pytest

from insurance_automation.agents.prompts import (
    DEFAULT_PROMPTS,
    LocalPromptStore,
    RegistryPromptStore,
)
from scripts.register_prompts import register_all


class Loaded:
    template = 'REGISTRY TEXT'


def test_registry_returns_registry_text_and_caches(monkeypatch):
    uris = []
    monkeypatch.setattr(mlflow.genai, 'load_prompt', lambda uri: uris.append(uri) or Loaded())
    store = RegistryPromptStore('cat.eval')
    assert store.get('writer') == 'REGISTRY TEXT'
    assert store.get('writer') == 'REGISTRY TEXT'
    assert uris == ['prompts:/cat.eval.writer@production']
    assert store.source('writer') == 'registry'


def test_registry_falls_back_and_remembers_failure(monkeypatch):
    calls = []

    def boom(uri):
        calls.append(uri)
        raise RuntimeError('down')

    monkeypatch.setattr(mlflow.genai, 'load_prompt', boom)
    store = RegistryPromptStore('cat.eval')
    assert store.get('writer') == DEFAULT_PROMPTS['writer']
    assert store.get('writer') == DEFAULT_PROMPTS['writer']
    assert len(calls) == 1
    assert store.source('writer') == 'local'


def test_registry_unknown_name_still_raises_keyerror(monkeypatch):
    monkeypatch.setattr(mlflow.genai, 'load_prompt', lambda uri: (_ for _ in ()).throw(OSError()))
    with pytest.raises(KeyError):
        RegistryPromptStore('cat.eval', fallback=LocalPromptStore()).get('nope')


class FakeRegistry:
    def __init__(self, existing=None):
        self.versions = {k: [v] for k, v in (existing or {}).items()}
        self.aliases = {}

    def load_prompt(self, uri):
        name = uri.split(':/')[1].split('@')[0]
        if name not in self.versions:
            raise RuntimeError('missing')
        t = self.versions[name][-1]
        return type('P', (), {'template': t, 'version': len(self.versions[name])})()

    def register_prompt(self, name, template):
        self.versions.setdefault(name, []).append(template)
        return type('P', (), {'version': len(self.versions[name])})()

    def set_prompt_alias(self, name, alias, version):
        self.aliases[(name, alias)] = version


def test_register_all_registers_new_and_sets_alias():
    reg = FakeRegistry()
    register_all('cat.eval', reg)
    assert set(reg.versions) == {f'cat.eval.{n}' for n in DEFAULT_PROMPTS}
    assert all(reg.aliases[(f'cat.eval.{n}', 'production')] == 1 for n in DEFAULT_PROMPTS)


def test_register_all_skips_unchanged_and_versions_changed():
    reg = FakeRegistry({'cat.eval.writer': DEFAULT_PROMPTS['writer'], 'cat.eval.critic': 'old'})
    register_all('cat.eval', reg)
    assert len(reg.versions['cat.eval.writer']) == 1
    assert len(reg.versions['cat.eval.critic']) == 2
    assert reg.aliases[('cat.eval.writer', 'production')] == 1
    assert reg.aliases[('cat.eval.critic', 'production')] == 2


def test_overlay_prompt_store_overrides_named_prompts_only():
    from insurance_automation.agents.prompts import LocalPromptStore, OverlayPromptStore

    base = LocalPromptStore({'writer': 'base writer', 'critic': 'base critic'})
    store = OverlayPromptStore(base, {'writer': 'challenger writer'})
    assert store.get('writer') == 'challenger writer'
    assert store.get('critic') == 'base critic'


def test_overlay_prompt_store_rejects_unknown_override_names():
    import pytest

    from insurance_automation.agents.prompts import LocalPromptStore, OverlayPromptStore

    store = OverlayPromptStore(LocalPromptStore({'writer': 'w'}), {'nonsense': 'x'})
    with pytest.raises(KeyError):
        store.get('nonsense')
