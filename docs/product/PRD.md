# PRD: Insurance claims and underwriting automation

Status: built as a portfolio project on Databricks Free Edition. Date: 2026-10-29.

## Problem

Claims handlers and underwriters answer coverage, risk and portfolio questions by hand across policy text, claim records and spreadsheets. An LLM can speed this up, but a model that decides coverage, amounts or approvals cannot be audited, and a model that is changed without measurement can regress unnoticed.

## Users

- Claims adjuster: asks for a coverage check and a recommended decision on one claim.
- Underwriter: asks for an applicant risk score with reasons.
- Analyst or manager: asks portfolio questions (counts, averages by type).
- Reviewer (senior adjuster, manager, SIU): approves, rejects or edits proposed decisions above their limit.
- AI platform lead (the author): needs a release process that blocks regressions.

## Goals

1. Answer five question types by routing: analytics, policy, risk, claim decision, and refusal of out-of-scope requests.
2. Take every decision from deterministic tools; use the LLM only for routing and wording.
3. Require human approval above the auto-settle limit, by an authority matrix, and never auto-deny on fraud flags.
4. Trace every run with per-node token counts, and version prompts and models.
5. Gate releases on a golden-set evaluation.

## Non-goals

- Not a production insurance system or a validated pricing model.
- No real customer data.
- No fine-tuning or GPU work.
- No custom MCP server.

## Success metrics

Qualitative: a stranger can run the setup, ask a claim question, see the proposed decision pause for approval, and read the trace.

Targets (from the plan, section 6; these are targets, not results):

| Target | Value |
|---|---|
| Routing accuracy on the golden set | at least 90% |
| Groundedness per the judge | at least 0.85, every policy answer cites a clause |
| Cost | median and p95 per request reported; hard cap enforced; the gate uses a median ceiling of 0.02 USD |
| Gate | a regression is caught and demonstrated |
| Governance | PII not in agent output; every approval logged |
| Judge quality | agreement with human labels reported (kappa); results carry confidence intervals |

Measured results: [see docs/EVALUATION.md] (golden set 86 items, 50 dev and 36 held-out; held-out numbers are one run over applicable items, and judges are uncalibrated).

## Scope

Now: supervisor graph with SQL analyst, policy RAG (TF-IDF), coverage checker, fraud screener, risk scorer, writer, critic and approval gate; UC tables, masks and functions; registered risk model with fairness audit; prompt registry; custom evaluation harness with judges, confidence intervals and a release gate; one scale-to-zero serving endpoint, deployed and verified on 2026-10-29 (model version 3; review fixes committed, pending redeploy). The endpoint's service principal sees masked PII, so served behaviour differs from the evaluated behaviour until an owner-approved mask exception is applied (see GOVERNANCE.md).

Roadmap (not built): multi-turn simulated users, full red-team set, hybrid retrieval with reranking, model routing, agent memory, feedback flywheel, online scoring.

## Risks

| Risk | Mitigation |
|---|---|
| Synthetic data hides real-world difficulty | State the limit; do not claim real-world accuracy |
| Seeded fraud labels and code-derived expected values flatter fraud and authority metrics | Describe them as pass-through checks, not detection |
| Endpoint identity sees masked PII, so served behaviour differs from evaluation | Documented as a known issue; fix implemented, awaiting owner approval |
| LLM judges disagree with humans | Calibrate on hand labels and report kappa |
| Free Edition quotas interrupt evaluation | Cache and resume |
| Approval role not authenticated, pending runs per process | Documented in GOVERNANCE.md; production would need identity and durable state |
| Prompt injection in notes or policy text | SQL guard, critic checks, writer instructed to treat text as data; full red-team is roadmap |
