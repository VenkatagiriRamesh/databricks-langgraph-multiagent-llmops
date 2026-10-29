import pytest

from insurance_automation.tools.authority import required_authority


@pytest.mark.parametrize('amount,siu,expected', [
    (1999.99, False, 'auto'),
    (2000, False, 'adjuster'),
    (10000, False, 'adjuster'),
    (10001, False, 'senior_adjuster'),
    (25000, False, 'senior_adjuster'),
    (25001, False, 'manager'),
    (50, True, 'siu'),
    (90000, True, 'siu'),
])
def test_required_authority_boundaries(amount, siu, expected):
    assert required_authority(amount, siu) == expected


def test_required_authority_rejects_negative_amount():
    with pytest.raises(ValueError):
        required_authority(-1, False)
