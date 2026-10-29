# CV material

Every figure comes from `docs/EVALUATION.md` and the committed reports in `eval/results/`. Held-out numbers (36 items, 1 run, with the number of applicable items) are used throughout. Re-check before sending.

## (a) Resume bullets

1. Built a LangGraph multi-agent claims copilot on Databricks with deterministic coverage, fraud and authority tools; route accuracy 0.972 on 36 held-out items, safety 1.000 on 6 injection cases.
2. Built MLflow tracing, a prompt registry and a custom evaluation harness; groundedness 0.903 and correctness 0.889 (LLM judge, uncalibrated) on 36 held-out items, one run each.
3. Designed an evaluation-gated release: the gate blocked a regression (correctness 0.951 to 0.674 on the dev split) and passed a within-noise change; deployed a scale-to-zero endpoint.

Optional fourth: "Trained and registered a risk model in Unity Catalog (AUC 0.888, sex excluded); disparate impact ratios 0.937 (sex), 0.865 (region)."

Each bullet is under 30 words. Do not add "3 runs", "93 runs" or the old 31-item figures: runs were deterministic cache replays.

## (b) Title and tech line

Project title: Multi-agent claims and underwriting automation on Databricks (LangGraph, MLflow, Unity Catalog)

Tech line: Databricks Free Edition, LangGraph, MLflow (tracing, prompt registry, evaluation), Unity Catalog (column masks, functions, model registry), Model Serving, Foundation Model APIs, scikit-learn, Python, SQL, pytest, GitHub Actions

## (c) Skills-row addition

Agentic AI & LLMOps: LangGraph, multi-agent orchestration, MLflow tracing and GenAI evaluation, prompt registry, guardrails, human-in-the-loop, Unity Catalog governance

| Keyword | Where it is real in the repo | Safe to claim now? |
|---|---|---|
| LangGraph | `src/insurance_automation/agents/graph.py`: supervisor, five specialist paths, writer, critic, interrupt-based approval gate | Yes |
| Multi-agent orchestration | Supervisor routing to specialist nodes with retry and escalation edges; deployed endpoint | Yes (one graph with specialist nodes, not independent agents talking to each other) |
| MLflow tracing | Per-node spans with token counts (`agents/tracing.py`); traces seen in the demo run | Yes |
| GenAI evaluation | Custom harness, 86-item golden set (50 dev, 36 held-out), CIs, release gate; not `mlflow.genai.evaluate` | Yes (say custom harness; judges uncalibrated) |
| Prompt registry | Four prompts in `insurance_automation.eval`, alias `production`, with in-code fallback | Yes |
| Guardrails | SQL guard, critic checks, injection handling, authority matrix | Yes (6 injection cases per split, not a red-team suite) |
| Human-in-the-loop | Approval gate, approve/reject/edit, replay refusal, decision log | Yes (role not authenticated on Free Edition; approval state is per process) |
| Unity Catalog governance | Column masks, UC functions, model registry with alias, prompt registry in UC | Yes (one workspace, synthetic data) |
| Managed MCP / MCP consumption | UC functions exist and are exposable; the graph does not call MCP | NOT safe |
| Hybrid search / reranking | Retrieval is TF-IDF only (ADR-002) | NOT safe |
| Red-teaming | 12 injection and probe items only | NOT safe |
| Online evaluation / monitoring | Offline golden-set evaluation only | NOT safe |
| Calibrated LLM judges / kappa | Sheet unlabelled, kappa not measured | NOT safe |
| Fine-tuning, GPU | Not done | NOT safe |

## (d) Interview questions this project supports

1. **How do you know the evaluation is trustworthy?** Only partly. Dev and held-out are separate splits and the first dev run exposed bugs in my own scorers. An independent review then found my "3 runs each" claim was false: runs were cache replays, so the sample is 36 items, one run. The held-out split is also no longer pristine, because I read its failures. Judge scores are uncalibrated (30-row sheet unlabelled, no kappa).
2. **Your fraud and authority match is 1.000. Is that real?** It is circular. The expected values came from the same deterministic code the agent uses, so the metric shows the graph passes the tools' verdicts through, over 7 held-out fraud-positive items. It does not show detection of real fraud. Authority is separately checked against a hand-computed 18-row table.
3. **36 held-out items is small. What can you conclude?** Intervals are wide (route accuracy 0.972, interval 0.918 to 1.000). I can say the system is not badly broken on unseen items and that the gate caught a large regression; I cannot rank small changes. SQL match is 0.750 over 4 items, one a rounding false alarm.
4. **What happens to a pending approval if the endpoint restarts?** It is lost: pending state is in process memory (Free Edition has no Lakebase) and the role in a reply is not authenticated. Decisions already made are written to a Delta table, best-effort.
5. **Why not let the LLM decide coverage?** Coverage, payable amount, fraud referral and authority must be replayable and unit-testable, so they are code and the model only routes and words (ADR-005). The critic and writer prompt block statements that a claim is approved.

## (e) Weak spots to volunteer before being asked

- **Replayed runs, found by review.** I reported 3 runs each; they were byte-identical cache replays. Corrected to 1 run, 36 held-out items.
- **Circular ground truth.** Expected fraud referral and authority came from the code under test. They test pass-through only.
- **Thin SQL sample.** 4 held-out analytics items; 0.750 is not an accuracy estimate.
- **Uncalibrated judges.** Same model family as the agent, no human labels, no kappa.
- **Masked-identity divergence (known issue).** The endpoint's service principal (216983c9-db86-4ef8-b500-9349e6025f94) sees masked notes and applicant ids, so the risk lookup returns nothing and the INCONSISTENT_NOTES flag and SIU routing for claims such as C00017 are lost. Evaluation ran as the workspace owner. The fix (`scripts/apply_masks.py` with AGENT_PRINCIPAL) is implemented but not applied: it grants access to unmasked PII and needs the owner's approval.
- **Per-process approval state.** Pending approvals live in one endpoint process's memory and the approving role is not authenticated.
- **Pending redeploy.** The endpoint serves model version 3; review fixes are committed but not deployed.
