import csv

import pytest

from insurance_automation.evaluation.calibration import (
    calibration_report,
    cohens_kappa,
    load_labels,
)


def test_kappa_perfect():
    assert cohens_kappa(['pass', 'fail'], ['pass', 'fail']) == 1.0
    assert cohens_kappa(['pass', 'pass'], ['pass', 'pass']) == 1.0


def test_kappa_hand_computed():
    a = ['pass'] * 4 + ['fail'] * 4 + ['pass'] * 1 + ['fail'] * 1
    b = ['pass'] * 4 + ['fail'] * 4 + ['fail'] * 1 + ['pass'] * 1
    # po=0.8, pe=0.5 -> 0.6
    assert cohens_kappa(a, b) == pytest.approx(0.6)


def test_kappa_errors():
    with pytest.raises(ValueError):
        cohens_kappa(['a'], ['a', 'b'])
    with pytest.raises(ValueError):
        cohens_kappa([], [])


def test_unlabelled_rows_ignored(tmp_path):
    path = tmp_path / 'c.csv'
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['id', 'judge', 'judge_score', 'human_label'])
        w.writeheader()
        w.writerow({'id': '1', 'judge': 'groundedness', 'judge_score': '1.0', 'human_label': 'pass'})
        w.writerow({'id': '2', 'judge': 'groundedness', 'judge_score': '0.25', 'human_label': ' '})
        w.writerow({'id': '3', 'judge': 'groundedness', 'judge_score': '0.5', 'human_label': 'fail'})
    rows = load_labels(str(path))
    assert [r['id'] for r in rows] == ['1', '3']
    assert calibration_report(rows) == {'groundedness': 1.0}
