"""Fees and wear: costs taken off afterwards vs costs in the plan."""
from pathlib import Path

import numpy as np
import pandas as pd
from battery import battery_schedule
from costs import cost_of, costs
from data import load_backtest, wide
from risk import error_matrix, ewma_vol, has_history, nw_test

# set before running, compared on revenue after costs (newey-west)
CASES = {"main": costs(), "wear 10": costs(wear=10), "wear 40": costs(wear=40), "with tariffs": costs(tariffs=True)}

fc = load_backtest()
dates, E = error_matrix(fc)
sig = ewma_vol(E)
F, A = wide(fc, "ensemble"), wide(fc, "actual")

rows = []
for i in range(len(dates)):
    if not has_history(dates, E, i):
        continue
    blind = battery_schedule(F[i])
    rows.append({"date": dates[i], "case": "none", "plan": "no costs", "revenue": A[i] @ blind, "cost": 0.0,
                 "sold": blind[blind > 0].sum()})
    for name, c in CASES.items():
        aware = battery_schedule(F[i], costs=c)
        for plan, q in [("after the fact", blind), ("in the plan", aware)]:
            rows.append({"date": dates[i], "case": name, "plan": plan, "revenue": A[i] @ q, "cost": cost_of(q, c),
                         "sold": q[q > 0].sum()})
daily = pd.DataFrame(rows)
daily["net"] = daily["revenue"] - daily["cost"]

summary = []
for (case, plan), x in daily.groupby(["case", "plan"], sort=False):
    x = x.set_index("date")
    other = daily[(daily["case"] == case) & (daily["plan"] == "after the fact")].set_index("date")["net"]
    diff, p = nw_test((x["net"] - other).to_numpy()) if plan == "in the plan" else (0.0, np.nan)
    summary.append({"case": case, "plan": plan, "revenue": x["revenue"].sum(), "cost": x["cost"].sum(),
                    "net": x["net"].sum(), "net_per_day": x["net"].mean(), "sold_per_day": x["sold"].mean(),
                    "days_no_trade": int((x["sold"] < 1e-6).sum()), "loss_days": int((x["net"] < 0).sum()),
                    "diff_per_day": diff, "p": p})
summary = pd.DataFrame(summary)

print(f"{daily['date'].nunique()} days, {daily['date'].min():%d %b %Y} to {daily['date'].max():%d %b %Y}")
print(summary.round(3).to_string(index=False))

Path("results").mkdir(exist_ok=True)
daily.round({"revenue": 2, "cost": 2, "sold": 3, "net": 2}).to_csv("results/cost_daily.csv", index=False)
summary.round(4).to_csv("results/cost_summary.csv", index=False)
