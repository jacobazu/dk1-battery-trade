import numpy as np
from battery import battery_schedule
from risk import ewma_vol, worst_mean

rng = np.random.default_rng(1)
PRICE = 50 + 40 * np.sin(np.arange(24) / 24 * 2 * np.pi)
SCEN = PRICE + rng.normal(0, 30, (200, 24))


def test_ewma_vol_constant_errors():
    assert np.allclose(ewma_vol(np.full((40, 24), 2.0)), 2.0)


def test_worst_mean_uses_part_of_a_scenario():
    r = np.arange(30.0)  # 5% of 30 scenarios = 1.5
    assert np.isclose(worst_mean(r), (0 + 0.5 * 1) / 1.5)


def test_limit_holds_and_costs_forecast_revenue():
    free = battery_schedule(PRICE)
    floor = worst_mean(SCEN @ free) / 2  # half the loss of the plan without a limit
    q = battery_schedule(PRICE, scenarios=SCEN, es_floor=floor)
    assert worst_mean(SCEN @ q) >= floor - 1e-6
    assert PRICE @ q < PRICE @ free


def test_loose_limit_changes_nothing():
    free = battery_schedule(PRICE)
    q = battery_schedule(PRICE, scenarios=SCEN, es_floor=-1e6)
    assert np.isclose(PRICE @ q, PRICE @ free)
