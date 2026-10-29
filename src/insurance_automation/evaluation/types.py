"""Golden evaluation item schema."""
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class GoldenItem:
    id: str
    question: str
    expected_route: str
    expected_tools: list[str]
    reference_answer: str
    reference_sql: str | None
    reference_rows: list[dict] | None
    must_cite: bool
    expected_citations: list[str]
    safety_case: bool
    forbidden_phrases: list[str] = field(default_factory=list)
    expected_authority: str | None = None
    expected_fraud_referral: bool | None = None
    claim_id: str | None = None
    split: Literal['dev', 'heldout'] = 'dev'
