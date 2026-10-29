"""Sample about 30 judged outputs from a results JSONL into a CSV for human labelling."""
import argparse
import csv
import json
import random
import sys

FIELDS = ['id', 'judge', 'question', 'reference_answer', 'evidence', 'answer', 'judge_score',
          'human_label']
EVIDENCE_CHARS = 1200


def export(results: str, golden: str, out: str, n: int = 30, seed: int = 0) -> int:
    from insurance_automation.evaluation.golden import load_golden

    items = {i.id: i for i in load_golden(golden)}
    rows = []
    with open(results, encoding='utf-8') as handle:
        for line in handle:
            rec = json.loads(line)
            for judge, score in rec.get('judge', {}).items():
                item = items.get(rec['id'])
                rows.append({'id': f"{rec['id']}#{rec['run']}",
                             'question': item.question if item else '',
                             'reference_answer': item.reference_answer if item else '',
                             'evidence': rec['output'].get('evidence', '')[:EVIDENCE_CHARS],
                             'answer': rec['output']['answer'], 'judge': judge,
                             'judge_score': score, 'human_label': ''})
    rng = random.Random(seed)
    sample = []
    for judge in sorted({r['judge'] for r in rows}):  # balance the sample across judges
        pool = [r for r in rows if r['judge'] == judge]
        sample += rng.sample(pool, min(n // 2, len(pool)))
    with open(out, 'w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sample)
    return len(sample)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', default='eval/results/results_dev.jsonl')
    parser.add_argument('--golden', default='eval/golden_set.jsonl')
    parser.add_argument('--out', default='eval/calibration_labels.csv')
    parser.add_argument('--n', type=int, default=30)
    args = parser.parse_args(argv)
    print(f'wrote {export(args.results, args.golden, args.out, args.n)} rows to {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
