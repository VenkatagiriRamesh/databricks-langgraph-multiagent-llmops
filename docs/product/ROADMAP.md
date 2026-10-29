# Plan: `databricks-langgraph-claims-copilot`

A multi-agent insurance underwriting and claims copilot on Databricks. LangGraph orchestrates the agents, MLflow handles tracing, evaluation, prompts and model lifecycle, and Unity Catalog governs everything.

Status: **draft for review. Nothing has been built.**

---

## 1. Why this project

### What your portfolio has today
| Project | Pattern |
|---|---|
| databricks-candidates-analysis | UC SQL functions, Managed MCP, one serving endpoint, governance |
| databricks-rag-and-mcp-agents | RAG plus an MCP agent on insurance data |
| databricks-vectorless-agentic-search | UC SQL functions, Managed MCP, news data |
| scd2 / shift-left / medallion | Data engineering fundamentals |

Four of the five CV projects are "Delta plus UC functions plus MCP". A sixth of the same kind adds little.

### What this one adds (the gaps)
| Gap on the CV | How the project closes it | Evidence in the repo |
|---|---|---|
| No LangGraph, multi-agent, or LLMOps keywords | Supervisor graph with specialist agents | `src/agents/`, graph diagram |
| No agent evaluation or quality gating | `mlflow.genai.evaluate`, golden set, a gate that blocks regressions | `eval/`, CI workflow, results table in README |
| Bosch "72% OpEx / 41% perf" claim is proprietary | Public token and cost ledger built from MLflow traces | cost dashboard, `docs/COST_ANALYSIS.md` |
| Thesis ML (2020) is the latest classic ML | Risk model trained with MLflow, registered in UC, promoted by alias | `src/models/`, UC model |
| Leadership or product ownership not visible | Run as a team product: PRD, ADRs, roadmap, CI, runbook | `docs/product/`, `docs/adr/` |
| No AI governance story (relevant for banks and insurers) | EU AI Act risk note, audit trail, human approval step | `docs/GOVERNANCE.md` |

### Goals
1. One flagship project that makes the "GenAI / Data & AI platform lead" CV line credible.
2. Every claim on the CV bullet can be shown live in an interview in under 5 minutes.
3. Different in kind from the existing repos: orchestration, evaluation and lifecycle, not more tools.

### Non-goals
- No new certification or study track.
- No GPU training or fine-tuning.
- No custom MCP server or hand-rolled standing service (consistent with your other repos).
- Not a production insurance system. It is a credible, honest demo on synthetic and public data.

### Anti-goals (would make it a failure even if it runs)
- Looking like a sixth copy of the UC-functions-plus-MCP pattern.
- Claims in the README that the evaluation does not back up.
- An agent that works only because of hardcoded demo prompts.

---

## 2. Data

| Source | Use | Reused? |
|---|---|---|
| Insurance dataset (1,338 rows: age, sex, BMI, children, smoker, region, charges) | Applicants and policies base table | **Yes**, from `databricks-rag-and-mcp-agents` |
| Synthetic claims (about 5k rows): claim amount, type, date, status, adjuster notes | Claims analysis and the human-approval scenarios | New, generated in Databricks |
| Synthetic underwriting guidelines and policy documents (about 30 short docs) | RAG corpus | New, LLM-generated and reviewed by hand |
| Golden evaluation set (about 60 to 80 questions with reference answers and expected tool route) | Evaluation and gating | New, hand-curated |

Rules carried over from your other repos:
- Generated data is created on Databricks and **never committed to GitHub**; only the generator code is.
- Everything is idempotent and re-runnable.

---

## 3. Architecture

### Unity Catalog layout
Catalog `claims_copilot`:

| Schema | Contents |
|---|---|
| `raw` | Landed files (Volume), `applicants_raw`, `claims_raw` |
| `curated` | `applicants`, `claims`, `policy_docs`, `policy_doc_embeddings` (or a Vector Search index) |
| `agent_tools` | UC functions the agents call (read-only analytics, lookup) |
| `models` | `risk_classifier`, `claims_copilot_agent` (registered), aliases `champion` / `challenger` |
| `eval` | Golden set, evaluation runs, cost ledger, human-approval log |

PII columns get UC column masks and row filters, as in the candidates project. Masking is enforced at the catalog layer, not in agent code.

