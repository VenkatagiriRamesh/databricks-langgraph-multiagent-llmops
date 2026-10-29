"""Run the golden set against the live graph and log the report to MLflow.

Refresh the Databricks token first (e.g. `export DATABRICKS_TOKEN=<fresh token>`), because
a long run fails midway on an expired one. Progress is kept in a JSONL file, so a rerun
after a quota error resumes where it stopped.
"""
import argparse
import os
import sys

DEFAULT_GOLDEN = 'eval/golden_set.jsonl'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['dev', 'heldout'], default='dev')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--golden', default=DEFAULT_GOLDEN)
    parser.add_argument('--prompt', action='append', default=[], metavar='NAME=TEXT',
                        help='override a prompt for a challenger experiment')
    parser.add_argument('--report-out', default='eval/results/latest_report.json')
    args = parser.parse_args(argv)

    import hashlib
    import json
    import pathlib

    import mlflow

    from insurance_automation.agents.graph import build_graph, invoke, resume
    from insurance_automation.agents.prompts import (
        DEFAULT_PROMPTS,
        OverlayPromptStore,
        RegistryPromptStore,
    )
    from insurance_automation.common.config import load_config
    from insurance_automation.evaluation.golden import load_golden
    from insurance_automation.evaluation.harness import make_runner, run_eval
    from insurance_automation.evaluation.judges import judge_correctness, judge_groundedness
    from insurance_automation.runtime import build_live_context

    cfg = load_config(require_warehouse=True)
    mlflow.set_tracking_uri('databricks')
    user = os.environ.get('USER_EMAIL', 'venkatagiriramesh11@gmail.com')
    mlflow.set_experiment(f'/Users/{user}/insurance_automation_eval')
    prompts = RegistryPromptStore(cfg.schema('eval'))
    if args.prompt:
        prompts = OverlayPromptStore(prompts, dict(p.split('=', 1) for p in args.prompt))
    ctx = build_live_context(cfg, prompts=prompts)
    graph = build_graph(ctx)
    items = load_golden(args.golden, split=args.split)

    runner = make_runner(graph, invoke, resume)  # safety items are not auto-approved

    def judge(item, output):
        return {
            'groundedness': judge_groundedness(ctx.llm, item, output).score,
            'correctness': judge_correctness(ctx.llm, item, output).score,
        }

    # Results are cached per graph_hash, so it must change whenever behaviour can change.
    code = hashlib.sha256()
    for sub in ('agents', 'tools'):
        for path in sorted(pathlib.Path('src/insurance_automation', sub).glob('*.py')):
            code.update(path.read_bytes())
    fingerprint = json.dumps(
        {'model': cfg.fm_model, 'code': code.hexdigest(),
         'prompts': {n: prompts.get(n) for n in sorted(DEFAULT_PROMPTS)}},
        sort_keys=True)
    graph_hash = hashlib.sha256(fingerprint.encode()).hexdigest()[:10]
    os.makedirs(os.path.dirname(args.report_out) or '.', exist_ok=True)
    results = os.path.join(os.path.dirname(args.report_out) or '.', f'results_{args.split}.jsonl')
    report = run_eval(runner, items, n_runs=args.runs, judge=judge, results_path=results,
                      graph_hash=graph_hash)
    with open(args.report_out, 'w', encoding='utf-8') as handle:
        handle.write(report.to_json())
    with mlflow.start_run(run_name=f'eval-{args.split}'):
        mlflow.log_params({'split': args.split, 'runs': args.runs, 'graph_hash': graph_hash,
                           'n_items': report.n_items})
        for name, m in report.metrics.items():
            mlflow.log_metrics({f'{name}_mean': m.mean, f'{name}_low': m.low,
                                f'{name}_high': m.high})
        mlflow.log_metrics({'cost_usd_median': report.cost_usd_median,
                            'latency_p95_s': report.latency_p95_s, 'stp_rate': report.stp_rate,
                            'escalation_rate': report.escalation_rate})
        mlflow.log_artifact(args.report_out)
    print(report.to_json())
    return 0


if __name__ == '__main__':
    sys.exit(main())
