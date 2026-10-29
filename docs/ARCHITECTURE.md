# Architecture

This document describes what is built in this repository. Evaluation results are not repeated here; see [docs/EVALUATION.md] for measured numbers. Platform limits are in [ADR-001](adr/001-platform-constraints.md).

## 1. Components

| Component | Where | Role |
|---|---|---|
| Graph | `src/insurance_automation/agents/` | LangGraph state machine: nodes, routing, retries, approval gate |
| Tools | `src/insurance_automation/tools/` | Deterministic logic: guarded SQL, TF-IDF retrieval, coverage check, fraud screen, authority matrix, risk model |
| LLM layer | `src/insurance_automation/llm/` | Foundation Model client, on-disk response cache, per-node token and cost ledger |
| Live wiring | `src/insurance_automation/runtime.py` | Builds the graph context against the SQL warehouse, Foundation Models and MLflow |
| Serving wrapper | `agents/serving.py`, `agents/entry.py` | `ResponsesAgent` with the two-call approval pattern |
| Evaluation | `src/insurance_automation/evaluation/` | Golden set loader, scorers, LLM judges, harness, statistics, gate, judge calibration |
| Scripts | `scripts/` | One script per lifecycle step (see SETUP.md) |
| Data generator | `src/insurance_automation/data/generate.py` | Deterministic synthetic policies, claims and policy clauses |

## 2. Data flow

```
question -> supervisor (LLM picks a route) -> specialist path -> writer (LLM words the answer)
         -> critic -> approval gate (human, when required) -> answer + trace + approval log
```

Routes are `analytics`, `policy`, `risk`, `claim_decision` and `refuse`. The supervisor returns one word. Anything that is not a known route becomes `refuse`. A `claim_decision` route without a claim id (pattern `C00000`) also becomes `refuse`.

## 3. The graph

| Node | Type | What it does |
|---|---|---|
| supervisor | LLM | Classifies the question into a route and extracts a claim id |
| refuse | code | Returns a fixed refusal message |
| sql_analyst | LLM + guard | The LLM writes one SELECT. `sql_guard` accepts it only if it is a single read-only SELECT on tables in `insurance_automation.curated`, with no comments; `LIMIT 200` is added if missing. Otherwise the query is refused and not run |
| policy_rag | code | TF-IDF cosine retrieval over the policy clauses, top 3 hits, returns nothing when no term overlaps |
| coverage_checker | code | Checks the claim against the policy: exclusions, waiting period, deductible and limit, reporting deadline. Returns covered or not, reasons, clause ids and payable amount |
| fraud_screener | code | Six explainable rules (late report, near inception, round amount, just under an authority limit, repeat claimant, inconsistent notes). Score at or above 0.4 recommends SIU referral. Also sets the required authority from the payable amount |
| risk_scorer | code + model | Loads the registered `champion` risk model, returns probability, band and top three reason codes. Falls back to training in-process from the applicants table if the registered model cannot be loaded |
| writer | LLM | Words the answer from the structured evidence; may cite only evidence ids it was given |
| critic | code, then LLM | Code checks first: cited ids must be in the evidence, and a draft that grants a claim while notes or policy text contain an injected instruction fails. If those pass, an LLM review returns pass or fail |
| escalate | code | After two failed critic rounds, returns an escalation message and marks the run pending human review |
| approval_gate | code | Pauses with LangGraph `interrupt()` when the required authority is not `auto` |

Edges: `claim_decision` goes coverage_checker, then fraud_screener and risk_scorer only if the claim is covered, otherwise straight to the writer. Analytics, policy and risk go directly to the writer. The writer feeds the critic. A critic failure returns to the writer at most twice, then goes to escalate.

State is a typed dict (`agents/state.py`). A `MemorySaver` checkpointer holds it per thread id.

## 4. Why decisions come from deterministic tools

The LLM does two jobs: choose the route, and put structured evidence into words. It does not decide coverage, payable amounts, fraud referral, risk bands or who must approve. Those come from code that can be unit-tested and replayed. See [ADR-005](adr/005-deterministic-decisions-llm-wording.md).

Consequences used in the design: the writer prompt forbids stating that a claim is approved or paid; the critic blocks drafts that do; the authority matrix is a pure function of payable amount and fraud referral, so evaluation can check it exactly.

## 5. Unity Catalog layout

Catalog `insurance_automation`:

