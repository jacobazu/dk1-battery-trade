"""Backtest of a loss limit on the battery plan.

Each day the plan still maximises revenue at the forecast, but the average revenue of the worst 5% of
the EWMA scenarios (risk.py) may not fall below -limit. Same days as the revenue at risk in R.
Set before running: the limits below, and the limited plans are compared with the plan without a
limit on realized revenue (Newey-West, 7 lags), loss days and the worst 5% of days.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from battery import battery_schedule
from data import load_backtest, wide
from risk import error_matrix, error_scenarios, ewma_vol, has_history, nw_test, worst_mean

LIMITS = [100, 50, 25, 0]  # euro a bad day may lose on average

fc = load_backtest()
dates, E = error_matrix(fc)
sig = ewma_vol(E)
F, A = wide(fc, "ensemble"), wide(fc, "actual")

rows = []
for i in range(len(dates)):
    if not has_history(dates, E, i):
        continue
    scen = F[i] + error_scenarios(dates, E, sig, i)
    free = battery_schedule(F[i])
    for L in [None] + LIMITS:
        q = free
        if L is not None and worst_mean(scen @ free) < -L:
            q = battery_schedule(F[i], scenarios=scen, es_floor=-L)
        rows.append({"date": dates[i], "limit": "none" if L is None else str(L),
                     "bound": q is not free, "planned": F[i] @ q,
                     "worst_5pct_ex_ante": worst_mean(scen @ q), "realized": A[i] @ q})
daily = pd.DataFrame(rows)

free = daily[daily["limit"] == "none"].set_index("date")["realized"]
summary = []
for L in ["none"] + [str(L) for L in LIMITS]:
    x = daily[daily["limit"] == L].set_index("date")
    diff, p = nw_test((x["realized"] - free).to_numpy()) if L != "none" else (0.0, np.nan)
    summary.append({"limit": L, "days_bound": int(x["bound"].sum()),
                    "revenue": x["realized"].sum(), "share_of_no_limit": x["realized"].sum() / free.sum(),
                    "diff_per_day": diff, "p": p,
                    "loss_days": int((x["realized"] < 0).sum()), "worst_day": x["realized"].min(),
                    "worst_5pct_days": worst_mean(x["realized"].to_numpy())})
summary = pd.DataFrame(summary)

print(f"{daily['date'].nunique()} days, {daily['date'].min():%d %b %Y} to {daily['date'].max():%d %b %Y}")
print(summary.round(3).to_string(index=False))

Path("results").mkdir(exist_ok=True)
daily.round({"planned": 2, "worst_5pct_ex_ante": 2, "realized": 2}).to_csv("results/limit_daily.csv", index=False)
summary.round(4).to_csv("results/limit_summary.csv", index=False)
