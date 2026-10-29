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
    resume_value = interrupt({
        'claim_id': state.get('claim_id'),
        'required_authority': state['authority'],
        'proposed_decision': 'refer_to_siu' if referred else 'approve_payment',
        'payable_amount': (state.get('coverage') or {}).get('payable_amount', 0.0),
        'fraud_flags': [f['code'] for f in fraud.get('flags', [])],
        'reason_codes': [r['feature'] for r in risk.get('reason_codes', [])],
    })
    decision = resume_value.get('decision')
    if decision == 'approve':
        return {'approval_status': 'approved', 'answer': state.get('draft', '')}
    if decision == 'edit':
        return {'approval_status': 'edited', 'answer': resume_value.get('edit_text', '')}
    return {'approval_status': 'rejected', 'answer': REJECTED_ANSWER}
