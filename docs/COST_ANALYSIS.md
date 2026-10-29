# Cost analysis

All dollar figures here are notional. Databricks Free Edition does not bill per token. The price table in `src/insurance_automation/llm/cost.py` was written from memory of public list prices and has not been verified; check current published prices before quoting any figure.

## Price table used

USD per million tokens (input, output), for the default model `databricks-meta-llama-3-3-70b-instruct`: 0.50 and 1.50. The file also holds entries for `databricks-meta-llama-3-1-8b-instruct` (0.15, 0.45) and `databricks-gpt-oss-120b` (0.15, 0.60). A model not in the table is priced at zero by the ledger.

## Cost per request, from the committed reports

The ledger records tokens in and out per node and prices them with the table above. Median cost per request:

| Report | Items | Median cost (USD) |
|---|---|---|
| Held-out, current system (`report_heldout_v1.json`) | 31 | 0.000399 |
| Dev v1 | 29 | 0.000439 |
| Dev v2 | 46 | 0.000434 |
| Dev v3 | 46 | 0.000414 |
| Challenger: supervisor "refuse if not completely certain" | 46 | 0.000418 |
| Challenger: writer "at most eight words" | 46 | 0.000333 |

The held-out median, about 0.0004 USD, is the figure used elsewhere. The release gate ceiling is 0.02 USD median; every run passed the cost check (`within_cost_budget` 1.000). The shorter-writer challenger is cheaper, and it is also the one the gate rejected for quality, which is the point of gating on quality and cost together. Only the median is reported in these files; no mean or p95 cost is committed.

## Tokens by node

These are observed examples from individual traces, not averages or distributions:

| Node | Example tokens in | Example tokens out |
|---|---|---|
| Supervisor | about 140 | about 2 |
| Writer | about 300 | about 60 |
| Critic (LLM review) | about 330 | about 80 |

The SQL analyst also makes an LLM call on analytics questions; no example figure is recorded for it here. Do not add these examples up and expect to reproduce the median: the number of LLM calls differs by route and by critic retries.

## Where calls are skipped

- A question that names a claim id (pattern `C00000`) is routed to the claim decision pipeline by a regular expression, so the supervisor LLM call is skipped.
- Coverage, fraud screening, authority and (when the registered model loads) risk scoring are code, not LLM calls. The critic runs deterministic checks first and calls the LLM review only if they pass.
- A request that is refused with a fixed message (empty or out of scope after routing) costs only the supervisor call.

## Cache effect on evaluation reruns

LLM responses are cached on disk under `.local_cache/llm`, and each (item, run, graph fingerprint) result is cached. The fingerprint covers the model, all prompts and the agent and tool source. A rerun after a quota error resumes from the cache instead of repeating finished work; changing a prompt or source file changes the fingerprint and invalidates it. The saving from a cached rerun was not measured, and it was not checked whether cached calls are counted in the ledger, so whether the reported medians include cached calls is unverified.

## Free Edition quota behaviour

Free Edition has daily compute and Foundation Model limits. Quota errors during evaluation are expected; the harness appends progress to JSONL and the cache lets a rerun resume (see `docs/SETUP.md`). The held-out run is 93 graph runs and the dev runs are 3 runs over 29 or 46 items; reduce `--runs` if limits bite. Specific quota numbers are not recorded in the repository.

## Idle cost

The only standing compute is the serving endpoint, which is configured to scale to zero, so there is no idle compute charge from it on a plan that bills for it. On Free Edition nothing is billed per token or per hour in any case. The cost of scale-to-zero is a slow first request after idle, and pending approvals held in the endpoint process are lost when it scales down (see `docs/GOVERNANCE.md`). Latency measured: held-out p95 12.3 s; deployed sample responses ranged from 0.6 s to 13.3 s (`docs/endpoint_samples.md`).

## What changes at scale

Not built, and not measured. These are the changes to evaluate, in this order.

- **Provisioned throughput or dedicated serving for the foundation model** instead of pay-per-token, once request volume is steady enough to justify reserved capacity.
- **Caching at serving time.** The on-disk cache exists only for evaluation. A shared cache for repeated policy and analytics questions would cut calls; it needs a freshness rule for SQL answers.
- **A smaller router model.** The supervisor call is short (about 140 tokens in as an example) and returns one word, so a smaller model could do it. This needs a routing-accuracy comparison on the golden set before adopting; the held-out route accuracy of 0.968 is the baseline to hold.
- **Model routing and prompt trimming** are on the roadmap, not built.
- State and approvals would need to move out of process memory (a persistent checkpointer) before the endpoint can run more than one replica.
