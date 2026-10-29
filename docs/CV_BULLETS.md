# CV material

Every figure comes from `docs/EVALUATION.md` and the committed reports in `eval/results/`. Held-out numbers are used throughout. Re-check before sending.

## (a) Resume bullets

1. Built a LangGraph multi-agent claims copilot on Databricks with deterministic coverage, fraud and authority tools; held-out route accuracy 0.968, safety 1.000 on 3 injection cases.
2. Implemented MLflow tracing, prompt registry and a custom evaluation harness; held-out groundedness 0.944 (LLM judge, uncalibrated) over 31 items, 3 runs.
3. Designed an evaluation-gated release: gate blocked a regression (correctness 0.951 to 0.674) and passed a within-noise change; deployed a scale-to-zero serving endpoint.

Word counts are under 30 each. Optional fourth, if space allows: "Trained and registered a risk model in Unity Catalog (AUC 0.888, sex excluded); disparate impact ratios 0.937 (sex), 0.865 (region)."

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
| GenAI evaluation | Custom harness, 77-item golden set, CIs, release gate; not `mlflow.genai.evaluate` | Yes (say custom harness; judges uncalibrated) |
| Prompt registry | Four prompts in `insurance_automation.eval`, alias `production`, with in-code fallback | Yes |
| Guardrails | SQL guard, critic checks, injection handling, authority matrix | Yes (3 injection cases, not a red-team suite) |
| Human-in-the-loop | Approval gate, approve/reject/edit, replay refusal, decision log | Yes (role not authenticated on Free Edition; state is per process) |
| Unity Catalog governance | Column masks, UC functions, model registry with alias, prompt registry in UC | Yes (one workspace, synthetic data) |
| Managed MCP / MCP consumption | UC functions exist and are exposable; the graph does not call MCP | NOT safe |
| Hybrid search / reranking | Retrieval is TF-IDF only (ADR-002) | NOT safe |
| Red-teaming | 3 injection items only | NOT safe |
| Online evaluation / monitoring | Offline golden-set evaluation only | NOT safe |
| Calibrated LLM judges / kappa | Sheet unlabelled, kappa not measured | NOT safe |
| Fine-tuning, GPU | Not done | NOT safe |

## (d) Interview questions this project supports

1. **How do you know the evaluation is trustworthy?** Dev and held-out are separate: the dev set was tuned on and the held-out set (31 items, 3 runs) was not, and the first dev run exposed two bugs in my own scorers. The judge scores are not yet calibrated against my hand labels (the 30-row sheet is unlabelled), so I call them indicative.
2. **Your fraud precision and recall are 1.0. Is that real?** No, it is partly circular: the expected referral came from the same deterministic screener on the same data, and the labels are seeded. It shows the graph passes the screener's verdict through correctly, not that it detects real fraud.
3. **31 held-out items is small. What can you conclude?** The intervals are wide (route accuracy 0.968, interval 0.902 to 1.000), so 0.97 against 1.00 is not resolvable. I can say the system is not badly broken on unseen items and that the gate caught a large regression; I cannot rank small changes.
4. **What happens to a pending approval if the endpoint restarts?** It is lost, because pending state is in process memory (Free Edition has no Lakebase), and the role in a reply is not authenticated. Decisions already made are written to a Delta table, best-effort; production would need a persistent checkpointer and real identity.
5. **Why not let the LLM decide coverage?** Coverage, payable amount, fraud referral and authority must be replayable and unit-testable, so they are code and the model only routes and words (ADR-005). The critic and the writer prompt also block statements that a claim is approved, so an injected instruction cannot change the decision or skip the approval step.
