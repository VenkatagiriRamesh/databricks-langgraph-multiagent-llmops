"""Validate LLM-generated SQL before it reaches the warehouse."""
import re

LIMIT_DEFAULT = 200
MAX_SQL_CHARS = 4000
_DENIED_CALLS = {
    'secret', 'ai_query', 'ai_generate_text', 'is_member', 'is_account_group_member',
    'http_request', 'read_files', 'read_kafka', 'remote_query', 'schema_of_json', 'java_method',
    'reflect', 'input_file_name', 'try_reflect', 'ai_forecast', 'read_state_store',
}
_DENIED_BARE = {'current_user', 'session_user', 'user'}
_FROM_END = {'where', 'group', 'order', 'having', 'limit', 'union', 'intersect', 'except',
             'window', 'qualify', 'lateral', 'cluster', 'distribute', 'sort', 'offset'}
_FORBIDDEN = {
    'insert', 'update', 'delete', 'drop', 'alter', 'create', 'grant', 'revoke', 'merge',
    'truncate', 'call', 'copy', 'use', 'set', 'into', 'overwrite', 'load', 'optimize',
    'vacuum', 'refresh', 'execute',
}


class UnsafeSQLError(ValueError):
    pass


def validate_select_only(sql: str, allowed_schema: str) -> str:
    text = sql.strip()
    if len(text) > MAX_SQL_CHARS:
        raise UnsafeSQLError(f'statement too long (over {MAX_SQL_CHARS} characters)')
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
    plain = scrubbed.replace('`', '').lower()
    if re.search(r'\blateral\b', plain):
        raise UnsafeSQLError('LATERAL is not allowed')
    if re.search(r'\b(?:system|information_schema)\b', plain):
        raise UnsafeSQLError('system and information_schema references are not allowed')
    for name in re.findall(r'\b([a-z_][a-z_0-9]*)\s*\(', plain):
        if name in _DENIED_CALLS:
            raise UnsafeSQLError(f'function not allowed: {name}')
    for name in _DENIED_BARE.intersection(re.findall(r'[a-z_]+', plain)):
        if name != 'user' or re.search(r'\buser\s*\(', plain):
            raise UnsafeSQLError(f'function not allowed: {name}')
    _check_tables(scrubbed, allowed_schema)
    if not re.search(r'\blimit\s+\d+\s*$', scrubbed, flags=re.IGNORECASE):
        text = f'{text} LIMIT {LIMIT_DEFAULT}'
    return text


def _from_items(text: str, start: int) -> list[str]:
    """Comma-separated items (at paren depth 0) of the FROM list that starts at `start`."""
    items, depth, begin, i = [], 0, start, start
    while i < len(text):
        ch = text[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                break
        elif depth == 0:
            if ch == ',':
                items.append(text[begin:i])
                begin = i + 1
            elif ch.isalpha() and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == '_')):
                word = re.match(r'[a-z_]+', text[i:], flags=re.IGNORECASE).group(0)
                if word.lower() in _FROM_END:
                    break
                i += len(word) - 1
        i += 1
    items.append(text[begin:i])
    return items


def _check_ref(item: str, allowed_schema: str) -> None:
    item = item.strip()
    if not item or item.startswith('('):  # sub-queries are checked through their own FROM
        return
    match = re.match(r'([`\w.]+)\s*(\()?', item)
    if not match:
        raise UnsafeSQLError(f'unrecognised table reference: {item[:40]}')
    ref = match.group(1)
    if match.group(2):
        raise UnsafeSQLError(f'table-valued functions are not allowed: {ref}')
    if not ref.replace('`', '').lower().startswith(allowed_schema.lower() + '.'):
        raise UnsafeSQLError(f'table outside {allowed_schema}: {ref}')


def _check_tables(scrubbed: str, allowed_schema: str) -> None:
    for m in re.finditer(r'\bfrom\b', scrubbed, flags=re.IGNORECASE):
        for item in _from_items(scrubbed, m.end()):
            _check_ref(item, allowed_schema)
    for m in re.finditer(r'\bjoin\b', scrubbed, flags=re.IGNORECASE):
        _check_ref(scrubbed[m.end():].lstrip().split(' on ')[0], allowed_schema)
