import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass

from insurance_automation.agents.prompts import PromptStore
from insurance_automation.agents.state import ClaimsState
from insurance_automation.contracts import (
    ROUTES,
    TOOL_CHECK_COVERAGE,
    TOOL_RETRIEVE_POLICY,
    TOOL_RUN_SQL,
    TOOL_SCORE_RISK,
    TOOL_SCREEN_FRAUD,
)
from insurance_automation.llm.base import LLM, LedgerLike
from insurance_automation.tools.authority import required_authority
from insurance_automation.tools.coverage import check_coverage
from insurance_automation.tools.fraud import screen_fraud
from insurance_automation.tools.retrieval import PolicyHit
from insurance_automation.tools.risk_model import ReasonCode, RiskScore, describe_reason
from insurance_automation.tools.sql_guard import UnsafeSQLError, validate_select_only

CLAIM_ID = re.compile(r'C\d{5}')
APPLICANT_ID = re.compile(r'A\d{4}')
CITATION_ID = re.compile(r'[A-Z]+-\d{2}')
INJECTION = re.compile(r'ignore (all |any )?(previous|prior) instructions|approve this claim', re.IGNORECASE)
GRANTS = re.compile(r'(?<!not )(?<!n\'t )(?<!un)\b(approved?|grant(ed|s)?)\b', re.IGNORECASE)
REFUSAL_ANSWER = 'I can only help with insurance claims, policy, risk and analytics questions.'
NO_PROVISION = 'No relevant policy provision found.'
POLICY_HITS = 3


@dataclass
class Tools:
    run_query: Callable[[str], list[dict]]
    search_policy: Callable[[str, int], list[PolicyHit]]
    get_claim: Callable[[str], dict | None]
    get_policy: Callable[[str], dict | None]
    get_applicant: Callable[[str], dict | None]
    get_history: Callable[[str], list[dict]]
    score_risk: Callable[[dict], RiskScore]


@dataclass
class NodeContext:
    llm: LLM
    tools: Tools
    ledger: LedgerLike
    prompts: PromptStore
    allowed_schema: str = 'insurance_automation.curated'


def call_llm(ctx: NodeContext, node: str, prompt: str, system: str = '') -> str:
    result = ctx.llm.invoke(prompt, system=system, node=node)
    ctx.ledger.record(node, result)
    return result.text


def _called(state: ClaimsState, tool: str) -> list[str]:
    return [*state.get('tools_called', []), tool]


def supervisor(state: ClaimsState, ctx: NodeContext) -> dict:
    question = state.get('question', '')
    if not question.strip():
        return {'route': 'refuse'}
    text = call_llm(ctx, 'supervisor', question, ctx.prompts.get('supervisor'))
    word = text.strip().lower().strip('.,!"\'` \n')
    route = word if word in ROUTES else 'refuse'
    match = CLAIM_ID.search(question)
    claim_id = match.group(0) if match else None
    if route == 'claim_decision' and claim_id is None:
        route = 'refuse'
    return {'route': route, 'claim_id': claim_id}


def refuse(state: ClaimsState, ctx: NodeContext) -> dict:
    return {'answer': REFUSAL_ANSWER, 'approval_status': 'not_required'}


