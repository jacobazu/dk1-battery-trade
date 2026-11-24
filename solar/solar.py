"""Solar panel with the battery as its buffer, rules in solar/RULES.md (fixed 24 Nov 2026, before this was run).

A: no battery, solar forecast sold day-ahead, errors at the imbalance price.
B: solar and battery, day-ahead only, with the buffer.
C: B plus energinet's reserves: capacity at 07:15 the day before, then the day-ahead plan at 10:30.
Writes solar/results/daily.csv, hourly.csv, summary.csv
    python solar/solar.py
"""
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.optimize import Bounds, LinearConstraint, milp

HERE = Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "opportunity"))
from battery import SETUP  # noqa: E402
from costs import FEE, costs  # noqa: E402
from data import load_all  # noqa: E402
from opportunity import PRODUCTS, reserve_prices  # noqa: E402
from reserves import nw_t  # noqa: E402

OUT = HERE / "results"
SOLAR = "https://raw.githubusercontent.com/jacobazu/dk1-renewables-forecasting/main/results/final_forecasts.csv"
GRID = 1.0                       # MW, shared by panel and battery
FIRST, SCORED_FROM = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-01")
C = costs()
KEEP = 1000.0                    # € per MW of buffer: the buffer comes before any trade


def solar():
    """1 MWp shaped like dk1's solar: forecast and output divided by the fleet size, by danish date and hour"""
    s = pd.read_csv(SOLAR)
    s = s[s["target"] == "solar"]
    t = pd.to_datetime(s["time"]).dt.tz_localize("UTC").dt.tz_convert("Europe/Copenhagen")
    d = pd.DataFrame({"date": t.dt.tz_localize(None).dt.normalize(), "hour": t.dt.hour,
                      "fc": (s["forecast"] / s["cap"]).clip(0, 1).values, "act": (s["actual"] / s["cap"]).clip(0, 1).values})
    return d.groupby(["date", "hour"], as_index=False).mean()


def imbalance_prices():
    """dk1 imbalance price, € per MWh, hourly mean of the quarter-hours. saved, as the reserve prices are"""
    f = OUT / "imbalance_prices.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["date"])
    out = []
    for a in pd.date_range(FIRST - pd.Timedelta(days=1), "2026-10-13", freq="MS"):
        b = a + pd.offsets.MonthBegin(1)
        for attempt in range(5):
            r = requests.get("https://api.energidataservice.dk/dataset/ImbalancePrice", timeout=120,
                             params={"start": f"{a:%Y-%m-%d}", "end": f"{b:%Y-%m-%d}", "limit": 0,
                                     "filter": '{"PriceArea":["DK1"]}'})
            if r.status_code != 429:
                break
            time.sleep(60 * (attempt + 1))
        r.raise_for_status()
        out.append(pd.DataFrame(r.json()["records"]))
        time.sleep(3)
    d = pd.concat(out)
    t = pd.to_datetime(d["TimeDK"])
    d = pd.DataFrame({"date": t.dt.normalize(), "hour": t.dt.hour, "imbalance": d["ImbalancePriceEUR"]})
    d = d.groupby(["date", "hour"], as_index=False)["imbalance"].mean()
    OUT.mkdir(exist_ok=True)
    d.to_csv(f, index=False, date_format="%Y-%m-%d")
    return d


def buffer(err, fc):
    """room (up) and charge (down) per hour: the 1 in 20 worst error for that hour, never more than the panel can
    miss by. err: days x 24 errors as a share of the fleet"""
    up = np.clip(np.nanquantile(err, 0.95, axis=0), 0, None)
    dn = np.clip(-np.nanquantile(err, 0.05, axis=0), 0, None)
    return np.minimum(up, 1 - fc), np.minimum(dn, fc)


