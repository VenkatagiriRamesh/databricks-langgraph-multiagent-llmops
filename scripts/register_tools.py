"""Register read-only SQL table functions in `agent_tools`; Databricks Managed MCP exposes UC functions.

Run: python -m scripts.register_tools
"""
from insurance_automation.common.config import load_config
from insurance_automation.common.sql import run_sql


def function_statements(catalog: str) -> list[str]:
    cur, tools = f'{catalog}.curated', f'{catalog}.agent_tools'
    return [
        f"""CREATE OR REPLACE FUNCTION {tools}.get_claim(claim_id STRING)
RETURNS TABLE(claim_id STRING, policy_id STRING, applicant_id STRING, claim_type STRING,
              amount DOUBLE, loss_date DATE, reported_date DATE, status STRING)
COMMENT 'Look up one claim by id.'
RETURN SELECT c.claim_id, c.policy_id, c.applicant_id, c.claim_type, c.amount, c.loss_date,
              c.reported_date, c.status
       FROM {cur}.claims c WHERE c.claim_id = get_claim.claim_id""",
        f"""CREATE OR REPLACE FUNCTION {tools}.get_policy(policy_id STRING)
RETURNS TABLE(policy_id STRING, product STRING, inception_date DATE, deductible INT,
              coverage_limit INT, waiting_period_days INT, exclusions STRING)
COMMENT 'Look up one policy by id: deductible, limit, waiting period and excluded clauses.'
RETURN SELECT p.policy_id, p.product, p.inception_date, p.deductible, p.coverage_limit,
              p.waiting_period_days, p.exclusions
       FROM {cur}.policies p WHERE p.policy_id = get_policy.policy_id""",
        f"""CREATE OR REPLACE FUNCTION {tools}.claims_summary_by_type()
RETURNS TABLE(claim_type STRING, claims BIGINT, total_amount DOUBLE, avg_amount DOUBLE)
COMMENT 'Claim frequency and severity by claim type.'
RETURN SELECT claim_type, COUNT(*), ROUND(SUM(amount), 2), ROUND(AVG(amount), 2)
       FROM {cur}.claims GROUP BY claim_type ORDER BY claim_type""",
        f"""CREATE OR REPLACE FUNCTION {tools}.get_policy_clause(clause_id STRING)
RETURNS TABLE(doc_id STRING, title STRING, section STRING, body STRING)
COMMENT 'Return the text of one policy clause by id, for example RPT-01.'
RETURN SELECT d.doc_id, d.title, d.section, d.body
       FROM {cur}.policy_docs d WHERE d.doc_id = get_policy_clause.clause_id""",
    ]


def main() -> None:
    cfg = load_config(require_warehouse=True)
    for statement in function_statements(cfg.catalog):
        run_sql(statement, cfg.warehouse_id)
    print(run_sql(f"SELECT * FROM {cfg.catalog}.agent_tools.claims_summary_by_type()", cfg.warehouse_id))
    print(run_sql(f"SELECT * FROM {cfg.catalog}.agent_tools.get_policy_clause('RPT-01')", cfg.warehouse_id))
    print(run_sql(f"SELECT * FROM {cfg.catalog}.agent_tools.get_claim('C00001')", cfg.warehouse_id))


if __name__ == '__main__':
    main()
