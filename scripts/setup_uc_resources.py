"""Create the catalog, schemas and landing Volume. Idempotent.

Run: python -m scripts.setup_uc_resources
"""
from insurance_automation.common.config import load_config
from insurance_automation.common.sql import run_sql

SCHEMAS = ('raw', 'curated', 'agent_tools', 'models', 'eval')


def main() -> None:
    cfg = load_config(require_warehouse=True)
    run_sql(f'CREATE CATALOG IF NOT EXISTS {cfg.catalog}', cfg.warehouse_id)
    for name in SCHEMAS:
        run_sql(f'CREATE SCHEMA IF NOT EXISTS {cfg.schema(name)}', cfg.warehouse_id)
    run_sql(f'CREATE VOLUME IF NOT EXISTS {cfg.schema("raw")}.landing', cfg.warehouse_id)
    print(f'ready: {cfg.catalog} with schemas {", ".join(SCHEMAS)} and volume raw.landing')


if __name__ == '__main__':
    main()
