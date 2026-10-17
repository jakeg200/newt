"""The statistics behind graduation, in one place.

Graduation is the claim: on items like these, among the cases the agent chooses to handle, it
disagrees with its mentor less than α of the time, with 95% confidence. The bound is one-sided
Clopper–Pearson: UCB95(k, n) = Beta⁻¹(0.95; k + 1, n − k), with k errors in n cases.

Known answers at α = 2%: zero errors needs 149 cases, one error 236, two errors 313.
"""

from dataclasses import dataclass

from scipy.stats import beta


def ucb95(k: int, n: int) -> float:
    """Upper 95% bound on the error rate after k errors in n cases."""
    if n <= 0:
        return 1.0
    if k >= n:
        return 1.0
    return float(beta.ppf(0.95, k + 1, n - k))


def lcb95(k: int, n: int) -> float:
    """Lower 95% bound on the error rate: how bad it is at least, given k errors in n."""
    if n <= 0 or k <= 0:
        return 0.0
    return float(beta.ppf(0.05, k, n - k + 1))


def cases_needed(alpha: float, errors: int = 0) -> int:
    """Smallest n for which `errors` errors still keep the upper bound at or under α."""
    lo, hi = errors + 1, errors + 2
    while ucb95(errors, hi) > alpha:
        lo, hi = hi, hi * 2
    while lo < hi:  # first n with ucb <= alpha
        mid = (lo + hi) // 2
        if ucb95(errors, mid) <= alpha:
            hi = mid
        else:
            lo = mid + 1
    return lo


@dataclass
class Threshold:
    tau: float | None  # None: no threshold meets the bar
    n_above: int
    errors_above: int
    ucb: float
    coverage: float  # share of cases at or above tau
    total: int


def choose_tau(scores: list[float], errors: list[bool], alpha: float) -> Threshold:
    """The lowest confidence threshold τ such that, among cases scoring at least τ, the upper
    bound on the error rate is at most α. Lowest τ means the most coverage that's still safe.
    When no τ qualifies, report the best (lowest-bound) one so people can see how far off it is."""
    pairs = sorted(zip(scores, errors), key=lambda p: -p[0])
    total = len(pairs)
    if not pairs:
        return Threshold(None, 0, 0, 1.0, 0.0, 0)
    qualifying: Threshold | None = None
    closest: Threshold | None = None
    k = i = 0
    while i < total:
        tau = pairs[i][0]
        while i < total and pairs[i][0] == tau:  # ties go in together
            k += pairs[i][1]
            i += 1
        candidate = Threshold(tau, i, k, ucb95(k, i), i / total, total)
        if candidate.ucb <= alpha:
            qualifying = candidate  # scanning downwards, so the last one found is the lowest tau
        if closest is None or candidate.ucb < closest.ucb:
            closest = candidate
    if qualifying:
        return qualifying
    assert closest is not None
    return Threshold(None, closest.n_above, closest.errors_above, closest.ucb, closest.coverage, total)
