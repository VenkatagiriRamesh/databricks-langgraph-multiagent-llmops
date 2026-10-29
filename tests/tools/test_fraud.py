from insurance_automation.data.generate import (
    generate_claims,
    generate_policies,
    with_applicant_ids,
)
from insurance_automation.tools.fraud import screen_fraud


def policy(**kw):
    return {'policy_id': 'P1', 'applicant_id': 'A1', 'inception_date': '2024-01-01',
            'coverage_limit': 50000, **kw}


def claim(**kw):
    base = {'claim_id': 'C1', 'applicant_id': 'A1', 'amount': 1234.56,
            'loss_date': '2024-06-01', 'reported_date': '2024-06-03',
            'adjuster_notes': 'Claim documents received.'}
    return {**base, **kw}


def codes(screen):
    return {f.code for f in screen.flags}


def test_screen_fraud_clean_claim_has_no_flags():
    s = screen_fraud(claim(), policy(), [])
    assert s.flags == [] and s.score == 0.0 and not s.refer_to_siu


def test_screen_fraud_flags_late_report():
    s = screen_fraud(claim(reported_date='2024-08-15'), policy(), [])
    assert 'LATE_REPORT' in codes(s)


def test_screen_fraud_flags_loss_near_inception():
    s = screen_fraud(claim(loss_date='2024-01-15', reported_date='2024-01-16'), policy(), [])
    assert 'NEAR_INCEPTION' in codes(s)


def test_screen_fraud_flags_round_amount():
    assert 'ROUND_AMOUNT' in codes(screen_fraud(claim(amount=8000.0), policy(), []))


def test_screen_fraud_flags_amount_just_under_authority_limit():
    assert 'JUST_UNDER_LIMIT' in codes(screen_fraud(claim(amount=9900.0), policy(), []))


def test_screen_fraud_flags_repeat_claimant():
    history = [{'claim_id': f'H{i}', 'applicant_id': 'A1', 'loss_date': f'2024-0{i}-01'} for i in (3, 4, 5)]
    assert 'REPEAT_CLAIMANT' in codes(screen_fraud(claim(), policy(), history))


def test_screen_fraud_flags_inconsistent_notes():
    s = screen_fraud(claim(adjuster_notes='Claimant could not provide original receipts.'), policy(), [])
    assert 'INCONSISTENT_NOTES' in codes(s)


def test_screen_fraud_flags_carry_evidence_text():
    s = screen_fraud(claim(reported_date='2024-08-15'), policy(), [])
    assert all(f.evidence for f in s.flags)


def test_screen_fraud_refers_when_multiple_indicators_combine():
    s = screen_fraud(
        claim(amount=8000.0, reported_date='2024-08-15',
              adjuster_notes='Claimant could not provide original receipts.'),
        policy(), [],
    )
    assert s.refer_to_siu and 0.5 <= s.score <= 1.0


def test_screen_fraud_never_auto_denies():
    s = screen_fraud(claim(amount=8000.0, reported_date='2024-08-15'), policy(), [])
    assert not hasattr(s, 'deny') and not hasattr(s, 'decision')


def test_screen_fraud_precision_and_recall_on_seeded_labels():
    applicants = with_applicant_ids([
        {'age': 40, 'sex': 'male', 'bmi': 28.0, 'children': i % 3, 'smoker': 'no',
         'region': 'northeast', 'charges': 5000.0} for i in range(300)
    ])
    policies = generate_policies(applicants, seed=2)
    by_policy = {p['policy_id']: p for p in policies}
    claims = [c for c in generate_claims(policies, n=2000, seed=2) if not c['has_injection']]
    tp = fp = fn = 0
    for c in claims:
        referred = screen_fraud(c, by_policy[c['policy_id']], []).refer_to_siu
        tp += referred and c['seeded_fraud']
        fp += referred and not c['seeded_fraud']
        fn += (not referred) and c['seeded_fraud']
    recall = tp / (tp + fn)
    precision = tp / (tp + fp)
    assert recall >= 0.5 and precision >= 0.5