### The LangGraph graph
```
            ┌────────────┐
 request ──▶│ Supervisor │  classify intent, pick route, track budget
            └─────┬──────┘
   ┌──────────┬───┴───────┬──────────────┐
   ▼          ▼           ▼              ▼
 SQL        Policy      Risk           Report
 analyst    RAG agent   scoring        writer
 agent      (retrieve   agent          agent
 (text-to-  + cite)     (calls UC
  SQL on                model)
  curated)
   └──────────┴─────┬─────┴──────────────┘
                    ▼
             ┌────────────┐
             │   Critic   │  groundedness, PII, policy-citation check
             └─────┬──────┘
          pass ┌───┴───┐ fail → back to the failing agent (max 2 retries)
               ▼       
        ┌─────────────┐   high risk or high value
        │ Approval    │──────────────────────────▶ interrupt() → human decision
        │ gate        │                              (approve / reject / edit)
        └──────┬──────┘
               ▼
            response + audit record
```

Design points:
- **State** is a typed `TypedDict` holding the question, route, tool outputs, citations, risk score, retry count, token spend and approval status.
- **Checkpointing** persists state so an interrupted run resumes after a human decision. See open risk R1.
- **Budget guard:** the supervisor stops a run that exceeds a token or step ceiling (feeds the cost story).
- **Critic** is a separate node with its own prompt, so evaluation can score it independently.

### MLflow usage
| Capability | What we do |
|---|---|
| Tracing | `mlflow.langchain.autolog()` plus manual spans on custom nodes; every run is a span tree |
| Prompt Registry | Supervisor, analyst, critic and writer prompts versioned, loaded by alias |
| Experiments | Risk model training runs: params, metrics, signature, input example |
| Model Registry (UC) | `risk_classifier` and the agent registered, promoted by `champion` alias |
| GenAI evaluation | `mlflow.genai.evaluate` on the golden set with built-in judges (correctness, groundedness, safety) plus custom scorers (correct route, correct tool, citation present, cost ceiling) |
| Gate | A script compares challenger and champion; the alias only moves if the challenger meets thresholds |
| Monitoring | Inference table to a cost and quality dashboard |

### Evaluation system (the centrepiece)

"State of the art" here means rigour: the evaluation is measured, calibrated and honest about uncertainty, not just a few LLM judges. Six layers:

| Layer | What is evaluated | How |
|---|---|---|
| **1. Component** | Each node alone: router accuracy, SQL correctness (execution match against reference results), retriever recall@k and MRR, risk model AUC and calibration, critic precision and recall | Unit-level evals per node on labelled slices |
| **2. Trajectory** | Did the agent take the right path: correct agents called, right tools, no redundant steps, retries within limit | Custom scorers over MLflow trace spans, comparing to expected route |
| **3. End-to-end** | Correctness, groundedness, completeness, citation validity, tone | `mlflow.genai.evaluate` with built-in and custom judges plus reference answers |
| **4. Multi-turn** | Task success across a conversation, including the approval flow | Scripted and LLM-simulated user sessions replayed against the graph |
| **5. Safety and robustness** | Prompt injection, PII leakage, out-of-scope requests, adversarial phrasing | Red-team set (phase 8) run through the same harness |
| **6. Operational** | Latency, tokens, cost per request, failure rate | Computed from traces and recorded as metrics next to quality |

