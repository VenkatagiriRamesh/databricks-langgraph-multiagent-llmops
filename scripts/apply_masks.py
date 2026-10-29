"""(Re)apply the PII column masks without reloading data.

Run: AGENT_PRINCIPAL=<serving service principal id> python -m scripts.apply_masks
Without AGENT_PRINCIPAL only admins and the claims role see real values. Setting it grants that
one principal unmasked access, so do it deliberately. Find the id: the endpoint's `executed_by`
in system.query.history after one call.
"""
import os

from insurance_automation.common.config import load_config
from insurance_automation.common.sql import run_sql
from insurance_automation.data.masks import mask_statements


def main() -> None:
    cfg = load_config(require_warehouse=True)
    principal = os.environ.get('AGENT_PRINCIPAL', '')
    for statement in mask_statements(cfg.schema('curated'), principal):
        run_sql(statement, cfg.warehouse_id)
    print(f'masks applied; agent principal {"allowed: " + principal if principal else "not set"}')


if __name__ == '__main__':
    main()
