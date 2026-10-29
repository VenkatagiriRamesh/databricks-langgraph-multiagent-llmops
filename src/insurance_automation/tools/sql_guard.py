"""Validate LLM-generated SQL before it reaches the warehouse."""
import re

LIMIT_DEFAULT = 200
_FORBIDDEN = {
    'insert', 'update', 'delete', 'drop', 'alter', 'create', 'grant', 'revoke', 'merge',
    'truncate', 'call', 'copy', 'use', 'set', 'into', 'overwrite', 'load', 'optimize',
    'vacuum', 'refresh', 'execute',
}


class UnsafeSQLError(ValueError):
    pass


def validate_select_only(sql: str, allowed_schema: str) -> str:
    text = sql.strip()
    if text.endswith(';'):
        text = text[:-1].rstrip()
    if not text:
        raise UnsafeSQLError('empty statement')
    scrubbed = re.sub(r"'(?:[^']|'')*'", "''", text)
    if '--' in scrubbed or '/*' in scrubbed:
        raise UnsafeSQLError('comments are not allowed')
    if ';' in scrubbed:
        raise UnsafeSQLError('multiple statements are not allowed')
    words = re.findall(r'[a-z_]+', scrubbed.lower())
    if not words or words[0] != 'select':
        raise UnsafeSQLError('only SELECT statements are allowed')
    bad = _FORBIDDEN.intersection(words)
    if bad:
        raise UnsafeSQLError(f'forbidden keyword: {min(bad)}')
    prefix = allowed_schema.lower() + '.'
    for ref in re.findall(r'\b(?:from|join)\s+([`\w.]+)', scrubbed, flags=re.IGNORECASE):
        if not ref.replace('`', '').lower().startswith(prefix):
            raise UnsafeSQLError(f'table outside {allowed_schema}: {ref}')
    if not re.search(r'\blimit\s+\d+\s*$', scrubbed, flags=re.IGNORECASE):
        text = f'{text} LIMIT {LIMIT_DEFAULT}'
    return text
