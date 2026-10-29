"""Agreement between LLM judges and human labels."""
import csv
from collections import Counter

PASS_THRESHOLD = 0.75


def cohens_kappa(a: list[str], b: list[str]) -> float:
    if len(a) != len(b):
        raise ValueError('label lists must have the same length')
    if not a:
        raise ValueError('label lists must not be empty')
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in ca) / (n * n)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def load_labels(path: str) -> list[dict]:
    with open(path, newline='', encoding='utf-8') as handle:
        return [r for r in csv.DictReader(handle) if (r.get('human_label') or '').strip()]


def calibration_report(rows: list[dict]) -> dict[str, float]:
    by_judge: dict[str, tuple[list[str], list[str]]] = {}
    for row in rows:
        judge_labels, human_labels = by_judge.setdefault(row['judge'], ([], []))
        passed = float(row['judge_score']) >= PASS_THRESHOLD
        judge_labels.append('pass' if passed else 'fail')
        human_labels.append(row['human_label'].strip().lower())
    return {j: cohens_kappa(jl, hl) for j, (jl, hl) in by_judge.items()}
