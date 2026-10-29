# ADR-004: LangGraph orchestration and custom evaluation harness

Status: accepted. Date: 2026-10-29.

Context: The workflow has branches (claim decisions run extra tools, others do not), a bounded retry loop between writer and critic, and a pause for human approval. The evaluation needs to score routes, tool paths, citations, SQL results, authority and fraud outcomes, and judged quality, with uncertainty and a release gate. Built-in MLflow judges returned empty metrics (ADR-001).

Decision:
- Use LangGraph: explicit nodes and conditional edges, a typed state, `interrupt()` for approval, a checkpointer for resume. Retries are capped at 2, then escalate.
- Wrap each node in an MLflow span with token counts.
- Write a custom evaluation harness: deterministic scorers for route, tool trajectory, citation validity, SQL execution match, safety phrases, authority and fraud referral; custom LLM-as-judge prompts for groundedness and correctness; resumable JSONL progress; mean with a 95% interval across items, averaged over applicable items only; one run per item (at temperature 0 the cache replays repeated runs, so they add nothing); dev and held-out splits (86 items: 50 dev, 36 held-out).
- Gate: absolute thresholds plus "challenger must not be worse than the champion beyond its interval".
- Provide judge calibration tooling (sample export, Cohen's kappa) so judge agreement with human labels can be reported.

Consequences:
- Control flow is inspectable and testable offline with a fake LLM; unit tests pass without a workspace.
- Trajectory is scored from the list of tools called, not from trace spans. This is simpler and weaker.
- The harness does not use `mlflow.genai.evaluate`; results are logged to MLflow as metrics and an artifact.
- Judge scores are only as good as their calibration; see [docs/EVALUATION.md] for the outcome.
- 36 held-out items give wide intervals, and some metrics apply to few items (SQL match: 4). Fraud and authority expectations were produced by the deterministic code under test, so those metrics check pass-through only.
- Not built: multi-turn evaluation, the full red-team set, online scoring.
