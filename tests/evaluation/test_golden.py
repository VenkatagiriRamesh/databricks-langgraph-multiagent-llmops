import json
from pathlib import Path

import pytest

from insurance_automation.contracts import ROUTES
from insurance_automation.evaluation.golden import load_golden, save_golden

REAL_PATH = Path(__file__).resolve().parents[2] / 'eval' / 'golden_set.jsonl'


def _row(i: str, **kw) -> dict:
    base = {
        'id': i, 'question': 'q?', 'expected_route': 'policy', 'expected_tools': ['retrieve_policy'],
        'reference_answer': 'a', 'reference_sql': None, 'reference_rows': None, 'must_cite': True,
        'expected_citations': ['COV-01'], 'safety_case': False, 'forbidden_phrases': [],
        'expected_authority': None, 'expected_fraud_referral': None, 'claim_id': None,
        'split': 'dev',
    }
    return {**base, **kw}


def _write(path, rows):
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n')


def test_golden_loads_and_splits_without_overlap(tmp_path):
    p = tmp_path / 'g.jsonl'
    _write(p, [_row('a'), _row('b', split='heldout'), _row('c')])
    assert len(load_golden(str(p))) == 3
    dev, held = load_golden(str(p), 'dev'), load_golden(str(p), 'heldout')
    assert {i.id for i in dev} == {'a', 'c'} and {i.id for i in held} == {'b'}
    assert not {i.id for i in dev} & {i.id for i in held}


def test_duplicate_id_raises(tmp_path):
    p = tmp_path / 'g.jsonl'
    _write(p, [_row('a'), _row('a')])
    with pytest.raises(ValueError, match='duplicate'):
        load_golden(str(p))


def test_unknown_route_raises(tmp_path):
    p = tmp_path / 'g.jsonl'
    _write(p, [_row('a', expected_route='weather')])
    with pytest.raises(ValueError, match='route'):
        load_golden(str(p))


def test_unknown_tool_raises(tmp_path):
    p = tmp_path / 'g.jsonl'
    _write(p, [_row('a', expected_tools=['hack'])])
    with pytest.raises(ValueError, match='tool'):
        load_golden(str(p))


def test_missing_field_and_bad_split_raise(tmp_path):
    p = tmp_path / 'g.jsonl'
    row = _row('a')
    del row['question']
    _write(p, [row])
    with pytest.raises(ValueError, match='missing'):
        load_golden(str(p))
    _write(p, [_row('a', split='test')])
    with pytest.raises(ValueError, match='split'):
        load_golden(str(p))


def test_save_roundtrip(tmp_path):
    p = tmp_path / 'g.jsonl'
    _write(p, [_row('a'), _row('b', split='heldout')])
    items = load_golden(str(p))
    out = tmp_path / 'o.jsonl'
    save_golden(items, str(out))
    assert load_golden(str(out)) == items


def test_real_golden_set():
    items = load_golden(str(REAL_PATH))
    assert len(items) >= 50
    assert len({i.id for i in items}) == len(items)
    for split in ('dev', 'heldout'):
        assert {i.expected_route for i in items if i.split == split} == set(ROUTES)
    for i in items:
        if i.expected_route == 'claim_decision':
            assert i.claim_id and i.expected_authority
        if i.expected_route == 'policy':
            assert i.expected_citations
    for split in ('dev', 'heldout'):
        positives = [i for i in items if i.split == split and i.expected_fraud_referral is True]
        assert len(positives) >= 3
        negatives = [i for i in items if i.split == split and i.expected_fraud_referral is False]
        assert len(negatives) >= 3
