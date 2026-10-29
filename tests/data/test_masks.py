import pytest

from insurance_automation.data.masks import mask_statements

CUR = 'insurance_automation.curated'
PRINCIPAL = '216983c9-db86-4ef8-b500-9349e6025f94'


def joined(**kw):
    return '\n'.join(mask_statements(CUR, **kw))


def test_masks_cover_notes_and_applicant_id():
    sql = joined(agent_principal='')
    assert f'{CUR}.mask_notes' in sql and f'{CUR}.mask_applicant_id' in sql
    assert 'ALTER COLUMN adjuster_notes SET MASK' in sql
    assert 'ALTER COLUMN applicant_id SET MASK' in sql


def test_agent_principal_is_allowed_by_name_when_given():
    sql = joined(agent_principal=PRINCIPAL)
    assert f"current_user() = '{PRINCIPAL}'" in sql


def test_no_principal_clause_when_blank():
    assert 'current_user()' not in joined(agent_principal='')


def test_humans_without_the_role_still_get_masked_values():
    sql = joined(agent_principal=PRINCIPAL)
    assert "'*** masked ***'" in sql and 'sha2(id, 256)' in sql


@pytest.mark.parametrize('bad', ["x' OR '1'='1", 'a b', "'; DROP TABLE t; --"])
def test_principal_must_look_like_a_uuid_or_email(bad):
    with pytest.raises(ValueError):
        mask_statements(CUR, agent_principal=bad)
