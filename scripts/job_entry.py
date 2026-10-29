"""Entry point for Databricks job tasks: exports job parameters as the environment the scripts read.

Used by resources/jobs.yml, e.g. --warehouse-id {{job.parameters.warehouse_id}} --script run_eval
"""
import argparse
import os
import re
import runpy
import sys


def _run_module(module: str, argv: list[str]) -> None:
    sys.argv = [module, *argv]
    runpy.run_module(module, run_name='__main__')


def main(argv: list[str] | None = None, runner=_run_module) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--warehouse-id', required=True)
    parser.add_argument('--catalog', default='insurance_automation')
    parser.add_argument('--fm-model', default='databricks-meta-llama-3-3-70b-instruct')
    parser.add_argument('--script', required=True)
    args, rest = parser.parse_known_args(argv)
    if not re.fullmatch(r'[a-z_]+', args.script):
        parser.error(f'invalid script name: {args.script}')
    os.environ['DATABRICKS_WAREHOUSE_ID'] = args.warehouse_id
    os.environ['UC_CATALOG'] = args.catalog
    os.environ['FM_API_MODEL'] = args.fm_model
    runner(f'scripts.{args.script}', [a for a in rest if a != '--'])


if __name__ == '__main__':
    main()
