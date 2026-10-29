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


def test_best_effort_log_swallows_failures_and_keeps_them_for_inspection():
    from insurance_automation.agents.approval_log import ApprovalRecord, BestEffortApprovalLog

    class Broken:
        def append(self, record):
            raise PermissionError('no INSERT privilege')

    log = BestEffortApprovalLog(Broken())
    record = ApprovalRecord('r1', 'C1', 'adjuster', 'approve', '2026-10-29T00:00:00', 10.0, '')
    log.append(record)  # must not raise
    assert len(log.failures) == 1 and 'no INSERT privilege' in log.failures[0]


def test_best_effort_log_passes_records_through_when_healthy():
    from insurance_automation.agents.approval_log import (
        ApprovalRecord,
        BestEffortApprovalLog,
        InMemoryApprovalLog,
    )

    inner = InMemoryApprovalLog()
    log = BestEffortApprovalLog(inner)
    log.append(ApprovalRecord('r1', 'C1', 'adjuster', 'approve', '2026-10-29T00:00:00', 10.0, ''))
    assert len(inner.records) == 1 and log.failures == []
