import pytest

from insurance_automation.evaluation.stats import mean_ci


def test_mean_ci_known_values():
    mean, low, high = mean_ci([1, 2, 3])
    assert mean == 2.0
    assert 2.0 - low == pytest.approx(high - 2.0)
    assert high - 2.0 == pytest.approx(2.484, abs=0.01)


def test_mean_ci_single_value():
    assert mean_ci([0.7]) == (0.7, 0.7, 0.7)


def test_mean_ci_empty_raises():
    with pytest.raises(ValueError):
        mean_ci([])


def test_mean_ci_other_confidence_raises():
    with pytest.raises(ValueError):
        mean_ci([1, 2], confidence=0.9)


def test_mean_ci_large_sample_uses_normal():
    _, low, high = mean_ci([0.0, 1.0] * 50)
    assert 0.0 < low < 0.5 < high < 1.0
