"""In-process TF-IDF retrieval over policy documents: no embeddings, no Vector Search quota."""
import math
import re
from collections import Counter
from dataclasses import dataclass

SNIPPET_CHARS = 240
_STOP = {
    'the', 'and', 'for', 'are', 'not', 'can', 'how', 'what', 'does', 'this', 'that', 'with',
    'from', 'any', 'may', 'must', 'should', 'when', 'who', 'why', 'which', 'there', 'their',
}


@dataclass(frozen=True)
class PolicyHit:
    doc_id: str
    title: str
    score: float
    snippet: str


def _stem(token: str) -> str:
    for suffix in ('ing', 'ed', 'es', 's'):
        if token.endswith(suffix) and len(token) - len(suffix) >= 4:
            return token[: -len(suffix)]
    return token


def _tokens(text: str) -> list[str]:
    return [
        _stem(t) for t in re.findall(r'[a-z0-9]+', text.lower())
        if len(t) > 2 and t not in _STOP
    ]


def retrieve_policy(query: str, docs: list[dict], k: int = 3) -> list[PolicyHit]:
    query_tokens = _tokens(query)
    if not query_tokens or not docs:
        return []
    doc_tokens = [_tokens(f'{d["title"]} {d["title"]} {d["body"]}') for d in docs]
    df = Counter(t for tokens in doc_tokens for t in set(tokens))
    n = len(docs)

    def vector(tokens: list[str]) -> dict[str, float]:
        return {t: c * (math.log((1 + n) / (1 + df.get(t, 0))) + 1) for t, c in Counter(tokens).items()}

    q = vector(query_tokens)
    q_norm = math.sqrt(sum(v * v for v in q.values()))
    scored = []
    for doc, tokens in zip(docs, doc_tokens):
        d = vector(tokens)
        dot = sum(q[t] * d[t] for t in q if t in d)
        if dot > 0:
            d_norm = math.sqrt(sum(v * v for v in d.values()))
            scored.append((dot / (q_norm * d_norm), doc))
    scored.sort(key=lambda s: (-s[0], s[1]['doc_id']))
    return [
        PolicyHit(doc['doc_id'], doc['title'], round(score, 4), doc['body'][:SNIPPET_CHARS])
        for score, doc in scored[:k]
    ]
