"""Python revenue at risk vs R (results/battery_risk_daily.csv)."""
import numpy as np
import pandas as pd
from battery import battery_schedule
from data import REPO, load_backtest, wide
from risk import error_matrix, error_scenarios, ewma_vol, tail_stats

COLS = ["planned", "expected", "floor", "tail", "realized"]

fc = load_backtest()
dates, E = error_matrix(fc)
sig = ewma_vol(E)
F, A = wide(fc, "ensemble"), wide(fc, "actual")

r = pd.read_csv(REPO + "results/battery_risk_daily.csv", parse_dates=["date"])
r = r[(r["method"] == "ewma") & (r["source"] == "backtest")].set_index("date")[COLS]

rows = []
for D in r.index:
    i = np.searchsorted(dates, D)
    q = battery_schedule(F[i])
    planned = F[i] @ q
    st = tail_stats(planned + error_scenarios(dates, E, sig, i) @ q)
    rows.append({"date": D, "planned": planned, **st, "realized": A[i] @ q})
py = pd.DataFrame(rows).set_index("date")[COLS]

diff = (py - r).abs()
same = (diff <= 0.01).all(axis=1)
print("days:", len(diff))
print("days where every number matches to the cent:", int(same.sum()))
print("other days:", [str(D.date()) for D in diff.index[~same]])
print(pd.DataFrame({"python": py.mean(), "r": r.mean()}).round(2))

assert same.mean() > 0.99, "more than 1% of days differ"
