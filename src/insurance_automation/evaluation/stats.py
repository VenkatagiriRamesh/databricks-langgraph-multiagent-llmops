"""Small statistics helpers (scipy is not a dependency)."""
import math

# Two-sided 95% Student t critical values for df 1..30.
_T95 = (
    12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
    2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
    2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042,
)
_Z95 = 1.960


def mean_ci(values: list[float], confidence: float = 0.95) -> tuple[float, float, float]:
    if confidence != 0.95:
        raise ValueError('only a 95% confidence level is supported')
    if not values:
        raise ValueError('values must not be empty')
    n = len(values)
    mean = sum(values) / n
    if n == 1:
        return (values[0], values[0], values[0])
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    critical = _T95[n - 2] if n - 1 <= len(_T95) else _Z95
    half = critical * math.sqrt(variance / n)
    return (mean, mean - half, mean + half)
