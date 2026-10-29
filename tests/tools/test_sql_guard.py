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


@pytest.mark.parametrize('stmt', [
    f'SELECT * FROM {SCHEMA}.claims, other.schema.t',
    f'SELECT * FROM {SCHEMA}.claims c, other.schema.t t WHERE c.a = t.a',
    f'SELECT * FROM {SCHEMA}.claims,other.schema.t',
    f'SELECT * FROM {SCHEMA}.claims a JOIN {SCHEMA}.policies b ON a.k = b.k, other.s.t',
    f'SELECT * FROM {SCHEMA}.claims LATERAL VIEW explode(arr) x AS y',
    f'SELECT * FROM {SCHEMA}.claims, LATERAL (SELECT 1)',
    "SELECT * FROM range(10)",
    f'SELECT * FROM {SCHEMA}.claims, explode(array(1,2))',
    f'SELECT * FROM {SCHEMA}.claims JOIN {SCHEMA}.policies(1) p ON 1=1',
    f'SELECT * FROM {SCHEMA}.claims WHERE x IN (SELECT y FROM other.s.t, {SCHEMA}.claims)',
])
def test_guard_rejects_from_clause_bypasses(stmt):
    with pytest.raises(UnsafeSQLError):
        validate_select_only(stmt, SCHEMA)


@pytest.mark.parametrize('expr', [
    "secret('scope', 'key')", "ai_query('m', 'p')", "ai_generate_text('p')", 'current_user()',
    'current_user', 'session_user()', "is_member('g')", "is_account_group_member('g')",
    "http_request('x')", "read_kafka()", "remote_query('x')", "java_method('a', 'b')",
    "reflect('a', 'b')", 'input_file_name()', "SECRET ('a','b')", '`secret`(1, 2)',
    "schema_of_json('{}')",
])
def test_guard_rejects_denied_functions(expr):
    with pytest.raises(UnsafeSQLError):
        validate_select_only(f'SELECT {expr} AS v FROM {SCHEMA}.claims', SCHEMA)


@pytest.mark.parametrize('ref', [
    'system.access.audit', 'information_schema.tables', f'{SCHEMA}.information_schema.tables',
])
def test_guard_rejects_system_and_information_schema_references(ref):
    with pytest.raises(UnsafeSQLError):
        validate_select_only(f'SELECT * FROM {SCHEMA}.claims WHERE 1 = (SELECT 1 FROM {ref})',
                             SCHEMA)


def test_guard_rejects_statements_over_4000_chars():
    long_sql = f'SELECT claim_id FROM {SCHEMA}.claims WHERE ' + ' OR '.join(['1=1'] * 1000)
    assert len(long_sql) > 4000
    with pytest.raises(UnsafeSQLError, match='too long'):
        validate_select_only(long_sql, SCHEMA)


def test_guard_still_allows_legit_multi_table_queries():
    sql = validate_select_only(
        f'SELECT c.claim_id, count(*) FROM {SCHEMA}.claims c, {SCHEMA}.policies p '
        f'WHERE c.policy_id = p.policy_id GROUP BY c.claim_id', SCHEMA)
    assert sql.endswith('LIMIT 200')
    sql = validate_select_only(
        f'SELECT * FROM (SELECT * FROM {SCHEMA}.claims) t JOIN {SCHEMA}.policies p ON t.k = p.k',
        SCHEMA)
    assert 'JOIN' in sql
