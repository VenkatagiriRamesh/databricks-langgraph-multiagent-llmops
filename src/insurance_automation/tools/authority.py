"""Claims authority matrix (see policy doc AUTH-01)."""
from typing import Literal

Authority = Literal['auto', 'adjuster', 'senior_adjuster', 'manager', 'siu']
AUTO_LIMIT = 2000
ADJUSTER_LIMIT = 10000
SENIOR_LIMIT = 25000


def required_authority(amount: float, siu_referral: bool) -> Authority:
    if amount < 0:
        raise ValueError('amount must be non-negative')
    if siu_referral:
        return 'siu'
    if amount < AUTO_LIMIT:
        return 'auto'
    if amount <= ADJUSTER_LIMIT:
        return 'adjuster'
    if amount <= SENIOR_LIMIT:
        return 'senior_adjuster'
    return 'manager'