| Schema | Contents |
|---|---|
| `raw` | Volume `landing` (generated JSONL), `applicants_raw`, `claims_raw` |
| `curated` | `applicants` (1,338), `policies` (1,338, synthetic), `claims` (1,000, synthetic), `policy_docs` (17 clauses), the two masking functions |
| `agent_tools` | SQL functions `get_claim`, `get_policy`, `claims_summary_by_type`, `get_policy_clause` |
| `models` | `risk_classifier` (alias `champion`); `claims_copilot_agent` when `deploy_agent_endpoint` is run (alias `challenger`) |
| `eval` | Registered prompts (`supervisor`, `sql_analyst`, `writer`, `critic`); `approval_decisions` (created by the serving entrypoint when the agent loads) |

The `agent_tools` functions are read-only and can be exposed through Managed MCP. The graph does not call them: it reaches the warehouse through SQL statements. They are registered, not consumed by the graph.

## 6. MLflow usage

| Capability | Use |
|---|---|
| Tracing | Every node runs in a span carrying `tokens_in` and `tokens_out`; a root span wraps each invoke or resume. The demo run showed traces with per-node token counts |
| Prompt Registry | Four prompts registered in `insurance_automation.eval` with alias `production`; `RegistryPromptStore` loads them and falls back to the in-code defaults if the registry fails |
| Model Registry (UC) | `risk_classifier` logged as a pyfunc with signature and input example, promoted by alias only |
| Experiments | Training run logs params, holdout AUC and fairness ratios; the evaluation run logs metrics with confidence intervals, cost, latency, STP and escalation rates |
| Evaluation harness | A custom harness (`evaluation/harness.py`) with resumable JSONL progress, run per split and repeated runs. It logs to MLflow but does not use `mlflow.genai.evaluate`; the built-in judges returned empty metrics (ADR-001) |

## 7. Evaluation layers

The plan describes six layers. This table says which exist.

| Layer | Status | What exists |
|---|---|---|
| 1. Component | Partial | Risk model holdout AUC at training; SQL execution match against reference rows; fraud referral and authority matches. No retriever recall@k or critic precision/recall |
| 2. Trajectory | Shipped, simple | `tool_trajectory` compares the ordered list of tools called with the expected list. Not computed from trace spans |
| 3. End-to-end | Shipped | Route accuracy, citation validity, groundedness and correctness from custom LLM-as-judge prompts, cached per prompt |
| 4. Multi-turn | Roadmap | Not built |
| 5. Safety and robustness | Partial | Golden items with forbidden phrases and injected adjuster notes (at least 3 seeded), SQL guard, critic checks. The full red-team set is roadmap |
| 6. Operational | Shipped | Cost per request from the ledger (median reported), p95 latency, straight-through-processing rate, escalation rate |

Also built: a golden set of 77 items (46 dev, 31 held-out) across all five routes, mean and confidence interval over repeated runs, a release gate (absolute thresholds plus no regression beyond the champion's interval), and an export plus Cohen's kappa routine for judge calibration. Results and calibration outcome: [see docs/EVALUATION.md].

Roadmap, not built: simulated multi-turn users, full red-team set, hybrid retrieval with reranking, model routing, agent memory, feedback flywheel, online scoring on production traces.

## 8. Release flow

`run_eval` writes `eval/results/latest_report.json`. `gate_release` exits 1 if thresholds fail (route accuracy 0.90, groundedness 0.85, safety 1.00, authority match 0.90, median cost 0.02 USD) or if a metric regressed beyond the champion's confidence interval. On pass without `--offline` it moves the `champion` alias. `deploy_agent_endpoint` logs the agent from code, registers it with alias `challenger` and, with `--deploy`, creates a scale-to-zero endpoint. The endpoint `agents_insurance_automation-models-claims_copilot_agent` (model version 3) was deployed and exercised on 2026-10-29; sample responses are in `docs/endpoint_samples.md`. CI (`.github/workflows/ci.yml`) runs ruff, the offline unit tests and, if a report file is present, the offline gate.

## 9. Free Edition design choices

| Constraint | Choice |
|---|---|
| No Lakebase | In-memory checkpointer; pending approvals live in the endpoint process; each decision is also written to a Delta log table |
| One warehouse, quotas | Response cache on disk, resumable evaluation, small golden set |
| No Vector Search used | In-process TF-IDF retrieval (ADR-002) |
| Built-in judges empty | Custom LLM-as-judge prompts |
| Flaky CLI token refresh | Export a fresh `DATABRICKS_TOKEN` before long runs |
| One custom endpoint | Scale-to-zero, deployed only through the script |
