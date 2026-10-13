import numpy as np
from stress import stress_tests

F = np.full(24, 50.0)
F[2:4] = 10
F[18:20] = 200
Q = np.zeros(24)
Q[2:4] = -1
Q[18:20] = 0.9
NO_ERRORS = np.zeros((40, 24))


def test_without_errors_the_bad_cases_are_the_plan():
    r = stress_tests(F, Q, NO_ERRORS)
    assert np.isclose(r["Worst of the last 250 days"], F @ Q)
    assert np.isclose(r["Errors 3 times as big (worst 5%)"], F @ Q)


def test_a_peak_that_does_not_come_costs_money():
    assert stress_tests(F, Q, NO_ERRORS)["The peak doesn't come"] < F @ Q


def test_negative_midday_leaves_a_plan_idle_at_midday_alone():
    assert np.isclose(stress_tests(F, Q, NO_ERRORS)["Negative prices 11–15"], F @ Q)
