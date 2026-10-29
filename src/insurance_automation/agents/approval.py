from langgraph.types import interrupt

from insurance_automation.agents.state import ClaimsState

REJECTED_ANSWER = 'The proposed decision was rejected by the reviewer. No claim action was taken.'


def needs_approval(state: ClaimsState) -> bool:
    """Human approval is required for every claim decision above the auto-settle authority."""
    authority = state.get('authority')
    return authority is not None and authority != 'auto'


def approval_gate(state: ClaimsState) -> dict:
    if not needs_approval(state):
        return {'approval_status': 'not_required', 'answer': state.get('draft', '')}
    fraud = state.get('fraud') or {}
    risk = state.get('risk') or {}
    referred = bool(fraud.get('refer_to_siu'))
    coverage = state.get('coverage') or {}
    denial = coverage.get('covered') is False
    if referred:
        proposed = 'refer_to_siu'
    else:
        proposed = 'deny_claim' if denial else 'approve_payment'
    resume_value = interrupt({
        'claim_id': state.get('claim_id'),
        'required_authority': state['authority'],
        'proposed_decision': proposed,
        'approve_means': 'confirm_denial' if proposed == 'deny_claim' else proposed,
        'payable_amount': (state.get('coverage') or {}).get('payable_amount', 0.0),
        'fraud_flags': [f['code'] for f in fraud.get('flags', [])],
        'reason_codes': [r['feature'] for r in risk.get('reason_codes', [])],
    })
    decision = resume_value.get('decision')
    role, claim_id = state['authority'], state.get('claim_id')
    if decision == 'approve' and proposed == 'deny_claim':
        answer = f'{state.get("draft", "")}\n\nDecision: DENIAL CONFIRMED by {role} for claim {claim_id}.'
        return {'approval_status': 'approved', 'answer': answer}
    if decision == 'approve':
        amount = float((state.get('coverage') or {}).get('payable_amount', 0.0))
        answer = (
            f'{state.get("draft", "")}\n\nDecision: APPROVED by {role} for claim {claim_id}; '
            f'payable {amount:.2f}.'
        )
        return {'approval_status': 'approved', 'answer': answer}
    if decision == 'edit':
        answer = f'{resume_value.get("edit_text", "")}\n\nDecision: EDITED by {role}.'
        return {'approval_status': 'edited', 'answer': answer}
    answer = f'{REJECTED_ANSWER} Claim {claim_id}, rejected by {role}.'
    return {'approval_status': 'rejected', 'answer': answer}
