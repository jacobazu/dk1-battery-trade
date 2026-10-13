"""Battery plan for one day, same LP as R/battery.R."""
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

SETUP = {"cap_mwh": 2, "power_mw": 1, "eff_rt": 0.9, "max_cycle": 1}
ALPHA = 0.05  # the worst 1 in 20 scenarios


def battery_schedule(price, setup=SETUP, scenarios=None, es_floor=None, costs=None):
    """Net sale per hour in MWh (+ = sell) that earns the most at `price`."""
    price = np.asarray(price, dtype=float)
    n = len(price)
    eff = np.sqrt(setup["eff_rt"])
    cap, power = setup["cap_mwh"], setup["power_mw"]
    limit = scenarios is not None and es_floor is not None
    scen = np.asarray(scenarios, dtype=float) if limit else np.zeros((0, n))
    m = len(scen)

    # charge c, discharge d, stored s, charging flag u, and with a limit floor w and shortfalls y
    c = np.arange(n)
    d = c + n
    s = c + 2 * n
    u = c + 3 * n
    w = 4 * n
    y = 4 * n + 1 + np.arange(m)
    n_var = 4 * n + (1 + m if limit else 0)

    rows, lo, hi = [], [], []

    def add(terms, lower, upper):
        row = np.zeros(n_var)
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

    if limit:
        for k in range(m):
            # y_k >= w - revenue in scenario k
            add([(y[k], 1), (w, -1)] + [(d[h], scen[k, h]) for h in range(n)]
                + [(c[h], -scen[k, h]) for h in range(n)], 0, np.inf)
        # worst 5% average >= es_floor (rockafellar-uryasev)
        add([(w, 1)] + [(y[k], -1 / (ALPHA * m)) for k in range(m)], es_floor, np.inf)

    lower = np.zeros(n_var)
    upper = np.full(n_var, np.inf)
    upper[s] = cap
    upper[u] = 1
    integer = np.zeros(n_var)
    integer[u] = 1
    cost = np.zeros(n_var)
    cost[c] = price   # milp minimises
    cost[d] = -price
    if costs is not None:  # only trade if the spread pays the costs
        cost[c] += costs["buy"]
        cost[d] += costs["sell"]
    if limit:
        lower[w] = -np.inf

    res = milp(cost, constraints=LinearConstraint(np.array(rows), lo, hi),
               integrality=integer, bounds=Bounds(lower, upper),
               options={"mip_rel_gap": 0})
    if not res.success:
        raise RuntimeError("lp did not solve")
    return res.x[d] - res.x[c]


def battery_profit(forecast, actual, setup=SETUP):
    """Plan on the forecast, paid the actual price."""
    x = battery_schedule(forecast, setup)
    return float(np.asarray(actual, dtype=float) @ x)
