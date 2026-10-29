from insurance_automation.agents.approval_log import (
    ApprovalRecord,
    InMemoryApprovalLog,
    SqlApprovalLog,
    ensure_table_sql,
)

REC = ApprovalRecord('r1', 'C00001', 'adjuster', 'edit', '2026-10-29T10:00:00', 4000.0, "Pay O'Brien")


def test_in_memory_log_appends():
    log = InMemoryApprovalLog()
    log.append(REC)
    assert log.records == [REC]


def test_sql_log_escapes_single_quotes():
    calls = []
    SqlApprovalLog(lambda s, w: calls.append((s, w)) or [], 'c.ops.approvals', 'wh1').append(REC)
    stmt, wh = calls[0]
    assert wh == 'wh1' and stmt.startswith('INSERT INTO c.ops.approvals')
    assert "'Pay O''Brien'" in stmt and "'C00001'" in stmt and '4000.0' in stmt


def test_ensure_table_sql_is_idempotent_ddl():
    sql = ensure_table_sql('c.ops.approvals')
    assert 'CREATE TABLE IF NOT EXISTS c.ops.approvals' in sql and 'run_id' in sql
