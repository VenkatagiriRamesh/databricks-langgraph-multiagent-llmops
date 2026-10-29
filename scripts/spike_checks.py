"""Task 1: probe what this Free Edition workspace supports. Failures are results, not errors.

Run: python -m scripts.spike_checks
Creates only `<catalog>.eval` objects prefixed `spike_`, and removes them at the end.
"""
import os
import sys
import traceback

from insurance_automation.common.config import load_config
from insurance_automation.common.sql import run_sql

PROFILE = os.environ.get('DATABRICKS_CONFIG_PROFILE', 'candiate-analysis')
os.environ.setdefault('DATABRICKS_CONFIG_PROFILE', PROFILE)


def check(fn):
    def wrapper(*args):
        try:
            return fn(*args)
        except Exception as exc:  # noqa: BLE001 - a failure is the result here
            return False, f'{type(exc).__name__}: {str(exc)[:300]}'

    wrapper.__name__ = fn.__name__
    return wrapper


@check
def setup_catalog(cfg):
    run_sql(f'CREATE CATALOG IF NOT EXISTS {cfg.catalog}', cfg.warehouse_id)
    run_sql(f'CREATE SCHEMA IF NOT EXISTS {cfg.schema("eval")}', cfg.warehouse_id)
    return True, f'{cfg.schema("eval")} ready'


@check
def llm_call(cfg):
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    client = w.serving_endpoints.get_open_ai_client()
    resp = client.chat.completions.create(
        model=cfg.fm_model, messages=[{'role': 'user', 'content': 'Reply with the word OK.'}],
        max_tokens=10,
    )
    usage = resp.usage
    return True, f'reply={resp.choices[0].message.content!r} tokens={usage.prompt_tokens}+{usage.completion_tokens}'


@check
def langgraph_memory_checkpointer(cfg):
    import langgraph
    from langgraph.checkpoint.memory import MemorySaver

    MemorySaver()
    return True, f'MemorySaver available (langgraph {getattr(langgraph, "__version__", "?")})'


@check
def langgraph_persistent_checkpointer(cfg):
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    try:
        instances = list(w.database.list_database_instances())
    except Exception as exc:  # noqa: BLE001
        return False, f'Lakebase API unavailable: {type(exc).__name__}: {str(exc)[:200]}'
    return bool(instances), f'{len(instances)} Lakebase instance(s)'


@check
def prompt_registry(cfg):
    import mlflow

    mlflow.set_tracking_uri('databricks')
    mlflow.set_registry_uri('databricks-uc')
    name = f'{cfg.schema("eval")}.spike_prompt'
    mlflow.genai.register_prompt(name=name, template='Hello {{who}}')
    loaded = mlflow.genai.load_prompt(f'prompts:/{name}/1')
    return True, f'registered and loaded: {loaded.template!r}'


@check
def uc_model_alias(cfg):
    import mlflow
    import numpy as np
    from mlflow import MlflowClient
    from sklearn.linear_model import LogisticRegression

    mlflow.set_tracking_uri('databricks')
    mlflow.set_registry_uri('databricks-uc')
    me = os.environ.get('USER_EMAIL', 'venkatagiriramesh11@gmail.com')
    mlflow.set_experiment(f'/Users/{me}/insurance_automation_spike')
    X = np.array([[0.0], [1.0], [2.0], [3.0]])
    model = LogisticRegression().fit(X, [0, 0, 1, 1])
    name = f'{cfg.schema("eval")}.spike_model'
    with mlflow.start_run():
        info = mlflow.sklearn.log_model(
            model, name='model', input_example=X[:2], registered_model_name=name
        )
    client = MlflowClient()
    version = client.search_model_versions(f"name='{name}'")[0].version
    client.set_registered_model_alias(name, 'champion', version)
    mlflow.sklearn.load_model(f'models:/{name}@champion')
    return True, f'registered {name} v{version}, alias champion loads ({info.model_uri})'


@check
def genai_evaluate(cfg):
    import mlflow
    from mlflow.genai.scorers import scorer

    mlflow.set_tracking_uri('databricks')
    me = os.environ.get('USER_EMAIL', 'venkatagiriramesh11@gmail.com')
    mlflow.set_experiment(f'/Users/{me}/insurance_automation_spike')

    @scorer
    def non_empty(outputs) -> bool:
        return bool(outputs)

    def predict(question):
        return f'echo: {question}'

    results = mlflow.genai.evaluate(
        data=[{'inputs': {'question': 'a'}}, {'inputs': {'question': 'b'}}],
        predict_fn=predict,
        scorers=[non_empty],
    )
    return True, f'custom scorer ran; metrics={results.metrics}'


@check
def genai_builtin_judge(cfg):
    import mlflow
    from mlflow.genai.scorers import Safety

    mlflow.set_tracking_uri('databricks')
    me = os.environ.get('USER_EMAIL', 'venkatagiriramesh11@gmail.com')
    mlflow.set_experiment(f'/Users/{me}/insurance_automation_spike')
    results = mlflow.genai.evaluate(
        data=[{'inputs': {'question': 'hello'}}],
        predict_fn=lambda question: 'Hello, how can I help with your claim?',
        scorers=[Safety()],
    )
    return True, f'built-in judge ran; metrics={results.metrics}'


@check
def responses_agent_and_deploy_api(cfg):
    from mlflow.pyfunc import ResponsesAgent  # noqa: F401
    from databricks import agents

    return True, f'ResponsesAgent importable; agents.deploy present={hasattr(agents, "deploy")}'


@check
def serving_endpoints(cfg):
    from databricks.sdk import WorkspaceClient

    w = WorkspaceClient()
    custom = [
        e.name for e in w.serving_endpoints.list()
        if not any(getattr(s, 'foundation_model', None) for s in (e.config.served_entities or []))
    ] if True else []
    return True, f'custom endpoints: {custom}'


@check
def cleanup(cfg):
    for stmt in (
        f'DROP FUNCTION IF EXISTS {cfg.schema("eval")}.spike_unused',
        f'DROP MODEL IF EXISTS {cfg.schema("eval")}.spike_model',
    ):
        try:
            run_sql(stmt, cfg.warehouse_id)
        except Exception:  # noqa: BLE001
            pass
    return True, 'spike objects cleanup attempted (prompt spike_prompt left; delete in UI if wanted)'


CHECKS = [
    setup_catalog, llm_call, langgraph_memory_checkpointer, langgraph_persistent_checkpointer,
    prompt_registry, uc_model_alias, genai_evaluate, genai_builtin_judge,
    responses_agent_and_deploy_api, serving_endpoints,
]


def main() -> int:
    cfg = load_config(require_warehouse=True)
    print(f'{"check":42} {"ok":5} detail')
    for fn in CHECKS:
        ok, detail = fn(cfg)
        print(f'{fn.__name__:42} {str(ok):5} {detail}')
    ok, detail = cleanup(cfg)
    print(f'{"cleanup":42} {str(ok):5} {detail}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(1)
