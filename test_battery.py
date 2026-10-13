import numpy as np
from battery import SETUP, battery_schedule


def test_flat_price_means_no_trade():
    assert np.allclose(battery_schedule(np.full(24, 50.0)), 0)


def test_buys_cheap_sells_expensive():
    price = np.full(24, 50.0)
    price[3:5] = 10
    price[18:20] = 200
    x = battery_schedule(price)
    assert x[3:5].sum() < 0 and x[18:20].sum() > 0


def test_power_and_cycle_limits():
    x = battery_schedule(np.tile([0.0, 300.0], 12))
    eff = np.sqrt(SETUP["eff_rt"])
    assert np.all(np.abs(x) <= SETUP["power_mw"] + 1e-9)
    assert x[x > 0].sum() <= SETUP["cap_mwh"] * SETUP["max_cycle"] * eff + 1e-9
