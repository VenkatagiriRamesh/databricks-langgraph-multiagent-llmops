# ADR-004: LangGraph orchestration and custom evaluation harness

Status: accepted. Date: 2026-10-29.

Context: The workflow has branches (claim decisions run extra tools, others do not), a bounded retry loop between writer and critic, and a pause for human approval. The evaluation needs to score routes, tool paths, citations, SQL results, authority and fraud outcomes, and judged quality, with uncertainty and a release gate. Built-in MLflow judges returned empty metrics (ADR-001).

Decision:
- Use LangGraph: explicit nodes and conditional edges, a typed state, `interrupt()` for approval, a checkpointer for resume. Retries are capped at 2, then escalate.
- Wrap each node in an MLflow span with token counts.
- Write a custom evaluation harness: deterministic scorers for route, tool trajectory, citation validity, SQL execution match, safety phrases, authority and fraud referral; custom LLM-as-judge prompts for groundedness and correctness; resumable JSONL progress; mean with confidence interval over repeated runs; dev and held-out splits (48 items, 29 dev and 19 held-out at the time of writing).
- Gate: absolute thresholds plus "challenger must not be worse than the champion beyond its interval".
- Provide judge calibration tooling (sample export, Cohen's kappa) so judge agreement with human labels can be reported.

Consequences:
- Control flow is inspectable and testable offline with a fake LLM; about 220 unit tests pass without a workspace.
- Trajectory is scored from the list of tools called, not from trace spans. This is simpler and weaker.
- The harness does not use `mlflow.genai.evaluate`; results are logged to MLflow as metrics and an artifact.
- Judge scores are only as good as their calibration; see [docs/EVALUATION.md] for the outcome.
- The 48-item set gives wide intervals on per-route metrics.
- Not built: multi-turn evaluation, the full red-team set, online scoring.
