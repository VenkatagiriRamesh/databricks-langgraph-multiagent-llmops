from databricks.sdk import WorkspaceClient


class SQLExecutionError(RuntimeError):
    pass


def run_sql(statement: str, warehouse_id: str) -> list[dict]:
    client = WorkspaceClient()
    response = client.statement_execution.execute_statement(
        statement=statement, warehouse_id=warehouse_id, wait_timeout='50s'
    )
    state = str(response.status.state)
    if 'SUCCEEDED' not in state:
        detail = response.status.error.message if response.status.error else state
        raise SQLExecutionError(detail)
    columns = [c.name for c in response.manifest.schema.columns]
    data = response.result.data_array if response.result and response.result.data_array else []
    return [dict(zip(columns, row)) for row in data]
