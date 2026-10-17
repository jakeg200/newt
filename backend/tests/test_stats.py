"""The brief's numbers, reproduced (M5 acceptance)."""

import pytest

from app.eval.stats import cases_needed, choose_tau, lcb95, ucb95


@pytest.mark.parametrize(("errors", "needed"), [(0, 149), (1, 236), (2, 313)])
def test_cases_needed_at_two_percent(errors, needed):
    assert cases_needed(0.02, errors) == needed
    assert ucb95(errors, needed) <= 0.02 < ucb95(errors, needed - 1)


def test_fifty_clean_audits_cant_prove_two_percent():
    assert ucb95(0, 50) == pytest.approx(0.058, abs=0.001)  # why a 50-audit upper bound can't drive demotion


def test_four_errors_in_fifty_audits_means_worse_than_two_percent():
    assert lcb95(4, 50) > 0.02 > lcb95(3, 50)


def test_bounds_edges():
    assert ucb95(0, 0) == 1.0 and ucb95(5, 5) == 1.0 and lcb95(0, 10) == 0.0


def test_choose_tau_takes_the_lowest_safe_threshold():
    # 200 confident cases, none wrong; 100 less confident with 10% errors
    scores = [0.95] * 200 + [0.6] * 100
    errors = [False] * 200 + [i % 10 == 0 for i in range(100)]
    t = choose_tau(scores, errors, 0.02)
    assert t.tau == 0.95 and t.n_above == 200 and t.errors_above == 0
    assert t.coverage == pytest.approx(200 / 300) and t.ucb <= 0.02
    loose = choose_tau(scores, errors, 0.06)
    assert loose.tau == 0.6 and loose.coverage == 1.0


def test_no_safe_threshold_reports_how_close():
    t = choose_tau([0.9] * 100, [i < 3 for i in range(100)], 0.02)
    assert t.tau is None and t.n_above == 100 and t.errors_above == 3 and t.ucb > 0.02
