from insurance_automation.tools.coverage import check_coverage


def policy(**kw):
    base = {
        'policy_id': 'P1', 'inception_date': '2024-01-01', 'deductible': 1000,
        'coverage_limit': 50000, 'waiting_period_days': 30, 'exclusions': 'EXC-01|EXC-02',
    }
    return {**base, **kw}


def claim(**kw):
    base = {
        'claim_id': 'C1', 'claim_type': 'inpatient', 'amount': 5000.0,
        'loss_date': '2024-06-01', 'reported_date': '2024-06-05',
    }
    return {**base, **kw}


def test_check_coverage_applies_deductible_and_limit():
    d = check_coverage(claim(amount=5000.0), policy())
    assert d.covered and d.payable_amount == 4000.0
    assert 'COV-01' in d.clause_ids and 'DED-01' in d.clause_ids
    big = check_coverage(claim(amount=80000.0), policy(deductible=500))
    assert big.payable_amount == 50000.0


def test_check_coverage_amount_below_deductible_pays_zero():
    d = check_coverage(claim(amount=800.0), policy())
    assert d.covered and d.payable_amount == 0.0


def test_check_coverage_denies_within_waiting_period():
    d = check_coverage(claim(loss_date='2024-01-10'), policy())
    assert not d.covered and 'WAIT-01' in d.clause_ids and d.payable_amount == 0.0


def test_check_coverage_emergency_is_covered_inside_waiting_period():
    d = check_coverage(claim(claim_type='emergency', loss_date='2024-01-10'), policy())
    assert d.covered and 'COV-03' in d.clause_ids


def test_check_coverage_denies_excluded_peril_with_clause_id():
    d = check_coverage(claim(claim_type='cosmetic'), policy())
    assert not d.covered and d.clause_ids == ['EXC-01']


def test_check_coverage_peril_not_excluded_on_this_policy_is_not_denied():
    d = check_coverage(claim(claim_type='cosmetic'), policy(exclusions='EXC-02'))
    assert not d.covered or 'EXC-01' not in d.clause_ids


def test_check_coverage_notes_late_report_without_denying():
    d = check_coverage(claim(reported_date='2024-09-30'), policy())
    assert d.covered and 'RPT-01' in d.clause_ids
