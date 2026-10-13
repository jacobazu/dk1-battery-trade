"""Python battery revenue vs R (results/battery_daily.csv)."""
import pandas as pd
from battery import battery_profit

BASE = "https://raw.githubusercontent.com/jacobazu/dk1-price-forecasting/master/results/"
MODELS = ["perfect", "ensemble", "bmtx", "learx", "xgbx", "naive_mix"]

fc = pd.read_csv(BASE + "backtest_forecasts.csv").sort_values(["date", "hour"])
fc["ensemble"] = fc[["bmtx", "learx", "xgbx"]].mean(axis=1)
fc["perfect"] = fc["actual"]
r = pd.read_csv(BASE + "battery_daily.csv")
r = r[r["source"] == "backtest"].set_index("date")[MODELS]

py = pd.DataFrame({
    date: {m: battery_profit(day[m], day["actual"]) for m in MODELS}
    for date, day in fc.groupby("date")
}).T

diff = (py - r).abs()
print("days:", len(diff))
print("days where every model matches to the cent:", int((diff <= 0.01).all(axis=1).sum()))
print(pd.DataFrame({"python": py.sum(), "r": r.sum()}).round(0))

assert ((py.sum() / r.sum() - 1).abs() < 0.001).all(), "totals differ by more than 0.1%"
