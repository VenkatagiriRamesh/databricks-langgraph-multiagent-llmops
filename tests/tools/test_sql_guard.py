import pytest

from insurance_automation.tools.sql_guard import UnsafeSQLError, validate_select_only

SCHEMA = 'insurance_automation.curated'


def test_guard_accepts_simple_select_and_adds_limit():
    sql = validate_select_only(f'SELECT claim_id FROM {SCHEMA}.claims', SCHEMA)
    assert sql.endswith('LIMIT 200')


def test_guard_keeps_existing_limit():
    sql = validate_select_only(f'SELECT * FROM {SCHEMA}.claims LIMIT 5;', SCHEMA)
    assert sql.endswith('LIMIT 5') and 'LIMIT 200' not in sql


@pytest.mark.parametrize('stmt', [
    f'DROP TABLE {SCHEMA}.claims',
    f'DELETE FROM {SCHEMA}.claims',
    f"INSERT INTO {SCHEMA}.claims VALUES (1)",
    f"UPDATE {SCHEMA}.claims SET status = 'approved'",
    f'ALTER TABLE {SCHEMA}.claims DROP COLUMN status',
])
def test_guard_rejects_write_and_ddl(stmt):
    with pytest.raises(UnsafeSQLError):
        validate_select_only(stmt, SCHEMA)


def test_guard_rejects_multiple_statements():
    with pytest.raises(UnsafeSQLError):
        validate_select_only(f'SELECT 1 FROM {SCHEMA}.claims; DROP TABLE {SCHEMA}.claims', SCHEMA)


def test_guard_rejects_other_schema():
    with pytest.raises(UnsafeSQLError):
        validate_select_only('SELECT * FROM other_catalog.other.t', SCHEMA)


def test_guard_rejects_join_to_other_schema():
    with pytest.raises(UnsafeSQLError):
        validate_select_only(
            f'SELECT * FROM {SCHEMA}.claims c JOIN system.information_schema.tables t ON 1=1', SCHEMA
        )


def test_guard_rejects_comment_smuggling():
    with pytest.raises(UnsafeSQLError):
        validate_select_only(f'SELECT * FROM {SCHEMA}.claims -- ; DROP TABLE x', SCHEMA)


def test_guard_rejects_table_function():
    with pytest.raises(UnsafeSQLError):
        validate_select_only("SELECT * FROM read_files('/Volumes/x')", SCHEMA)


def test_guard_allows_forbidden_word_inside_string_literal():
    sql = validate_select_only(
        f"SELECT * FROM {SCHEMA}.claims WHERE adjuster_notes LIKE '%delete%'", SCHEMA
    )
    assert 'LIKE' in sql


def test_guard_rejects_empty():
    with pytest.raises(UnsafeSQLError):
        validate_select_only('   ', SCHEMA)
