"""Load applicants (reused from the RAG project), generate policies, claims and policy docs,
land them in the Volume, build Delta tables, and attach PII masks. Idempotent.

Run: python -m scripts.bootstrap_data
Generated data is created on Databricks and never committed; only this code is.
"""
import io
import json

from databricks.sdk import WorkspaceClient

from insurance_automation.common.config import load_config
from insurance_automation.common.sql import run_sql
from insurance_automation.data.generate import (
    generate_claims,
    generate_policies,
    generate_policy_docs,
    with_applicant_ids,
)

SOURCE_TABLE = 'insurance_rag_agent.raw.policies_raw'
SEED = 42
CLAIM_COUNT = 1000
ADMIN_GROUP = 'admins'
CLAIMS_GROUP = 'claims_role'


def _land(client: WorkspaceClient, volume: str, name: str, rows: list[dict]) -> str:
    path = f'/Volumes/{volume.replace(".", "/")}/{name}.jsonl'
    payload = '\n'.join(json.dumps(row) for row in rows).encode()
    client.files.upload(path, io.BytesIO(payload), overwrite=True)
    return path


def _ctas(table: str, path: str, select: str) -> str:
    return (
        f"CREATE OR REPLACE TABLE {table} AS SELECT {select} "
        f"FROM read_files('{path}', format => 'json')"
    )


def main() -> None:
    cfg = load_config(require_warehouse=True)
    wh = cfg.warehouse_id
    raw, cur = cfg.schema('raw'), cfg.schema('curated')
    client = WorkspaceClient()

    run_sql(
        f'CREATE OR REPLACE TABLE {raw}.applicants_raw AS '
        f'SELECT age, sex, bmi, children, smoker, region, charges, '
        f"current_timestamp() AS ingestion_timestamp, '{SOURCE_TABLE}' AS source_file "
        f'FROM {SOURCE_TABLE}',
        wh,
    )
    rows = run_sql(
        f'SELECT age, sex, bmi, children, smoker, region, charges FROM {raw}.applicants_raw '
        'ORDER BY age, sex, bmi, children, smoker, region, charges',
        wh,
    )
    applicants = with_applicant_ids([
        {'age': int(r['age']), 'sex': r['sex'], 'bmi': float(r['bmi']),
         'children': int(r['children']), 'smoker': r['smoker'], 'region': r['region'],
         'charges': float(r['charges'])}
        for r in rows
    ])
    policies = generate_policies(applicants, seed=SEED)
    claims = generate_claims(policies, n=CLAIM_COUNT, seed=SEED)
    docs = generate_policy_docs()

    volume = f'{raw}.landing'
    paths = {name: _land(client, volume, name, data) for name, data in (
        ('applicants', applicants), ('policies', policies), ('claims', claims), ('policy_docs', docs),
    )}

    run_sql(_ctas(f'{raw}.claims_raw', paths['claims'], '*'), wh)
    run_sql(_ctas(
        f'{cur}.applicants', paths['applicants'],
        'applicant_id, CAST(age AS INT) age, sex, CAST(bmi AS DOUBLE) bmi, '
        'CAST(children AS INT) children, smoker, region, CAST(charges AS DOUBLE) charges',
    ), wh)
    run_sql(_ctas(
        f'{cur}.policies', paths['policies'],
        'policy_id, applicant_id, product, CAST(inception_date AS DATE) inception_date, '
        'CAST(deductible AS INT) deductible, CAST(coverage_limit AS INT) coverage_limit, '
        'CAST(waiting_period_days AS INT) waiting_period_days, exclusions',
    ), wh)
    run_sql(_ctas(
        f'{cur}.claims', paths['claims'],
        'claim_id, policy_id, applicant_id, claim_type, CAST(amount AS DOUBLE) amount, '
        'CAST(loss_date AS DATE) loss_date, CAST(reported_date AS DATE) reported_date, '
        'CAST(filed_date AS DATE) filed_date, status, adjuster_notes, '
        'CAST(seeded_fraud AS BOOLEAN) seeded_fraud, CAST(has_injection AS BOOLEAN) has_injection',
    ), wh)
    run_sql(_ctas(f'{cur}.policy_docs', paths['policy_docs'], 'doc_id, title, section, body'), wh)

    run_sql(
        f'CREATE OR REPLACE FUNCTION {cur}.mask_notes(notes STRING) RETURNS STRING '
        f"RETURN CASE WHEN is_member('{ADMIN_GROUP}') OR is_account_group_member('{CLAIMS_GROUP}') "
        f"THEN notes ELSE '*** masked ***' END",
        wh,
    )
    run_sql(
        f'CREATE OR REPLACE FUNCTION {cur}.mask_applicant_id(id STRING) RETURNS STRING '
        f"RETURN CASE WHEN is_member('{ADMIN_GROUP}') OR is_account_group_member('{CLAIMS_GROUP}') "
        f'THEN id ELSE sha2(id, 256) END',
        wh,
    )
    run_sql(f'ALTER TABLE {cur}.claims ALTER COLUMN adjuster_notes SET MASK {cur}.mask_notes', wh)
    run_sql(f'ALTER TABLE {cur}.applicants ALTER COLUMN applicant_id SET MASK {cur}.mask_applicant_id', wh)

    for table in ('applicants', 'policies', 'claims', 'policy_docs'):
        count = run_sql(f'SELECT COUNT(*) c FROM {cur}.{table}', wh)[0]['c']
        print(f'{cur}.{table}: {count} rows')
    masks = run_sql(
        f"SELECT table_name, column_name, mask_name FROM {cfg.catalog}.information_schema.column_masks "
        f"WHERE table_schema = 'curated'",
        wh,
    )
    print('masks:', masks)


if __name__ == '__main__':
    main()
