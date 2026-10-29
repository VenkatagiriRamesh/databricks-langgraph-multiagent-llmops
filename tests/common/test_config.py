import pytest

from insurance_automation.common.config import Config, ConfigError, load_config


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv('UC_CATALOG', raising=False)
    monkeypatch.delenv('FM_API_MODEL', raising=False)
    cfg = load_config()
    assert cfg.catalog == 'insurance_automation'
    assert cfg.fm_model == 'databricks-meta-llama-3-3-70b-instruct'


def test_schema_helper_returns_three_level_name():
    cfg = Config(catalog='insurance_automation', fm_model='m', warehouse_id='w')
    assert cfg.schema('curated') == 'insurance_automation.curated'


def test_missing_warehouse_raises_config_error(monkeypatch):
    monkeypatch.delenv('DATABRICKS_WAREHOUSE_ID', raising=False)
    with pytest.raises(ConfigError):
        load_config(require_warehouse=True)