def plan(price, fc, up, dn, res=None, fix=None, setup=SETUP, c=C):
    """the day for panel and battery: solar sold, battery bought and sold, capacity, and the buffer kept.
    returns dict of hourly arrays"""
    n, k = 24, len(PRODUCTS)
    eff, cap, P = np.sqrt(setup["eff_rt"]), setup["cap_mwh"], setup["power_mw"]
    sol, ch, dis, s, u, bu, bd = (np.arange(n) + i * n for i in range(7))
    r = 7 * n + np.arange(n * k).reshape(n, k)
    s0 = 7 * n + n * k
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
        # battery power: up for energinet and the buffer's shortfall on top of the sale, down likewise
        add([(dis[h], 1), (r[h, F], 1), (r[h, A], 1), (r[h, M], 1), (bd[h], 1)], -np.inf, P)
        add([(ch[h], 1), (r[h, F], 1), (bu[h], 1)], -np.inf, P)
        # charge to deliver for the full hour (fcr 15 minutes) and the shortfall; room for fcr down and the surplus
        add([prev, (dis[h], -1 / eff), (r[h, A], -1 / eff), (r[h, M], -1 / eff), (r[h, F], -0.25 / eff),
             (bd[h], -1 / eff)], 0, np.inf)
        add([prev, (ch[h], eff), (r[h, F], 0.25 * eff), (bu[h], eff)], -np.inf, cap)
        # the grid connection, out and in, with energinet's power on top
        add([(sol[h], 1), (dis[h], 1), (ch[h], -1), (r[h, F], 1), (r[h, A], 1), (r[h, M], 1)], -np.inf, GRID)
        add([(ch[h], 1), (sol[h], -1), (dis[h], -1), (r[h, F], 1)], -np.inf, GRID)
    add([(dis[h], 1 / eff) for h in range(n)], -np.inf, cap * setup["max_cycle"])
    add([(s[n - 1], 1), (s0, -1)], 0, np.inf)

    lower, upper = np.zeros(nv), np.full(nv, np.inf)
    upper[sol], upper[s], upper[s0], upper[u], upper[r] = fc, cap, cap, 1, P
    upper[bu], upper[bd] = up, dn
    if res is None:
        upper[r] = 0
    if fix is not None:
        lower[r] = upper[r] = np.asarray(fix)
    integer = np.zeros(nv); integer[u] = 1
    obj = np.zeros(nv)
    obj[sol] = -np.asarray(price) + FEE
    obj[ch], obj[dis] = np.asarray(price) + c["buy"], -np.asarray(price) + c["sell"]
    obj[bu] = obj[bd] = -KEEP
    if res is not None:
        obj[r] = -np.nan_to_num(np.asarray(res, float))
    x = milp(obj, constraints=LinearConstraint(np.array(rows), lo, hi), integrality=integer,
             bounds=Bounds(lower, upper), options={"mip_rel_gap": 1e-6})
    if not x.success:
        raise RuntimeError("lp did not solve")
    v = x.x
    return {"sol": v[sol], "ch": v[ch], "dis": v[dis], "bu": v[bu], "bd": v[bd], "cap": v[r], "s0": v[s0]}


def day_out(pl, fc, act, p, imb, res_real, setup=SETUP, c=C):
    """the day itself, hour by hour: the battery covers actual minus sold solar inside the buffer, its power and
    its charge; the rest is settled at the imbalance price"""
    eff, cap, P = np.sqrt(setup["eff_rt"]), setup["cap_mwh"], setup["power_mw"]
    st, rows = pl["s0"], []
    for h in range(24):
        sold, b = pl["sol"][h], pl["dis"][h] - pl["ch"][h]
        made = act[h] if sold >= fc[h] - 1e-6 else min(act[h], sold)   # turned down if the plan sold less
        e = made - sold
        want = b - min(e, pl["bu"][h]) if e > 0 else b + min(-e, pl["bd"][h])
        want = float(np.clip(want, -P, P))
        if want >= 0:
            a = min(want, st * eff); st -= a / eff
        else:
            a = -min(-want, (cap - st) / eff); st -= a * eff
        x = sold + b                                   # sold day-ahead
        imb_mwh = made + a - x
        rows.append({"hour": h, "sold": x, "made": made, "error": e, "battery": a, "imbalance MWh": imb_mwh,
                     "day-ahead": p[h] * x - FEE * (sold + pl["ch"][h] + pl["dis"][h]),
                     "wear": -(c["sell"] - FEE) * max(a, 0), "imbalance": imb[h] * imb_mwh,
                     "capacity": float(np.nansum(pl["cap"][h] * res_real[h])),
                     "sun": fc[h] > 0.005 or act[h] > 0.005})
    return pd.DataFrame(rows)


def no_battery(fc, act, p_hat, p, imb):
    sold = np.where(p_hat >= 0, fc, 0)
    made = np.where(sold > 0, act, 0)
    return pd.DataFrame({"hour": range(24), "sold": sold, "made": made, "imbalance MWh": made - sold,
                         "day-ahead": p * sold - FEE * sold, "wear": 0.0, "imbalance": imb * (made - sold),
                         "capacity": 0.0, "sun": (fc > 0.005) | (act > 0.005)})


