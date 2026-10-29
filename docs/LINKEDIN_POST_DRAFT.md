# LinkedIn post drafts

Status: built, evaluated and deployed (endpoint model version 3, verified 2026-10-29; review fixes pending redeploy). Held-out numbers (36 items, 1 run) are in docs/EVALUATION.md. Judge calibration against hand labels is not done, so no kappa exists. Re-check every figure against docs/EVALUATION.md before posting.

## Full post (about 250 words, under 260), use now

A claims team does not lose time on the easy claims. It loses time deciding which are easy, which need an adjuster, which need a senior sign-off, and which go to SIU, and then proving why that call was made.

I built an open-source version of that workflow on Databricks Free Edition.

A LangGraph supervisor routes each request to specialist agents: coverage checking against policy clauses, fraud screening with explainable flags (never an automatic denial), underwriting risk with reason codes, an SQL analyst, and a critic that can send a draft back twice before it escalates.

Nothing is approved by prompt wording. A claims authority matrix decides who signs off: auto, adjuster, senior adjuster, manager, or SIU. Around it: MLflow tracing per node, a prompt registry, an evaluation-gated release, Unity Catalog governance with PII masked at the catalog layer, and a fairness audit. The risk model excludes sex.

Held-out set, 36 items, one run each: route accuracy 0.972, groundedness 0.903 (LLM judge, uncalibrated), safety 1.000 on 6 injection cases, SQL match 0.750 on only 4 items. An evaluation gate blocked a test regression, correctness 0.951 to 0.674 on the dev split.

Honest limits: the data is synthetic. Fraud and authority ground truth come from the same code the agent uses, so those matches test pass-through, not detection. An independent review found my first evaluation reported repeated runs that were cache replays. The deployed endpoint runs as an identity that sees masked PII, so it behaves differently from my evaluation. The fix is written but not applied.

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
- Confirm the repo README shows the same numbers (36 held-out items, 1 run) and a "done / roadmap" section, and that nothing deferred is implied.
- Attach the architecture diagram (see docs/DIAGRAM_PROMPT.md); a post with a visual gets read more.
- Tag no company or person without permission, including Bosch and Databricks.
- Re-read for tone: no hype words, at most 2 emoji (this draft has none).
