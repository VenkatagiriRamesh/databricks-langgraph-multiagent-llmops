"""Sample about 30 judged outputs from a results JSONL into a CSV for human labelling."""
import argparse
import csv
import json
import random
import sys

FIELDS = ['id', 'question', 'answer', 'judge', 'judge_score', 'human_label']


def export(results: str, golden: str, out: str, n: int = 30, seed: int = 0) -> int:
    from insurance_automation.evaluation.golden import load_golden

    questions = {i.id: i.question for i in load_golden(golden)}
    rows = []
    with open(results, encoding='utf-8') as handle:
        for line in handle:
            rec = json.loads(line)
            for judge, score in rec.get('judge', {}).items():
                rows.append({'id': f"{rec['id']}#{rec['run']}",
                             'question': questions.get(rec['id'], ''),
                             'answer': rec['output']['answer'], 'judge': judge,
                             'judge_score': score, 'human_label': ''})
    sample = random.Random(seed).sample(rows, min(n, len(rows)))
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