def sql_analyst(state: ClaimsState, ctx: NodeContext) -> dict:
    raw = call_llm(ctx, 'sql_analyst', state['question'], ctx.prompts.get('sql_analyst'))
    sql = re.sub(r'^```(?:sql)?|```$', '', raw.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()
    try:
        safe = validate_select_only(sql, ctx.allowed_schema)
    except UnsafeSQLError as err:
        return {'sql': None, 'rows': [], 'refusal_reason': f'query refused: {err}'}
    rows = ctx.tools.run_query(safe)
    return {'sql': safe, 'rows': rows, 'tools_called': _called(state, TOOL_RUN_SQL)}


def policy_rag(state: ClaimsState, ctx: NodeContext) -> dict:
    found = ctx.tools.search_policy(state['question'], POLICY_HITS)
    hits = [{'doc_id': h.doc_id, 'title': h.title, 'snippet': h.snippet} for h in found]
    return {
        'hits': hits, 'evidence_ids': [h['doc_id'] for h in hits],
        'tools_called': _called(state, TOOL_RETRIEVE_POLICY),
    }


def coverage_checker(state: ClaimsState, ctx: NodeContext) -> dict:
    claim = ctx.tools.get_claim(state['claim_id'])
    policy = ctx.tools.get_policy(claim['policy_id']) if claim else None
    if claim is None or policy is None:
        missing = {'covered': False, 'reasons': ['claim or policy record not found'],
                   'clause_ids': [], 'payable_amount': 0.0}
        return {'claim': claim, 'coverage': missing, 'authority': 'auto'}
    decision = check_coverage(claim, policy)
    update = {
        'claim': claim, 'coverage': asdict(decision),
        'tools_called': _called(state, TOOL_CHECK_COVERAGE),
        'evidence_ids': list(decision.clause_ids),
    }
    if not decision.covered:
        # A denial is authorised on the claimed amount (payable is 0); fraud referral does not apply.
        update['authority'] = required_authority(float(claim['amount']), False)
    return update


def after_coverage(state: ClaimsState) -> str:
    return 'fraud_screener' if (state.get('coverage') or {}).get('covered') else 'writer'


def fraud_screener(state: ClaimsState, ctx: NodeContext) -> dict:
    claim = state['claim']
    policy = ctx.tools.get_policy(claim['policy_id'])
    history = ctx.tools.get_history(claim['applicant_id'])
    screen = screen_fraud(claim, policy, history)
    amount = state['coverage']['payable_amount']
    return {
        'fraud': asdict(screen),
        'authority': required_authority(amount, screen.refer_to_siu),
        'tools_called': _called(state, TOOL_SCREEN_FRAUD),
    }


def risk_scorer(state: ClaimsState, ctx: NodeContext) -> dict:
    claim = state.get('claim')
    if claim:
        applicant_id = claim['applicant_id']
    else:
        match = APPLICANT_ID.search(state.get('question', ''))
        applicant_id = match.group(0) if match else None
    applicant = ctx.tools.get_applicant(applicant_id) if applicant_id else None
    if applicant is None:
        return {'risk': None, 'refusal_reason': 'applicant not found'}
    score = ctx.tools.score_risk(applicant)
    risk = asdict(score)
    risk['reason_text'] = [describe_reason(c, applicant) for c in score.reason_codes]
    return {'risk': risk, 'tools_called': _called(state, TOOL_SCORE_RISK)}


def _risk_drivers(risk: dict) -> list[str]:
    if 'reason_text' in risk:
        return risk['reason_text']
    return [describe_reason(ReasonCode(**c), {}) for c in risk.get('reason_codes', [])]


def _evidence_text(state: ClaimsState) -> str:
    parts = [f'Question: {state.get("question", "")}']
    if state.get('refusal_reason'):
        parts.append(f'Not done: {state["refusal_reason"]}')
    if state.get('sql'):
        parts.append(f'SQL: {state["sql"]}\nRows: {state.get("rows", [])}')
    if state.get('coverage'):
        c = state['coverage']
        parts.append(
            f'Coverage: covered={c["covered"]}; reasons={c["reasons"]}; '
            f'clauses={c["clause_ids"]}; payable_amount={c["payable_amount"]}'
        )
    if state.get('fraud'):
        f = state['fraud']
        parts.append(
            f'Fraud flags: {[(x["code"], x["evidence"]) for x in f["flags"]]}; '
            f'refer_to_siu={f["refer_to_siu"]}'
        )
    if state.get('risk'):
        r = state['risk']
        parts.append(f'Risk band: {r["band"]}; risk drivers: {_risk_drivers(r)}')
    if state.get('authority'):
        parts.append(f'Required authority: {state["authority"]}')
    if 'hits' in state:
        if state['hits']:
            parts.extend(f'[{h["doc_id"]}] {h["title"]}: {h["snippet"]}' for h in state['hits'])
        else:
            parts.append(NO_PROVISION)
    parts.append(f'Evidence ids: {state.get("evidence_ids", [])}')
    return '\n'.join(parts)


def writer(state: ClaimsState, ctx: NodeContext) -> dict:
    prompt = _evidence_text(state)
    retries = state.get('retries', 0)
    if state.get('critic_verdict') == 'fail':
        retries += 1
        prompt += f'\nA reviewer rejected your previous draft: {state.get("critic_reason", "")}'
    draft = call_llm(ctx, 'writer', prompt, ctx.prompts.get('writer')).strip()
    citations = list(dict.fromkeys(CITATION_ID.findall(draft)))
    return {
        'draft': draft, 'citations': citations, 'retries': retries,
        'evidence_ids': list(dict.fromkeys(state.get('evidence_ids', []))),
    }


def critic(state: ClaimsState, ctx: NodeContext) -> dict:
    draft = state.get('draft', '')
    evidence = set(state.get('evidence_ids', []))
    texts = [(state.get('claim') or {}).get('adjuster_notes', '')]
    texts += [h['snippet'] for h in state.get('hits', [])]
    flagged = any(INJECTION.search(t) for t in texts)
    problem = ''
    unknown = [c for c in state.get('citations', []) if c not in evidence]
    if unknown:
        problem = f'draft cites ids not in the evidence: {unknown}'
    elif flagged and GRANTS.search(draft):
        problem = 'draft approves a claim while the evidence contains an injected instruction'
    if problem:
        return {'critic_verdict': 'fail', 'critic_reason': problem, 'notes_flagged': flagged}
    text = call_llm(
        ctx, 'critic', f'{_evidence_text(state)}\n\nDraft:\n{draft}', ctx.prompts.get('critic'),
    )
    verdict, reason = 'pass', ''
    match = re.search(r'\{.*?\}', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            verdict = 'fail' if data.get('verdict') == 'fail' else 'pass'
            reason = str(data.get('reason', ''))
        except json.JSONDecodeError:
            pass
    return {'critic_verdict': verdict, 'critic_reason': reason, 'notes_flagged': flagged}


def escalate(state: ClaimsState, ctx: NodeContext) -> dict:
    return {'answer': ESCALATION_ANSWER, 'approval_status': 'pending'}


ESCALATION_ANSWER = (
    'I cannot give a reliable answer to this; it has been escalated for human review.'
)
