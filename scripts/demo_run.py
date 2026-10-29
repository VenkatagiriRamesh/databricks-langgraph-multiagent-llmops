"""Run questions through the live graph (real LLM, real tables, registered risk model).

Run: python -m scripts.demo_run "question one" "question two"
Needs a fresh token in the environment: see insurance_automation.runtime.refresh_token_env.
"""
import os
import sys

import mlflow

from insurance_automation.agents.graph import build_graph, invoke, resume
from insurance_automation.agents.prompts import RegistryPromptStore
from insurance_automation.common.config import load_config
from insurance_automation.runtime import build_live_context

DEFAULT_QUESTIONS = (
    'How late can a claim be reported before it needs a documented reason?',
    'How many claims do we have by claim type and what is the average amount?',
    'What is the underwriting risk for applicant A0042?',
    'Please decide claim C00009.',
)


def main(questions: list[str]) -> None:
    cfg = load_config(require_warehouse=True)
    mlflow.set_tracking_uri('databricks')
    user = os.environ.get('USER_EMAIL', 'venkatagiriramesh11@gmail.com')
    mlflow.set_experiment(f'/Users/{user}/insurance_automation_agent')
    prompts = RegistryPromptStore(cfg.schema('eval'))
    ctx = build_live_context(cfg, prompts=prompts)
    graph = build_graph(ctx)
    for i, question in enumerate(questions):
        result = invoke(graph, question, thread_id=f'demo-{i}')
        out = result.output
        print(f'\nQ: {question}\n  status={result.status} route={out.route} tools={out.tools_called}')
        print(f'  cost=${out.cost_usd:.5f} latency={out.latency_s:.1f}s citations={out.citations}')
        print(f'  A: {out.answer[:600]}')
        if result.status == 'pending_approval':
            print(f'  payload: {result.interrupt_payload}')
            final = resume(graph, f'demo-{i}', 'approve')
            print(f'  after approve: {final.output.approval_status}: {final.output.answer[:300]}')
    print(f'\nprompt sources: { {n: prompts.source(n) for n in ("supervisor", "writer")} }')
    print(f'risk model source: {ctx.tools.risk_source}; total cost ${ctx.ledger.total_usd():.5f}')


if __name__ == '__main__':
    main(sys.argv[1:] or list(DEFAULT_QUESTIONS))
