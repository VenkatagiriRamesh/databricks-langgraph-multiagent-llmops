"""Register the default prompts in the MLflow Prompt Registry (Unity Catalog) with alias production.

Run: python -m scripts.register_prompts
"""
import mlflow.genai

from insurance_automation.agents.prompts import DEFAULT_PROMPTS
from insurance_automation.common.config import load_config

ALIAS = 'production'


def _latest(store, name: str):
    try:
        return store.load_prompt(f'prompts:/{name}@{ALIAS}')
    except Exception:  # noqa: BLE001 - no alias / not registered yet
        try:
            return store.load_prompt(f'prompts:/{name}/latest')
        except Exception:  # noqa: BLE001
            return None


def register_all(schema: str, store=mlflow.genai) -> dict[str, int]:
    versions = {}
    for short, template in DEFAULT_PROMPTS.items():
        name = f'{schema}.{short}'
        current = _latest(store, name)
        if current is not None and current.template == template:
            version = current.version
        else:
            version = store.register_prompt(name=name, template=template).version
        store.set_prompt_alias(name, alias=ALIAS, version=version)
        versions[name] = version
    return versions


def main() -> None:
    cfg = load_config()
    mlflow.set_registry_uri('databricks-uc')
    for name, version in register_all(f'{cfg.catalog}.eval').items():
        print(f'{name} -> v{version} ({ALIAS})')


if __name__ == '__main__':
    main()