def main():
    OUT.mkdir(exist_ok=True)
    so = solar()
    px = load_all()
    imb = imbalance_prices()
    rp = OUT.parent.parent / "opportunity" / "results" / "reserve_prices.csv"
    res = pd.read_csv(rp, parse_dates=["date"]) if rp.exists() else reserve_prices()
    W = lambda df, d, cols: df[df.date == d].set_index("hour").reindex(range(24))[cols].to_numpy(float)
    err = {d: g.set_index("hour").reindex(range(24)).eval("act - fc").to_numpy() for d, g in so.groupby("date")}

    days, hours = [], []
    for d in pd.date_range(SCORED_FROM, so.date.max()):
        prev = d - pd.Timedelta(days=1)
        fc, act, fc_prev = W(so, d, ["fc"])[:, 0], W(so, d, ["act"])[:, 0], W(so, prev, ["fc"])[:, 0]
        p_hat, p = W(px, d, ["ensemble"])[:, 0], W(px, d, ["actual"])[:, 0]
        p_prev = W(px, prev, ["actual"])[:, 0]
        i_ = W(imb, d, ["imbalance"])[:, 0]
        R_prev, R = W(res, prev, PRODUCTS), W(res, d, PRODUCTS)
        if any(np.isnan(v).any() for v in (fc, act, fc_prev, p_hat, p, p_prev, i_)) \
                or np.isnan(R_prev).all(axis=0).any() or np.isnan(R).all(axis=0).any():
            continue
        # error history: the 60 settled days up to 10 days before
        past = [err[x] for x in pd.date_range(d - pd.Timedelta(days=70), d - pd.Timedelta(days=10)) if x in err]
        past = np.array(past)
        up, dn = buffer(past, fc)
        up0, dn0 = buffer(past, fc_prev)

        a = no_battery(fc, act, p_hat, p, i_).assign(case="A")
        pb = plan(p_hat, fc, up, dn)
        b = day_out(pb, fc, act, p, i_, np.zeros((24, 3))).assign(case="B")
        cap = plan(p_prev, fc_prev, up0, dn0, res=np.where(np.isnan(R_prev), -1e3, R_prev))["cap"]
        cap = np.round(cap, 3)
        pc = plan(p_hat, fc, up, dn, fix=cap)
        c_ = day_out(pc, fc, act, p, i_, R).assign(case="C")
        for x, pl in ((b, pb), (c_, pc)):
            x["buffer short"] = (up - pl["bu"]) + (dn - pl["bd"])
        for x in (a, b, c_):
            x["date"] = d
            x["net"] = x[["day-ahead", "wear", "imbalance", "capacity"]].sum(axis=1)
            hours.append(x)
        days.append({"date": d, "history days": len(past), **{f"{k} €": x["net"].sum() for k, x in (("A", a), ("B", b), ("C", c_))},
                     **{f"{k} imbalance MWh": x["imbalance MWh"].abs().sum() for k, x in (("A", a), ("B", b), ("C", c_))},
                     "solar MWh": act.sum(), "C held MW-hours": cap.sum()})

    daily = pd.DataFrame(days).set_index("date")
    hourly = pd.concat(hours, ignore_index=True)
    daily.round(3).to_csv(OUT / "daily.csv", date_format="%Y-%m-%d")
    hourly.round(4).to_csv(OUT / "hourly.csv", index=False, date_format="%Y-%m-%d")

    m, t = nw_t(daily["C €"] - daily["A €"])
    mb, tb = nw_t(daily["B €"] - daily["A €"])
    sun = hourly[hourly["sun"]]
    past = sun.assign(hit=sun["imbalance MWh"].abs() > 1e-3).groupby("case")["hit"].mean()
    cost = hourly.groupby("case")["imbalance"].sum() / len(daily)
    summary = pd.DataFrame([{"days": len(daily), "first": daily.index.min().date(), "last": daily.index.max().date(),
                             "A € a day": daily["A €"].mean(), "B € a day": daily["B €"].mean(),
                             "C € a day": daily["C €"].mean(),
                             "C minus A": m, "newey-west t": t, "C wins": bool(t > 2),
                             "B minus A": mb, "B newey-west t": tb,
                             **{f"{k} sun hours past the battery": past.get(k, np.nan) for k in "ABC"},
                             **{f"{k} imbalance € a day": cost.get(k, np.nan) for k in "ABC"},
                             "C buffer short hours": int((hourly.query("case == 'C'")["buffer short"] > 1e-3).sum())}])
    summary.round(4).to_csv(OUT / "summary.csv", index=False)
    print(summary.T.to_string())


if __name__ == "__main__":
    main()
