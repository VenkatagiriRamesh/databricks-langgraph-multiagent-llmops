import os
from dataclasses import dataclass

DEFAULT_CATALOG = 'insurance_automation'
DEFAULT_FM_MODEL = 'databricks-meta-llama-3-3-70b-instruct'


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    catalog: str
    fm_model: str
    warehouse_id: str = ''

    def schema(self, name: str) -> str:
        return f'{self.catalog}.{name}'


def load_config(require_warehouse: bool = False) -> Config:
    warehouse_id = os.environ.get('DATABRICKS_WAREHOUSE_ID', '')
    if require_warehouse and not warehouse_id:
        raise ConfigError('DATABRICKS_WAREHOUSE_ID is not set')
    return Config(
        catalog=os.environ.get('UC_CATALOG', DEFAULT_CATALOG),
        fm_model=os.environ.get('FM_API_MODEL', DEFAULT_FM_MODEL),
        warehouse_id=warehouse_id,
    )
