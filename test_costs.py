import numpy as np
from battery import battery_schedule
from costs import cost_of, costs

PRICE = np.r_[np.full(12, 40.0), np.full(6, 60.0), np.full(6, 90.0)]


def test_zero_costs_change_nothing():
    zero = {"buy": 0.0, "sell": 0.0}
    assert np.allclose(battery_schedule(PRICE, costs=zero), battery_schedule(PRICE))


def test_no_trade_when_wear_eats_the_spread():
    assert np.allclose(battery_schedule(PRICE, costs=costs(wear=60)), 0)


def test_cost_of_a_plan():
    q = np.zeros(24)
    q[2], q[20] = -1.0, 0.9
    c = {"buy": 1.0, "sell": 10.0}
    assert np.isclose(cost_of(q, c), 1.0 + 9.0)
