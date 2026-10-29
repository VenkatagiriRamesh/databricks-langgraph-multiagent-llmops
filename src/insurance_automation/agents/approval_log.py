from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ApprovalRecord:
    run_id: str
    claim_id: str | None
    required_authority: str | None
    decision: str
    decided_at: str
    payable_amount: float
    edit_text: str = ''


class ApprovalLog(Protocol):
    def append(self, record: ApprovalRecord) -> None: ...


class InMemoryApprovalLog:
    def __init__(self) -> None:
        self.records: list[ApprovalRecord] = []

    def append(self, record: ApprovalRecord) -> None:
        self.records.append(record)


def _lit(value: object) -> str:
    if value is None:
        return 'NULL'
    return "'" + str(value).replace('\\', '\\\\').replace("'", "''") + "'"


def ensure_table_sql(table: str) -> str:
    return (
        f'CREATE TABLE IF NOT EXISTS {table} (run_id STRING, claim_id STRING, '
        'required_authority STRING, decision STRING, decided_at TIMESTAMP, '
        'payable_amount DOUBLE, edit_text STRING)'
    )


class SqlApprovalLog:
    def __init__(self, run_sql: Callable[[str, str], list], table: str, warehouse_id: str):
        self.run_sql, self.table, self.warehouse_id = run_sql, table, warehouse_id

    def append(self, record: ApprovalRecord) -> None:
        stmt = (
            f'INSERT INTO {self.table} VALUES ({_lit(record.run_id)}, {_lit(record.claim_id)}, '
            f'{_lit(record.required_authority)}, {_lit(record.decision)}, '
            f'CAST({_lit(record.decided_at)} AS TIMESTAMP), {float(record.payable_amount)}, '
            f'{_lit(record.edit_text)})'
        )
        self.run_sql(stmt, self.warehouse_id)
