from langgraph.types import interrupt

from insurance_automation.agents.state import ClaimsState

REJECTED_ANSWER = 'The proposed decision was rejected by the reviewer. No claim action was taken.'


def needs_approval(state: ClaimsState) -> bool:
    """Human approval is required for every claim decision above the auto-settle authority."""
    authority = state.get('authority')
    return authority is not None and authority != 'auto'


def _auto_decision_line(state: ClaimsState) -> str | None:
    """Deterministic outcome for a claim decided under the auto authority, or None."""
    coverage = state.get('coverage')
    if state.get('authority') != 'auto' or not coverage or 'covered' not in coverage:
        return None
    claim_id = state.get('claim_id')
    if coverage['covered']:
        return (
            f'Decision: AUTO-SETTLED claim {claim_id}; '
            f'payable {float(coverage.get("payable_amount", 0.0)):.2f}; '
            'no human sign-off required (below 2,000).'
        )
    clauses = ', '.join(coverage.get('clause_ids') or [])
    return (
        f'Decision: AUTO-DENIED claim {claim_id} under {clauses}; '
        'no human sign-off required (below 2,000).'
    )


def approval_gate(state: ClaimsState) -> dict:
    if state.get('lookup_error') == 'claim_not_found':
        return {'approval_status': 'not_required',
                'answer': f'Claim {state.get("claim_id")} was not found.'}
    if state.get('lookup_error'):
        return {'approval_status': 'not_required',
                'answer': f'Claim {state.get("claim_id")} could not be assessed: '
                          f'{state["lookup_error"]}.'}
    if not needs_approval(state):
        draft = state.get('draft', '')
        line = _auto_decision_line(state)
        return {'approval_status': 'not_required',
                'answer': f'{draft}\n\n{line}' if line else draft}
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
        'approve_means': {'deny_claim': 'confirm_denial', 'refer_to_siu': 'confirm_referral'}.get(
            proposed, proposed),
        'payable_amount': (state.get('coverage') or {}).get('payable_amount', 0.0),
        'fraud_flags': [f['code'] for f in fraud.get('flags', [])],
        'reason_codes': [r['feature'] for r in risk.get('reason_codes', [])],
    })
    decision = resume_value.get('decision')
    role, claim_id = state['authority'], state.get('claim_id')
    if proposed == 'refer_to_siu' and decision == 'approve':
        answer = (
            f'{state.get("draft", "")}\n\nDecision: REFERRAL TO SIU CONFIRMED for claim '
            f'{claim_id}; no payment authorised.'
        )
        return {'approval_status': 'approved', 'answer': answer}
    if proposed == 'refer_to_siu' and decision == 'reject':
        answer = (
            f'{state.get("draft", "")}\n\nDecision: SIU REFERRAL REJECTED by {role} for claim '
            f'{claim_id}; return to claims handling.'
        )
        return {'approval_status': 'rejected', 'answer': answer}
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
