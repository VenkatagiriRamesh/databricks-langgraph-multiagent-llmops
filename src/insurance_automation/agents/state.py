from typing import TypedDict


class ClaimsState(TypedDict, total=False):
    question: str
    route: str
    claim_id: str | None
    claim: dict | None  # loaded claim record, kept so the critic can inspect adjuster notes
    sql: str | None
    rows: list[dict]
    refusal_reason: str | None
    hits: list[dict]
    coverage: dict | None
    fraud: dict | None
    risk: dict | None
    authority: str | None
    draft: str
    critic_verdict: str
    critic_reason: str
    retries: int
    approval_status: str
    answer: str
    citations: list[str]
    evidence_ids: list[str]
    tools_called: list[str]
    notes_flagged: bool
    lookup_error: str | None  # set when the claim or its policy record could not be loaded
