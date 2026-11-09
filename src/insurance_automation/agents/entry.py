"""Models-from-code entrypoint: MLflow imports this file when loading the logged agent."""
import mlflow

from insurance_automation.agents.approval_log import BestEffortApprovalLog, SqlApprovalLog
from insurance_automation.agents.serving import ClaimsResponsesAgent
from insurance_automation.common.config import load_config
from insurance_automation.common.sql import run_sql


def _build() -> ClaimsResponsesAgent:
    from insurance_automation import runtime  # written separately; imported lazily

    cfg = load_config()
    table = f'{cfg.schema("eval")}.approval_decisions'
    log = BestEffortApprovalLog(SqlApprovalLog(run_sql, table, cfg.warehouse_id))
    from insurance_automation.agents.prompts import RegistryPromptStore

    prompts = RegistryPromptStore(cfg.schema('eval'))  # reloads every 300 s: hot promotion
    import os

    from insurance_automation.agents.breaker import RuntimeBreaker, make_flag_reader
    from insurance_automation.agents.checkpoint import make_checkpointer

    reader = make_flag_reader(os.environ)
    return ClaimsResponsesAgent(
        lambda: runtime.build_live_context(cfg, prompts=prompts), log,
        checkpointer=make_checkpointer(os.environ),
        breaker=RuntimeBreaker(reader) if reader else None)


mlflow.models.set_model(_build())
