"""Battery plan for one day, the same LP as R/battery.R in dk1-price-forecasting."""
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

SETUP = {"cap_mwh": 2, "power_mw": 1, "eff_rt": 0.9, "max_cycle": 1}


def battery_schedule(price, setup=SETUP):
    """Net sale per hour in MWh (+ = discharge) that maximises revenue at `price`."""
    price = np.asarray(price, dtype=float)
    n = len(price)
    eff = np.sqrt(setup["eff_rt"])
    cap, power = setup["cap_mwh"], setup["power_mw"]

    # variables: charge c, discharge d, stored s, u = 1 if charging
    c = np.arange(n)
    d = c + n
    s = c + 2 * n
    u = c + 3 * n

    rows, lo, hi = [], [], []

    def add(terms, lower, upper):
        row = np.zeros(4 * n)
        for i, coef in terms:
            row[i] = coef
        rows.append(row)
        lo.append(lower)
        hi.append(upper)

    for h in range(n):
        before = [(s[h - 1], -1)] if h > 0 else []
        add([(s[h], 1), (c[h], -eff), (d[h], 1 / eff)] + before, 0, 0)  # storage, starts empty
        add([(c[h], 1), (u[h], -power)], -np.inf, 0)                      # charge only if u = 1
        add([(d[h], 1), (u[h], power)], -np.inf, power)                   # discharge only if u = 0
    add([(s[n - 1], 1)], 0, 0)                                             # empty at end of day
    add([(d[h], 1 / eff) for h in range(n)], -np.inf, cap * setup["max_cycle"])  # cycle limit

    upper = np.concatenate([np.full(2 * n, np.inf), np.full(n, cap), np.ones(n)])
    integer = np.concatenate([np.zeros(3 * n), np.ones(n)])
    cost = np.concatenate([price, -price, np.zeros(2 * n)])  # milp minimises

    res = milp(cost, constraints=LinearConstraint(np.array(rows), lo, hi),
               integrality=integer, bounds=Bounds(0, upper),
               options={"mip_rel_gap": 0})
    if not res.success:
        raise RuntimeError("lp did not solve")
    return res.x[d] - res.x[c]


def battery_profit(forecast, actual, setup=SETUP):
    """Plan on the forecast, paid the actual price."""
    x = battery_schedule(forecast, setup)
    return float(np.asarray(actual, dtype=float) @ x)
