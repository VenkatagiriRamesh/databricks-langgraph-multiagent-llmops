# Setup

## Prerequisites

- A Databricks workspace (built and tested on Free Edition, serverless only) and the Databricks CLI.
- Python 3.11 or newer.
- The applicants table `insurance_rag_agent.raw.policies_raw` from the author's earlier RAG project, or an equivalent table with columns age, sex, bmi, children, smoker, region, charges. `bootstrap_data` reads it by that name (`SOURCE_TABLE`).
- One SQL warehouse id.

## Install

```
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest -q        # offline unit tests, no workspace needed
```

## Authenticate and configure

```
databricks auth login --profile <profile>
databricks warehouses list --profile <profile>
cp .env.example .env
```

Fill `.env`: `DATABRICKS_CONFIG_PROFILE`, `DATABRICKS_WAREHOUSE_ID`, and optionally `UC_CATALOG` (default `insurance_automation`) and `FM_API_MODEL` (default `databricks-meta-llama-3-3-70b-instruct`). Export the variables into your shell; the scripts read the environment.

## Script order

Run from the repository root.

| Step | Command | Result |
|---|---|---|
| 1 | `python -m scripts.setup_uc_resources` | Catalog, five schemas, Volume `raw.landing` |
| 2 | `python -m scripts.bootstrap_data` | Tables, 1,338 applicants, 1,338 policies, 1,000 claims, 17 clauses, PII masks |
| 3 | `python -m scripts.register_tools` | Four UC SQL functions in `agent_tools` |
| 4 | `python -m scripts.train_register_model` | Trains, prints AUC and fairness, registers `risk_classifier`, alias `champion` |
| 5 | `python -m scripts.register_prompts` | Prompts in the registry, alias `production` |
| 6 | `python -m scripts.demo_run` | Four sample questions through the live graph |
| 7 | `python -m scripts.build_golden_set` | Writes `eval/golden_set.jsonl` |
| 8 | `python -m scripts.run_eval --split dev` (and `--split heldout`) | Report at `eval/results/latest_report.json`, metrics in MLflow |
| 9 | `python -m scripts.gate_release --report eval/results/latest_report.json --model-name <catalog>.models.claims_copilot_agent --model-version <n>` | Gate decision; sets `champion` on pass. Add `--offline` to check without setting an alias |
| 10 | `python -m scripts.deploy_agent_endpoint --deploy` | Registers the agent as `challenger`, creates a scale-to-zero endpoint. Omit `--deploy` to register only |

`resources/jobs.yml` defines a job chaining the scripts. It has not been verified end to end, and its `gate_release` task passes no arguments although the script requires `--report`; use the local script order above.

## Token note

Long runs (steps 6 and 8) fail midway if the CLI token expires, and the CLI refresh is intermittently unreliable (ADR-001). Before a long run:

```
export DATABRICKS_HOST=<workspace url>
export DATABRICKS_TOKEN=$(databricks auth token --profile <profile> | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
```

`runtime.refresh_token_env()` does the same from Python. Do not print or commit the token.

## Quota notes

- Free Edition has daily compute and Foundation Model limits. LLM responses are cached under `.local_cache/llm`, and `run_eval` appends progress to a JSONL file, so a rerun after a quota error resumes without redoing finished items.
- Evaluation uses repeated runs (`--runs`, default 3) over each split; reduce `--runs` if you hit limits.
- The deploy script refuses if more than one custom serving endpoint exists, unless `--force` is passed.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `DATABRICKS_WAREHOUSE_ID is not set` | Env not exported | Export the variable or load `.env` into the shell |
| 401 in MLflow trace export, or CLI exit status 45 | Token refresh failure | Export a fresh `DATABRICKS_TOKEN` |
| Evaluation stops with a quota or rate error | Daily limit | Wait and rerun the same command; it resumes from the JSONL and cache |
| Risk source reports `trained_in_process` | Registered model could not be loaded | Rerun step 4; check the alias `champion` exists |
| Prompt source reports `local` | Registry load failed | Rerun step 5; the graph still works with in-code prompts |
| `ResolutionTooDeep` on pip | Installing `databricks-agents` with `databricks-langchain` | Do not install `databricks-langchain` |
| `get_latest_versions` unsupported | UC registry | Use aliases and `search_model_versions` |
| Masked values where you expect real ones | Not in `admins` or `claims_role` | Expected behaviour for other users |
| Deploy aborts on endpoint count | Another custom endpoint exists | Delete the stale one, or pass `--force` |
