"""Column masks for PII: humans without the claims role see masked values.

The deployed agent runs as its own service principal, which must see real values or the
deterministic fraud and lookup logic would silently run on masked data. That principal is
named explicitly instead of widening access to everyone.
"""
import re

ADMIN_GROUP = 'admins'
CLAIMS_GROUP = 'claims_role'
_PRINCIPAL = re.compile(r'^[0-9a-fA-F-]{36}$|^[\w.+-]+@[\w.-]+$')


def mask_statements(
    curated_schema: str, agent_principal: str = '',
) -> list[str]:
    if agent_principal and not _PRINCIPAL.match(agent_principal):
        raise ValueError(f'not a service principal id or user email: {agent_principal!r}')
    allowed = f"is_member('{ADMIN_GROUP}') OR is_account_group_member('{CLAIMS_GROUP}')"
    if agent_principal:
        allowed += f" OR current_user() = '{agent_principal}'"
    return [
        (f'CREATE OR REPLACE FUNCTION {curated_schema}.mask_notes(notes STRING) RETURNS STRING '
        f"RETURN CASE WHEN {allowed} THEN notes ELSE '*** masked ***' END"),
        (f'CREATE OR REPLACE FUNCTION {curated_schema}.mask_applicant_id(id STRING) RETURNS STRING '
        f'RETURN CASE WHEN {allowed} THEN id ELSE sha2(id, 256) END'),
        (f'ALTER TABLE {curated_schema}.claims ALTER COLUMN adjuster_notes '
        f'SET MASK {curated_schema}.mask_notes'),
        (f'ALTER TABLE {curated_schema}.applicants ALTER COLUMN applicant_id '
        f'SET MASK {curated_schema}.mask_applicant_id'),
    ]
