# ADR-001: Free Edition platform constraints

Status: accepted. Date: 2026-10-29. Workspace: Databricks Free Edition (serverless only).
Evidence: `scripts/spike_checks.py` run against the workspace, MLflow 3.17.2, LangGraph 1.2.18.

| Capability | Result | Decision |
|---|---|---|
| Catalog, schema creation via SQL warehouse | Works | Create `insurance_automation` catalog and schemas |
| Foundation Model call (`databricks-meta-llama-3-3-70b-instruct`) | Works (OpenAI-compatible client) | Default model; Llama 3.1 8B available as a cheap router model |
| MLflow Prompt Registry in Unity Catalog | Works (register and load) | Use `RegistryPromptStore` |
| UC model registration and `champion` alias | Works. `get_latest_versions` is unsupported for UC; use `search_model_versions` and aliases | Aliases only |
| `mlflow.genai.evaluate` with custom scorers | Works | Not used as the harness; see the next row and ADR-004 |
| Built-in judges (Safety, Guidelines) | Run without error; returned empty metrics in the probe, so scoring is unconfirmed | The evaluation harness is custom (`evaluation/harness.py`) with direct LLM-as-judge through `CachedLLM` |
| Persistent LangGraph checkpointer (Lakebase) | Not available: 0 Lakebase instances | In-memory `MemorySaver` plus a Delta decision log for approvals (fallback R1) |
| `databricks-agents` (`agents.deploy`) | Package installs on its own; installing it together with databricks-langchain made pip fail with ResolutionTooDeep | Install `databricks-agents` only; skip `databricks-langchain` |
| Custom serving endpoints | None exist; full endpoint quota is free | Deploy one scale-to-zero endpoint |
| Auth | CLI OAuth token refresh is intermittently unreliable under concurrency (exit status 45); MLflow trace export then falls back to legacy auth and logs 401 | Long runs export a fresh `DATABRICKS_TOKEN` from `databricks auth token` first |
| Tracing API | `mlflow.get_last_active_trace_id` exists in 3.17; `get_last_active_trace` does not | Tests use the trace id API |

Consequences: approval resume works inside one endpoint process via the two-call pattern keyed by run id, with decisions persisted to a Delta table so they survive restarts.
