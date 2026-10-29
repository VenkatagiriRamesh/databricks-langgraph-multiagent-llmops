"""Log the claims agent (models-from-code), register it, alias it `challenger`, optionally deploy.

Run: python -m scripts.deploy_agent_endpoint [--deploy] [--force]
Registers <catalog>.models.claims_copilot_agent. The release gate promotes `champion`.
"""
import argparse
import os

ENTRY = 'src/insurance_automation/agents/entry.py'
PIP_REQUIREMENTS = [
    'mlflow==3.17.2', 'langgraph==1.2.18', 'databricks-sdk>=0.40.0', 'databricks-agents',
    'pydantic>=2',
]


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--deploy', action='store_true', help='create or update the serving endpoint')
    p.add_argument('--force', action='store_true', help='deploy even if custom endpoints exist')
    return p.parse_args(argv)


def agent_resources(cfg) -> list:
    """Resources the served agent may use; the endpoint is granted access to exactly these."""
    from mlflow.models.resources import (
        DatabricksServingEndpoint,
        DatabricksSQLWarehouse,
        DatabricksTable,
    )

    tables = ('applicants', 'policies', 'claims', 'policy_docs')
    return [
        DatabricksServingEndpoint(endpoint_name=cfg.fm_model),
        DatabricksSQLWarehouse(warehouse_id=cfg.warehouse_id),
        *[DatabricksTable(table_name=f'{cfg.schema("curated")}.{t}') for t in tables],
    ]


def main(argv=None) -> None:
    args = parse_args(argv)
    import mlflow
    from databricks import agents
    from databricks.sdk import WorkspaceClient

    from insurance_automation.common.config import load_config

    cfg = load_config(require_warehouse=True)
    model_name = f'{cfg.catalog}.models.claims_copilot_agent'
    mlflow.set_registry_uri('databricks-uc')
    from insurance_automation.agents.approval_log import ensure_table_sql
    from insurance_automation.common.sql import run_sql

    run_sql(ensure_table_sql(f'{cfg.schema("eval")}.approval_decisions'), cfg.warehouse_id)
    info = mlflow.pyfunc.log_model(
        name='agent', python_model=ENTRY, code_paths=['src/insurance_automation'],
        registered_model_name=model_name, pip_requirements=PIP_REQUIREMENTS,
        resources=agent_resources(cfg),
    )
    version = int(info.registered_model_version)
    mlflow.MlflowClient().set_registered_model_alias(model_name, 'challenger', version)
    print(f'Registered {model_name} version {version} with alias challenger')
    if not args.deploy:
        return
    custom = [
        e.name for e in WorkspaceClient().serving_endpoints.list()
        if e.name and not e.name.startswith('databricks-')
    ]
    print('Existing custom endpoints:', custom or 'none')
    if len(custom) > 1 and not args.force:
        raise SystemExit('More than 1 custom endpoint exists; delete stale ones or pass --force')
    deployment = agents.deploy(
        model_name, version, scale_to_zero=True,
        environment_vars={
            'DATABRICKS_WAREHOUSE_ID': cfg.warehouse_id, 'UC_CATALOG': cfg.catalog,
            'FM_API_MODEL': cfg.fm_model,
        },
    )
    print('Endpoint:', deployment.endpoint_name)


if __name__ == '__main__':
    os.environ.setdefault('MLFLOW_DISABLE_AGENT_HINT', '1')
    main()