Rigour practices (these are what separate it from a demo):
- **Judge calibration:** hand-label about 50 outputs, measure judge agreement with the labels (Cohen's kappa), and revise judge prompts until agreement is acceptable. Report the number.
- **Statistical honesty:** run each evaluation several times, report mean and confidence interval, and require a challenger to beat the champion beyond the noise, not by one point.
- **Error analysis:** failures are categorised (routing, retrieval, SQL, grounding, safety) and the breakdown goes in the README, with the top failure modes fixed and re-measured.
- **Versioned everything:** golden set, scorers, judge prompts and thresholds are versioned and stored as UC / MLflow evaluation datasets, so any past result can be reproduced.
- **Separate dev and held-out sets:** prompts are tuned on dev only; the held-out set is used for the release decision, which avoids overfitting to the test.
- **Regression suite:** every production failure or rejected approval becomes a permanent test case (the flywheel).
- **Online evaluation:** the same scorers run on sampled production traces from the inference table, with a quality and cost dashboard and drift alerts.
- **Gate and report:** each candidate release produces an evaluation report (table plus failure examples) that CI posts on the change and stores as an MLflow artifact.

Exact MLflow API names for datasets, scorers and production monitoring change between releases, so Phase 0 confirms what the workspace supports before the design is fixed.

### Serving
- The agent is logged as models-from-code using the `ResponsesAgent` interface and registered in UC.
- Deployed with `agents.deploy()` to one **scale-to-zero** endpoint, the same deliberate exception as your other repos.
- Asset Bundle (`databricks.yml`) defines jobs for data setup, training, evaluation and deployment.

---

## 4. Phased delivery

Each phase ends with something demonstrable and a commit. The product artifacts (right column) are produced as we go, not at the end.

| Phase | Work | Done when | Product artifact |
|---|---|---|---|
| **0. Spikes** (half day) | Verify the Free Edition risks R1 to R4 below | Each risk has a yes/no and a fallback | ADR-001 (platform constraints) |
| **1. Foundation** | Repo scaffold in house style, catalog and schemas, load insurance data, generate claims and policy docs, masks and filters | Tables exist, masked view verified | PRD (one page, success metrics) |
| **2. Tools** | UC functions for analytics, retriever over policy docs, train and register `risk_classifier` | Each tool callable and tested alone | ADR-002 (retrieval choice), ADR-003 (risk model) |
| **3. Agents** | Specialist agents, supervisor, critic, graph wiring, local runs | Graph answers the 10 core scenarios end to end | ADR-004 (why LangGraph) |
| **4. Observability** | Tracing everywhere, prompt registry, token and cost ledger, cost dashboard | One trace shows a request across all nodes with cost per node | `docs/COST_ANALYSIS.md` |
| **5. Evaluation and CI** | All six evaluation layers; golden set with dev and held-out split; judge calibration against about 50 hand labels; repeated runs with confidence intervals; error analysis; champion/challenger gate; GitHub Actions running unit tests and the eval gate; online scorers on sampled traces | A deliberately bad prompt change is blocked by the gate (demo this); judge agreement and error breakdown published | Eval results table, `docs/EVALUATION.md`, ADR on evaluation design |
| **6. Human-in-the-loop and deploy** | `interrupt()` approval flow, resume, approval log, `agents.deploy()`, endpoint test | Pause, approve, resume works on the deployed endpoint | Runbook |
| **7. Documentation** | Architecture diagram, EU AI Act note, `PRESENTATION.md`, `BUGFIXES.md`, CV bullets, LinkedIn post | A stranger can run it from the README | `docs/GOVERNANCE.md` |
| **8. GenAI depth** (replaces streaming and the App, which are dropped) | The five additions in section 4a | Each has a measured result in the README | ADR-005 to ADR-007 |

### 4a. GenAI depth (phase 8)

Chosen because these are the topics GenAI lead interviews probe, and none of your current repos covers them. Each one produces a number, not just a feature.

| Addition | What it is | Measured result |
|---|---|---|
| **Retrieval quality** | Hybrid retrieval (keyword plus embedding) with a reranker; retrieval evaluated separately from generation | Recall@k and MRR, hybrid vs embedding-only |
| **Safety and red-teaming** | Prompt-injection and PII-leak attack set (injected text inside adjuster notes and policy docs); critic and input guard defend against it | Attack success rate before and after guards |
| **Model routing for cost** | Small, cheap model for routing and the critic; larger model for analysis and writing | Cost per request and quality, routed vs single-model |
| **Agent memory and structured outputs** | Case memory across turns (checkpointed state plus a Delta-backed case history); Pydantic-validated outputs for every node | Schema-validity rate; multi-turn task success |
| **Feedback flywheel** | Human approval or rejection decisions and thumbs-down traces are mined back into the golden set; champion/challenger compared on replayed traffic | Golden set growth, challenger vs champion delta |

Also in scope here: the graph consumes some tools **through Managed MCP**, not only direct UC function calls, so the MCP skill on your CV is exercised by an orchestrated agent.

### 4b. Two-day build (decided scope for Free Edition)

Decisions made: domain is **insurance claims and underwriting automation** (intake, extraction, triage, routing, approval; the "business automation" angle that GCC insurer and bank roles ask for). Repo name: **`databricks-langgraph-insurance-automation`**. Workspace: the existing Free Edition workspace (`dbc-5545da01-a5ef`).

Two days is only possible by building a thin vertical slice first and being honest about what is deferred. The full plan above stays as the roadmap.

**Day 1: working multi-agent system, traced**
| Block | Output |
|---|---|
| Phase 0 spikes (1h) | Confirm checkpointing, judges, deploy on this workspace; delete unused endpoints |
| Data and UC (2h) | Catalog and schemas; reuse insurance data; generate about 1,000 synthetic claims and about 15 policy docs; PII masking |
| Tools (2h) | 4 to 5 UC functions, SQL-cosine retrieval, small risk model registered in UC |
| Graph (3h) | Supervisor, SQL analyst, policy RAG, risk, writer, critic, approval gate; runs locally and in the workspace |
| Tracing and prompts (1h) | MLflow tracing on all nodes; prompts in the Prompt Registry; token and cost per node |

**Day 2: evaluation, deploy, proof**
| Block | Output |
|---|---|
| Evaluation (4h) | Golden set of about 40 questions with dev and held-out split; layers 1 to 3 and 6 (component, trajectory, end-to-end, operational); cached judge calls; confidence intervals from 3 runs |
| Gate and CI (1h) | Champion/challenger gate; a bad prompt change shown to be blocked; GitHub Actions workflow |
| Deploy (1h) | One scale-to-zero endpoint; pause and approve flow tested |
| Docs (2h) | README with real numbers, architecture diagram, PRD, 3 ADRs, EU AI Act note, `PRESENTATION.md` |

**Deferred to a follow-up (honestly marked as roadmap in the README, never claimed):** multi-turn simulated users, the full red-team set, hybrid retrieval with reranking, model-routing experiment, agent memory, the feedback flywheel, online scoring on production traces.

**What cannot be skipped and what I cannot do for you**
- **Judge calibration:** about 30 outputs hand-labelled by you (30 minutes to an hour) in place of the 50 originally planned. Without it, the evaluation claim is weaker.
- **Quota:** the daily Free Edition caps may force the evaluation to spread past the second day. Cached results and a small golden set limit this. If a cap is hit, the work waits, and I will say so rather than cutting corners.
- **CV claims:** only what the delivered system demonstrates goes on your CV. Deferred items stay off it.

Rough effort for the full roadmap: about 3 to 4 weeks at evenings-and-weekends pace. Phases 0 to 3 are the risky ones; phases 4 to 7 are where the CV value comes from. Keep your study-free evenings.

---

## 5. Repository layout (house style plus additions)

```
databricks-langgraph-claims-copilot/
├── schema_mgt/            # 00_ setup: catalog, schemas, volume, load + synthesize data
├── src/
│   ├── 01_curate_data.ipynb
│   ├── 02_register_tools.ipynb
│   ├── 03_train_risk_model.ipynb
│   ├── 04_build_and_trace_graph.ipynb
│   ├── 05_evaluate_and_gate.ipynb
│   ├── 06_deploy_agent.ipynb
│   └── claims_copilot/    # importable package: graph, nodes, state, prompts, scorers
├── eval/                  # golden set definition, thresholds
├── tests/                 # unit tests for nodes, tools, scorers
├── scripts/               # data generators, deploy helpers
├── resources/             # Asset Bundle job definitions
├── docs/
│   ├── product/           # PRD, roadmap, backlog
│   ├── adr/               # architecture decision records
│   ├── ARCHITECTURE.md, GOVERNANCE.md, COST_ANALYSIS.md, SETUP.md
│   └── architecture_diagram.png
├── .github/workflows/     # CI: lint, tests, eval gate
├── databricks.yml
├── BUGFIXES.md, PRESENTATION.md, README.md, LICENSE
```

The numbered notebooks follow your portfolio skill (config cell, idempotency, validation cell). The graph logic itself lives in the package so it is testable and importable by model serving.

---

## 6. Success criteria (what "good" means)

1. **Routing accuracy** on the golden set at or above 90%.
2. **Groundedness** at or above 0.85 per the judge; every policy answer cites a document.
3. **Cost:** median cost per request and p95 reported; a hard budget cap is enforced.
4. **Gate works:** a regression is caught by CI, demonstrated and documented.
5. **Governance:** PII never appears in agent output (tested), every approval is logged.
6. **Reproducible:** a fresh workspace goes from `bundle deploy` to a working endpoint following the README.
7. **Cheap:** idle cost near zero; the only standing service is the scale-to-zero endpoint.
11. **Evaluation rigour:** judge agreement with human labels is reported (kappa), results carry confidence intervals, and a failure-mode breakdown is published.
12. **Evaluation coverage:** all six layers (component, trajectory, end-to-end, multi-turn, safety, operational) run from one command and in CI.
8. **Retrieval:** hybrid plus rerank beats embedding-only on recall@k, reported honestly either way.
9. **Safety:** prompt-injection attack success rate falls measurably after guards; the before and after are both in the README.
10. **Routing:** the routed-model setup costs less than single-model at comparable quality.

Numbers above are targets; the README will report the real values, including misses.

---

## 7. Risks and open items

| ID | Risk | Fallback |
|---|---|---|
| R1 | LangGraph persistent checkpointing may not be available on Free Edition (for example a Lakebase-backed saver) | A small Delta-table-backed checkpointer, or in-memory saver for the demo with the limitation documented |
| R2 | `mlflow.genai.evaluate` judges may be rate limited or behave differently on pay-per-token models | Fewer judges, a smaller golden set, cached results |
| R3 | `agents.deploy()` plus `interrupt()` resume semantics across calls | Implement approval as a two-call pattern (propose then confirm) keyed by a run id |
| R4 | Vector Search quota on Free Edition | In-process SQL cosine similarity, as in the candidates project |
| R5 | Scope creep from phase 8 | Cut phase 8 items one at a time, agent memory first; phases 0 to 7 stand alone |
| R6 | LLM-generated synthetic data looks unrealistic | Seed from the real insurance statistics; review by hand |

I have not verified R1 to R4. Phase 0 exists to settle them before committing to the design.

---

## 8. CV and interview payoff

Draft CV project entry (to be replaced with measured numbers):

> **Multi-Agent Claims Copilot on Databricks** · LangGraph, MLflow GenAI Evaluation, Unity Catalog, Mosaic AI Serving
> • Supervisor-and-specialist agent graph with human-in-the-loop approval, served on a scale-to-zero endpoint.
> • Evaluation-gated releases: CI blocks agent changes that regress routing or groundedness on a golden set.
> • Per-node token and cost tracing from MLflow, with a hard budget guard.

### ATS keyword coverage

ATS matching reads your CV text, so each keyword below must appear in the CV (project entry or skills line) **and** be real in the repo. I will not list a term the project does not demonstrate.

| Keyword (as job descriptions write it) | Where it is real in the project |
|---|---|
| LangGraph, LangChain | The orchestration graph (`claims_copilot/graph.py`) |
| Multi-agent systems, agent orchestration, supervisor pattern | Supervisor plus SQL, RAG, risk, writer and critic agents |
| Agentic AI, tool calling, function calling | UC functions and Managed MCP tools used by the agents |
| Model Context Protocol (MCP) | Tools consumed through Managed MCP |
| RAG, hybrid search, reranking, vector search, embeddings | Policy RAG agent, phase 8 retrieval work |
| LLMOps, MLOps, model registry, CI/CD for ML | MLflow registry with aliases, eval-gated GitHub Actions |
| LLM evaluation, LLM-as-a-judge, golden dataset, trajectory evaluation, online evaluation | `mlflow.genai.evaluate`, custom scorers, six-layer evaluation system, calibrated judges, sampled-trace scoring |
| Observability, tracing, monitoring | MLflow tracing, cost ledger, inference tables |
| Guardrails, prompt injection, red-teaming, responsible AI | Critic node, attack set, EU AI Act note |
| Human-in-the-loop | `interrupt()` approval gate |
| Prompt engineering, prompt management | MLflow Prompt Registry |
| Text-to-SQL | SQL analyst agent |
| Unity Catalog, data governance, Mosaic AI, Model Serving | Whole project |
| Cost optimisation, FinOps for LLMs | Token ledger, model routing |

Suggested CV skills-line change: add one row, "Agentic AI & LLMOps: LangGraph, multi-agent orchestration, MLflow GenAI evaluation and tracing, prompt registry, guardrails, human-in-the-loop". The project entry and the README should use the same wording so the terms repeat consistently.

Interview stories this supports:
- "How do you know an agent change is safe to ship?" (the eval gate)
- "How do you control LLM cost?" (ledger plus budget guard, linked to your Bosch result)
- "How do you govern an AI system in a regulated domain?" (masking, audit trail, human approval, EU AI Act note)
- "Tell me how you run a technical project as a lead." (PRD, ADRs, roadmap, CI)
- "How do you evaluate retrieval, and how do you defend against prompt injection?" (recall@k/MRR, red-team set with before/after numbers)
- "How do you trade model cost against quality?" (routing experiment)
- "How does an agent get better after launch?" (feedback flywheel into the golden set)

The CV should also drop to the 3 or 4 strongest projects so this one leads.

---

## 9. Decisions needed from you

1. **Domain:** decided: insurance claims and underwriting automation.
2. **Scope:** decided: the two-day slice in section 4b, the rest as roadmap.
3. **Repo name:** decided: `databricks-langgraph-insurance-automation`. GitHub visibility (public or private) still needs your answer.
4. **Workspace:** decided: existing Free Edition workspace. The CLI login for profile `candiate-analysis` has expired and needs `databricks auth login --profile candiate-analysis` from you.
5. **Still needed:** the SQL warehouse ID, which existing serving endpoints may be deleted, and about an hour of your time on Day 2 for judge calibration labels.

After you review this, the next steps are: a short design doc from your answers, then a step-by-step implementation plan for phases 0 and 1. No building before that.
