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


def test_pip_requirements_cover_every_third_party_import_in_src():
    import ast
    import pathlib
    import sys

    from scripts.deploy_agent_endpoint import PIP_REQUIREMENTS

    pip_name = {'sklearn': 'scikit-learn', 'databricks': 'databricks-sdk', 'langchain_core': 'langchain-core'}
    imported = set()
    for path in pathlib.Path('src/insurance_automation').rglob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                imported |= {a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split('.')[0])
    third_party = imported - set(sys.stdlib_module_names) - {'insurance_automation'}
    required = ' '.join(PIP_REQUIREMENTS).lower()
    missing = sorted(m for m in third_party if pip_name.get(m, m).lower() not in required)
    assert not missing, f'deploy requirements are missing: {missing}'


def test_deploy_script_migrates_the_approval_table():
    import pathlib

    source = pathlib.Path('scripts/deploy_agent_endpoint.py').read_text()
    assert 'migrate_table_sql' in source


def test_replace_flag_is_supported_and_off_by_default():
    from scripts.deploy_agent_endpoint import parse_args

    assert parse_args([]).replace is False
    assert parse_args(['--deploy', '--replace']).replace is True
