"""Models-from-code entrypoint: MLflow imports this file when loading the logged agent."""
import mlflow

from insurance_automation.agents.approval_log import SqlApprovalLog, ensure_table_sql
from insurance_automation.agents.serving import ClaimsResponsesAgent
from insurance_automation.common.config import load_config
from insurance_automation.common.sql import run_sql


def _build() -> ClaimsResponsesAgent:
    from insurance_automation import runtime  # written separately; imported lazily

    cfg = load_config()
    table = f'{cfg.schema("eval")}.approval_decisions'
    log = SqlApprovalLog(run_sql, table, cfg.warehouse_id)
    run_sql(ensure_table_sql(table), cfg.warehouse_id)
    return ClaimsResponsesAgent(lambda: runtime.build_live_context(cfg), log)


mlflow.models.set_model(_build())
