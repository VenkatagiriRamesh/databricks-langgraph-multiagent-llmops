from types import SimpleNamespace
from unittest.mock import MagicMock

from insurance_automation.common.sql import run_sql


def test_run_sql_maps_rows_to_dicts(mocker):
    response = SimpleNamespace(
        status=SimpleNamespace(state='SUCCEEDED', error=None),
        manifest=SimpleNamespace(
            schema=SimpleNamespace(columns=[SimpleNamespace(name='a'), SimpleNamespace(name='b')])
        ),
        result=SimpleNamespace(data_array=[['1', 'x'], ['2', 'y']]),
    )
    client = MagicMock()
    client.statement_execution.execute_statement.return_value = response
    mocker.patch('insurance_automation.common.sql.WorkspaceClient', return_value=client)

    rows = run_sql('SELECT 1', 'wh')

    assert rows == [{'a': '1', 'b': 'x'}, {'a': '2', 'b': 'y'}]
