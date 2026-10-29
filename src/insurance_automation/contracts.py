"""Shared names and types that every layer (graph, evaluation, serving) agrees on."""
from dataclasses import dataclass, field
from typing import Literal

Route = Literal['analytics', 'policy', 'risk', 'claim_decision', 'refuse']
ROUTES = ('analytics', 'policy', 'risk', 'claim_decision', 'refuse')

TOOL_RUN_SQL = 'run_sql'
TOOL_RETRIEVE_POLICY = 'retrieve_policy'
TOOL_CHECK_COVERAGE = 'check_coverage'
TOOL_SCREEN_FRAUD = 'screen_fraud'
TOOL_SCORE_RISK = 'score_risk'
TOOL_NAMES = (
    TOOL_RUN_SQL, TOOL_RETRIEVE_POLICY, TOOL_CHECK_COVERAGE, TOOL_SCREEN_FRAUD, TOOL_SCORE_RISK,
)

ApprovalStatus = Literal['not_required', 'pending', 'approved', 'rejected', 'edited']
Authority = Literal['auto', 'adjuster', 'senior_adjuster', 'manager', 'siu']


@dataclass
class AgentOutput:
    """What one graph run produced, in the form the evaluation scorers consume."""

    answer: str
    route: str
    tools_called: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)  # clause/doc ids named in the answer
    hit_ids: list[str] = field(default_factory=list)  # clause/doc ids actually retrieved or checked
    sql: str | None = None
    rows: list[dict] = field(default_factory=list)
    cost_usd: float = 0.0
    latency_s: float = 0.0
    approval_status: str = 'not_required'
    required_authority: str | None = None
    fraud_referred: bool | None = None
