"""What does it cost a battery to help Energinet? Rules in opportunity/RULES.md, fixed before this was run.

Each day one linear program picks the day-ahead plan and the capacity held for FCR, aFRR up and mFRR up, decided at
07:30 the day before on the forecast and the day before's reserve prices, then paid at the real prices.
Writes opportunity/results/daily.csv, hourly.csv and summary.csv
    python opportunity/opportunity.py
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.optimize import Bounds, LinearConstraint, milp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from battery import SETUP  # noqa: E402
from costs import costs  # noqa: E402
from data import load_all  # noqa: E402
from reserves import API, MARKETS, nw_t  # noqa: E402

OUT = Path(__file__).parent / "results"
PRODUCTS = ["FCR", "aFRR up", "mFRR up"]
C = costs()


def reserve_prices():
    """€ per MW and hour in each reserve market, by danish date and hour (hourly mean where the market is finer)."""
    out = []
    for market, (name, time_col, price, dk1) in MARKETS.items():
        params = {"start": "2025-10-01", "end": "now+P2D", "limit": 0, "sort": f"{time_col} ASC"}
        if dk1:
            params["filter"] = '{"PriceArea":["DK1"]}'
        for attempt in range(5):
            r = requests.get(API + name, params=params, timeout=120)
            if r.status_code != 429:
                break
            time.sleep(60 * (attempt + 1))
        r.raise_for_status()
        d = pd.DataFrame(r.json()["records"])
        print(market, len(d), "rows,", d[time_col].min(), "to", d[time_col].max(),
              "| rows per day lately:", d.tail(2000).groupby(pd.to_datetime(d.tail(2000)[time_col]).dt.date).size().median())
        t = pd.to_datetime(d[time_col], utc=True).dt.tz_convert("Europe/Copenhagen")
        d = pd.DataFrame({"date": t.dt.tz_localize(None).dt.normalize(), "hour": t.dt.hour, market: d[price]})
        out.append(d.groupby(["date", "hour"])[market].mean())
        time.sleep(5)
    return pd.concat(out, axis=1).reset_index()


def plan(price, res, force=None, cyclic=True, setup=SETUP, c=C):
    """Day-ahead plan and capacity per hour that earn the most at day-ahead `price` and reserve prices `res`
    (24 x 3, € per MW and hour). force=(product, hour) holds exactly 1 MW of that product in that hour and nothing
    else. Returns (net sale per hour, capacity 24 x 3)."""
    n, k = len(price), len(PRODUCTS)
    eff, cap, P = np.sqrt(setup["eff_rt"]), setup["cap_mwh"], setup["power_mw"]
    ch, dis, s, u = (np.arange(n) + i * n for i in range(4))
    r = 4 * n + np.arange(n * k).reshape(n, k)   # capacity, hour x product
    s0 = 4 * n + n * k                            # charge at the start of the day
    nv = s0 + 1
    rows, lo, hi = [], [], []

    def add(terms, a, b):
        row = np.zeros(nv)
        for i, v in terms:
            row[i] += v
        rows.append(row); lo.append(a); hi.append(b)

    F, A, M = 0, 1, 2
    for h in range(n):
        prev = (s[h - 1], 1) if h else (s0, 1)
        add([(s[h], 1), (ch[h], -eff), (dis[h], 1 / eff), (prev[0], -1)], 0, 0)
        add([(ch[h], 1), (u[h], -P)], -np.inf, 0)
        add([(dis[h], 1), (u[h], P)], -np.inf, P)
        add([(dis[h], 1), (r[h, F], 1), (r[h, A], 1), (r[h, M], 1)], -np.inf, P)   # power left for discharging
        add([(ch[h], 1), (r[h, F], 1)], -np.inf, P)                                # and for charging (fcr)
        # charge to deliver up for the full hour (fcr 15 minutes), after this hour's own sale
        add([prev, (dis[h], -1 / eff), (r[h, A], -1 / eff), (r[h, M], -1 / eff), (r[h, F], -0.25 / eff)], 0, np.inf)
        # room to take in 15 minutes of fcr down
        add([prev, (ch[h], eff), (r[h, F], 0.25 * eff)], -np.inf, cap)
    add([(dis[h], 1 / eff) for h in range(n)], -np.inf, cap * setup["max_cycle"])
    if cyclic:
        add([(s[n - 1], 1), (s0, -1)], 0, np.inf)
    else:
        add([(s0, 1)], 0, 0); add([(s[n - 1], 1)], 0, 0)

    lower, upper = np.zeros(nv), np.full(nv, np.inf)
    upper[s], upper[s0], upper[u], upper[r] = cap, cap, 1, P
    if force is None:
        if res is None:
            upper[r] = 0
    else:
        upper[r] = 0
        prod, hour = force
        lower[r[hour, PRODUCTS.index(prod)]] = upper[r[hour, PRODUCTS.index(prod)]] = P
    integer = np.zeros(nv); integer[u] = 1
    obj = np.zeros(nv)
    obj[ch], obj[dis] = np.asarray(price) + c["buy"], -np.asarray(price) + c["sell"]
    if res is not None:
        obj[r] = -np.nan_to_num(np.asarray(res, float))
    sol = milp(obj, constraints=LinearConstraint(np.array(rows), lo, hi), integrality=integer,
               bounds=Bounds(lower, upper), options={"mip_rel_gap": 1e-6})
    if not sol.success:
        raise RuntimeError("lp did not solve")
    return sol.x[dis] - sol.x[ch], sol.x[r]


def da_value(q, price, c=C):
    q = np.asarray(q)
    return float(np.asarray(price) @ q - c["buy"] * -q[q < 0].sum() - c["sell"] * q[q > 0].sum())


def main():
    OUT.mkdir(exist_ok=True)
    rv = pd.read_csv(ROOT / "results" / "reserves_daily.csv", parse_dates=["date"]).set_index("date")
    fc = load_all()
    res = reserve_prices()
    res.to_csv(OUT / "reserve_prices.csv", index=False)
    R = {d: g.set_index("hour").reindex(range(24))[PRODUCTS].to_numpy() for d, g in res.groupby("date")}
    days, hours = [], []
    for d, g in fc.groupby("date"):
        if d not in rv.index or len(g) != 24 or g.actual.isna().any():
            continue
        prev = d - pd.Timedelta(days=1)
        if prev not in R or d not in R or np.isnan(R[prev]).all(axis=0).any() or np.isnan(R[d]).all(axis=0).any():
            continue
        g = g.sort_values("hour")
        p_hat, p = g.ensemble.to_numpy(), g.actual.to_numpy()
        q, cap = plan(p_hat, R[prev])                       # rule 3: decided with what was known
        split = da_value(q, p) + float(np.nansum(cap * R[d]))
        q0, _ = plan(p_hat, None)                           # the same machinery with no capacity, a check
        days.append({"date": d, "day-ahead only": rv.at[d, "day-ahead"], "whole day": rv.at[d, "rule"],
                     "split day": split, "split, no capacity": da_value(q0, p),
                     **{f"MWh {k}": cap[:, i].sum() for i, k in enumerate(PRODUCTS)}})
        base = da_value(plan(p, None)[0], p)                # hindsight, as RULES says
        for h in range(24):
            lost = base - da_value(plan(p, None, force=("aFRR up", h))[0], p)
            hours.append({"date": d, "hour": h, "lost": lost, **dict(zip(PRODUCTS, R[d][h]))})
    daily = pd.DataFrame(days).set_index("date")
    hourly = pd.DataFrame(hours)
    daily.round(2).to_csv(OUT / "daily.csv")
    hourly.round(2).to_csv(OUT / "hourly.csv", index=False)

    m, t = nw_t(daily["split day"] - daily["whole day"])
    summary = pd.DataFrame([{"days": len(daily), "first": daily.index.min().date(), "last": daily.index.max().date(),
                             **daily.mean().round(1).to_dict(), "split minus whole day": round(m, 1),
                             "newey-west t": round(t, 2), "split day wins": bool(t > 2)}])
    summary.to_csv(OUT / "summary.csv", index=False)
    print(summary.T.to_string())
    print(hourly.groupby("hour")[["lost"] + PRODUCTS].mean().round(1).to_string())


if __name__ == "__main__":
    main()
