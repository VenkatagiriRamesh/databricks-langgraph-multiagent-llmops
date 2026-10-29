from insurance_automation.common.config import Config
from scripts.deploy_agent_endpoint import agent_resources


def test_agent_resources_cover_llm_warehouse_and_curated_tables():
    cfg = Config(catalog='insurance_automation', fm_model='databricks-llm', warehouse_id='wh1')
    resources = agent_resources(cfg)
    described = [r.to_dict() for r in resources]
    flat = str(described)
    assert 'databricks-llm' in flat and 'wh1' in flat
    for table in ('applicants', 'policies', 'claims', 'policy_docs'):
        assert f'insurance_automation.curated.{table}' in flat
