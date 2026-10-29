import os

import pytest

from scripts.job_entry import main


def test_job_entry_exports_params_then_runs_script(monkeypatch):
    for key in ('DATABRICKS_WAREHOUSE_ID', 'UC_CATALOG', 'FM_API_MODEL'):
        monkeypatch.delenv(key, raising=False)
    seen = {}

    def runner(module, argv):
        seen.update(module=module, argv=argv, warehouse=os.environ['DATABRICKS_WAREHOUSE_ID'],
                    catalog=os.environ['UC_CATALOG'], model=os.environ['FM_API_MODEL'])

    main(['--warehouse-id', 'wh1', '--catalog', 'cat', '--fm-model', 'm1',
          '--script', 'run_eval', '--', '--split', 'dev'], runner=runner)

    assert seen == {'module': 'scripts.run_eval', 'argv': ['--split', 'dev'],
                    'warehouse': 'wh1', 'catalog': 'cat', 'model': 'm1'}


def test_job_entry_rejects_script_names_that_are_not_plain_identifiers():
    with pytest.raises(SystemExit):
        main(['--warehouse-id', 'w', '--script', '../evil'], runner=lambda m, a: None)
