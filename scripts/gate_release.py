"""Release gate. Exit 1 on failure; on pass (and not --offline) set the UC alias `champion`.

Usage: python -m scripts.gate_release --report eval/results/latest_report.json --offline
"""
import argparse
import sys

from insurance_automation.evaluation.gate import Thresholds, gate_decision
from insurance_automation.evaluation.harness import EvalReport


def _load(path: str) -> EvalReport:
    with open(path, encoding='utf-8') as handle:
        return EvalReport.from_json(handle.read())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    parser.add_argument('--champion-report')
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--model-name')
    parser.add_argument('--model-version')
    args = parser.parse_args(argv)
    champion = _load(args.champion_report) if args.champion_report else None
    result = gate_decision(champion, _load(args.report), Thresholds())
    if not result.passed:
        print('GATE FAILED')
        for reason in result.reasons:
            print(f'- {reason}')
        return 1
    print('GATE PASSED')
    if not args.offline:
        if not (args.model_name and args.model_version):
            print('--model-name and --model-version are required to set the alias')
            return 1
        from mlflow import MlflowClient

        MlflowClient(registry_uri='databricks-uc').set_registered_model_alias(
            args.model_name, 'champion', args.model_version)
        print(f'alias champion -> {args.model_name} v{args.model_version}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
