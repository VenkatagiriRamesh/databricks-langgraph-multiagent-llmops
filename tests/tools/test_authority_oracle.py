"""Independent oracle for coverage plus authority.

Every expected value below was worked out by hand from docs/GOVERNANCE.md section 2, not produced
by the code under test:
  covered claim: payable = min(amount - deductible, limit), floored at 0
                 authority from payable: < 2,000 auto; <= 10,000 adjuster;
                 <= 25,000 senior_adjuster; above manager
  denied claim:  authority from the claimed amount by the same bands (no fraud referral)
  any fraud referral on a covered claim: siu
"""
import pytest

from insurance_automation.tools.authority import required_authority
from insurance_automation.tools.coverage import check_coverage

# (label, claim_type, amount, deductible, limit, covered, fraud_referral, payable, authority)
ROWS = [
    ('just under auto band', 'inpatient', 1999.99, 0, 50000, True, False, 1999.99, 'auto'),
    ('exactly 2000 is adjuster', 'inpatient', 2000.00, 0, 50000, True, False, 2000.00, 'adjuster'),
    ('exactly 10000 is adjuster', 'inpatient', 10000.00, 0, 50000, True, False, 10000.00, 'adjuster'),
    ('10000.01 is senior', 'inpatient', 10000.01, 0, 50000, True, False, 10000.01, 'senior_adjuster'),
    ('exactly 25000 is senior', 'inpatient', 25000.00, 0, 50000, True, False, 25000.00, 'senior_adjuster'),
    ('25000.01 is manager', 'inpatient', 25000.01, 0, 50000, True, False, 25000.01, 'manager'),
    # 2500 - 600 = 1900: deductible pulls the claim down from adjuster to auto
    ('deductible crosses band down to auto', 'inpatient', 2500.00, 600, 50000, True, False, 1900.00, 'auto'),
    # 26000 - 1500 = 24500: the GOVERNANCE.md example, senior adjuster not manager
    ('deductible crosses band down to senior', 'inpatient', 26000.00, 1500, 100000, True, False,
     24500.00, 'senior_adjuster'),
    # 10500 - 1000 = 9500
    ('deductible crosses band down to adjuster', 'outpatient', 10500.00, 1000, 50000, True, False,
     9500.00, 'adjuster'),
    # 40000 - 500 = 39500 but the limit caps the payout at 20000
    ('limit caps payable into senior band', 'inpatient', 40000.00, 500, 20000, True, False,
     20000.00, 'senior_adjuster'),
    # 27000 - 1000 = 26000, limit 25000 caps it, so senior and not manager
    ('limit caps payable at 25000 exactly', 'emergency', 27000.00, 1000, 25000, True, False,
     25000.00, 'senior_adjuster'),
    # 300 - 500 is negative, floored at 0
    ('deductible exceeds amount', 'pharmacy', 300.00, 500, 5000, True, False, 0.00, 'auto'),
    ('fraud referral overrides small payable', 'inpatient', 1500.00, 0, 50000, True, True, 1500.00, 'siu'),
    ('fraud referral overrides manager band', 'inpatient', 30000.00, 0, 50000, True, True, 30000.00, 'siu'),
    # denials (cosmetic is excluded by EXC-01): authority is on the claimed amount, not the payable
    ('denial under 2000', 'cosmetic', 1500.00, 0, 50000, False, False, 0.00, 'auto'),
    ('denial of 5000', 'cosmetic', 5000.00, 400, 50000, False, False, 0.00, 'adjuster'),
    ('denial of 12000', 'cosmetic', 12000.00, 0, 50000, False, False, 0.00, 'senior_adjuster'),
    ('denial of 30000', 'cosmetic', 30000.00, 2000, 50000, False, False, 0.00, 'manager'),
]


def _claim(claim_type: str, amount: float) -> dict:
    return {'claim_type': claim_type, 'amount': amount, 'loss_date': '2024-06-01',
            'reported_date': '2024-06-10'}


def _policy(deductible: int, limit: int) -> dict:
    return {'exclusions': 'EXC-01', 'inception_date': '2023-01-01', 'waiting_period_days': 30,
            'deductible': deductible, 'coverage_limit': limit}


def test_table_is_large_enough_and_has_boundaries():
    assert len(ROWS) >= 12
    amounts = {r[2] for r in ROWS}
    assert {1999.99, 2000.0, 10000.0, 10000.01, 25000.0, 25000.01} <= amounts


@pytest.mark.parametrize(
    'label,claim_type,amount,deductible,limit,covered,referral,payable,authority',
    ROWS, ids=[r[0] for r in ROWS])
def test_oracle_row(label, claim_type, amount, deductible, limit, covered, referral, payable, authority):
    cov = check_coverage(_claim(claim_type, amount), _policy(deductible, limit))
    assert cov.covered is covered
    assert cov.payable_amount == pytest.approx(payable)
    basis = cov.payable_amount if cov.covered else amount
    got = required_authority(basis, referral if cov.covered else False)
    assert got == authority
