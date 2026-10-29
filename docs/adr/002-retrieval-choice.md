# ADR-002: In-process TF-IDF retrieval for policy clauses

Status: accepted. Date: 2026-10-29.

Context: The policy corpus is 17 short clauses with stable ids (COV-01, WAIT-01 and so on). Answers must cite clause ids that were actually retrieved. Free Edition has quota limits, and the plan listed Vector Search quota as an unverified risk (R4) with in-process similarity as the fallback.

Decision: Retrieve with TF-IDF cosine similarity computed in process (`tools/retrieval.py`): lowercase tokens, light suffix stripping, stop words, title weighted twice, top 3 hits, empty result when no query term overlaps. The clause table is loaded once per process.

Consequences:
- No embedding calls, no index to maintain, no quota use; behaviour is deterministic and unit-testable.
- An empty result produces the explicit "No relevant provision found" evidence, so the writer has nothing to cite.
- Purely lexical matching misses paraphrases with no shared terms. At 17 clauses this is acceptable; it would not scale to a large corpus.
- Retriever recall@k and MRR are not measured in this repository. Hybrid retrieval with reranking is roadmap and not built.
- Vector Search was not tried on this workspace, so its availability is unverified.
