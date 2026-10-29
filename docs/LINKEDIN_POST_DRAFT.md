# LinkedIn post drafts

Status: built, evaluated and deployed (endpoint verified 2026-10-29). Held-out numbers are in docs/EVALUATION.md. Judge calibration against hand labels is not done, so no kappa exists. Re-check every figure against docs/EVALUATION.md before posting.

## Full post (about 240 words), use now

A claims team does not lose time on the easy claims. It loses time deciding which claims are easy, which need an adjuster, which need a senior sign-off, and which should go to SIU, and then proving afterwards why that call was made.

I built an open-source version of that workflow on Databricks Free Edition.

A LangGraph supervisor routes each request to specialist agents: coverage checking against policy clauses, fraud screening with explainable red flags (never an automatic denial), underwriting risk with adverse-action style reason codes, an SQL analyst for loss-ratio and frequency questions, and a critic that can send a draft back twice before it escalates.

Nothing is approved by prompt wording. A claims authority matrix decides who must sign off: auto, adjuster, senior adjuster, manager, or SIU. The audit record names the required role.

Around it: MLflow tracing per node, a prompt registry, an evaluation-gated release flow, Unity Catalog governance with PII masked at the catalog layer, and a fairness audit. The risk model excludes sex, which is the EU gender-neutral pricing context.

Measured on a held-out set of 31 items, 3 runs each: route accuracy 0.968, groundedness 0.944 (LLM judge, not yet calibrated against human labels), safety 1.000 on 3 injection cases, median notional cost per request about 0.0004 USD. Risk model disparate impact ratios: sex 0.937, region 0.865.

Honest limits: all data is synthetic or public toy data, fraud labels are seeded (so fraud precision and recall of 1.0 are partly circular), judge scores are uncalibrated, and this is not a validated pricing model.

Code, plan and decision records: https://github.com/VenkatagiriRamesh/databricks-langgraph-multiagent-llmops

For insurance practitioners: which authority limits or fraud indicators would you challenge first?

#Insurance #Databricks #LangGraph #MLflow #AIGovernance #DataEngineering

## Earlier build-in-public variant (about 90 words), superseded: written before results existed, do not post

I am building a claims triage copilot for insurers on Databricks Free Edition: a LangGraph supervisor, specialist agents for coverage, fraud screening and underwriting risk, and a claims authority matrix that decides who must approve each decision.

The synthetic data layer is done and verified, with PII masked in Unity Catalog. Agents, evaluation and deployment come next. No results yet, and I will publish numbers only when they are measured.

Repo: https://github.com/VenkatagiriRamesh/databricks-langgraph-multiagent-llmops

Which fraud indicators would you challenge first?

#Insurance #Databricks #LangGraph #AIGovernance

## Before you post

- The full post has no placeholders left; confirm each figure against docs/EVALUATION.md and docs/GOVERNANCE.md.
- Confirm the repo README shows the same real numbers and a "done / roadmap" section, and that nothing deferred is implied.
- Attach the architecture diagram (see docs/DIAGRAM_PROMPT.md); a post with a visual gets read more.
- Tag no company or person without permission, including Bosch and Databricks.
- Re-read for tone: no hype words, at most 2 emoji (this draft has none).
