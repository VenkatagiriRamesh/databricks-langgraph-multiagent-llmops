from datetime import date

import pytest

from insurance_automation.data.generate import (
    ROUND_AMOUNT_STEP,
    generate_claims,
    generate_policies,
    generate_policy_docs,
    with_applicant_ids,
)


@pytest.fixture
def applicants():
    rows = [
        {'age': 30 + i % 30, 'sex': 'male' if i % 2 else 'female', 'bmi': 22.0 + i % 10,
         'children': i % 4, 'smoker': 'yes' if i % 5 == 0 else 'no',
         'region': ['northeast', 'southeast', 'southwest', 'northwest'][i % 4],
         'charges': 3000.0 + 250 * i}
        for i in range(200)
    ]
    return with_applicant_ids(rows)


@pytest.fixture
def policies(applicants):
    return generate_policies(applicants, seed=7)


def test_applicant_ids_are_unique_and_stable(applicants):
    ids = [a['applicant_id'] for a in applicants]
    assert len(set(ids)) == len(ids)
    assert ids[0] == 'A0000'


def test_one_policy_per_applicant_with_valid_terms(applicants, policies):
    assert len(policies) == len(applicants)
    for p in policies:
        assert p['deductible'] in (500, 1000, 2500)
        assert p['coverage_limit'] in (50000, 100000, 250000)
        assert p['waiting_period_days'] == 30


def test_generate_claims_is_deterministic_for_seed(policies):
    assert generate_claims(policies, n=100, seed=3) == generate_claims(policies, n=100, seed=3)


def test_generate_claims_differs_for_other_seed(policies):
    assert generate_claims(policies, n=100, seed=3) != generate_claims(policies, n=100, seed=4)


def test_claims_reference_existing_policies(policies):
    policy_ids = {p['policy_id'] for p in policies}
    claims = generate_claims(policies, n=150, seed=1)
    assert len(claims) == 150
    assert {c['policy_id'] for c in claims} <= policy_ids


def test_claim_amounts_positive_and_status_valid(policies):
    for c in generate_claims(policies, n=150, seed=1):
        assert c['amount'] > 0
        assert c['status'] in {'open', 'approved', 'denied', 'review'}
        assert date.fromisoformat(c['reported_date']) >= date.fromisoformat(c['loss_date'])


def test_seeded_fraud_rate_is_between_five_and_twelve_percent(policies):
    claims = generate_claims(policies, n=1000, seed=1)
    rate = sum(c['seeded_fraud'] for c in claims) / len(claims)
    assert 0.05 <= rate <= 0.12


def test_every_seeded_fraud_claim_shows_an_indicator(policies):
    by_policy = {p['policy_id']: p for p in policies}
    for c in generate_claims(policies, n=1000, seed=1):
        if not c['seeded_fraud']:
            continue
        p = by_policy[c['policy_id']]
        lag = (date.fromisoformat(c['reported_date']) - date.fromisoformat(c['loss_date'])).days
        since_inception = (
            date.fromisoformat(c['loss_date']) - date.fromisoformat(p['inception_date'])
        ).days
        assert (
            lag > 45
            or since_inception <= 30
            or c['amount'] % ROUND_AMOUNT_STEP == 0
            or c['amount'] in (1990.0, 9900.0, 24900.0)
        )


def test_some_legit_claims_fall_inside_waiting_period(policies):
    by_policy = {p['policy_id']: p for p in policies}
    inside = [
        c for c in generate_claims(policies, n=1000, seed=1)
        if not c['seeded_fraud']
        and (date.fromisoformat(c['loss_date'])
             - date.fromisoformat(by_policy[c['policy_id']]['inception_date'])).days
        < by_policy[c['policy_id']]['waiting_period_days']
    ]
    assert len(inside) >= 10


def test_injection_fixture_present(policies):
    injected = [c for c in generate_claims(policies, n=300, seed=1) if c['has_injection']]
    assert len(injected) >= 3
    assert all('ignore' in c['adjuster_notes'].lower() for c in injected)


def test_policy_docs_have_unique_ids_and_nonempty_body():
    docs = generate_policy_docs()
    ids = [d['doc_id'] for d in docs]
    assert len(set(ids)) == len(ids) and len(docs) >= 15
    assert all(d['body'].strip() and d['title'].strip() for d in docs)


def test_policy_docs_cover_every_clause_used_by_policies(policies):
    clause_ids = {d['doc_id'] for d in generate_policy_docs()}
    used = {c for p in policies for c in p['exclusions'].split('|') if c}
    assert used <= clause_ids


def test_some_legit_claims_are_reported_late(policies):
    late = [
        c for c in generate_claims(policies, n=1000, seed=1)
        if not c['seeded_fraud']
        and (date.fromisoformat(c['reported_date']) - date.fromisoformat(c['loss_date'])).days > 45
    ]
    assert len(late) >= 10


def test_some_fraud_claims_have_benign_notes(policies):
    benign = [
        c for c in generate_claims(policies, n=1000, seed=1)
        if c['seeded_fraud'] and not c['has_injection']
        and 'could not' not in c['adjuster_notes'] and 'differ' not in c['adjuster_notes']
    ]
    assert len(benign) >= 10
