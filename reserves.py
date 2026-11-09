"""Where should a DK1 battery earn: day-ahead or reserves?

Each day the same 1 MW / 2 MWh battery does one thing: day-ahead arbitrage (this repo's plan after fees and wear),
or selling 1 MW of capacity in FCR, aFRR up or mFRR up. The reserve bids for day D close around 07:30 on D-1, when
D-1's prices in every market are known. Rule, fixed before it was run: day D goes to the market that paid most on
D-1 (a tie goes to day-ahead).

Simplified: in the reserve markets the battery bids 0 and is paid the hourly clearing price (price taker).
Activation energy, wear while holding reserves and the state of charge are left out.
Reserve prices: Energi Data Service. Writes results/reserves_daily.csv
    python reserves.py
"""
import time

import numpy as np
import pandas as pd
import requests

API = "https://api.energidataservice.dk/dataset/"
START = "2023-07-01"
OPTIONS = ["day-ahead", "FCR", "aFRR up", "mFRR up"]
# dataset, time column, price column, filter on DK1 (FcrDK1 is DK1 only)
MARKETS = {"FCR": ("FcrDK1", "HourUTC", "FCRdk_EUR", False),
           "aFRR up": ("AfrrReservesNordic", "TimeUTC", "UpPriceEUR", True),
           "mFRR up": ("mFRRCapacityMarket", "TimeUTC", "UpPriceEUR", True)}


def download(name, time_col, dk1):
    params = {"start": START, "end": "now+P2D", "limit": 0, "sort": f"{time_col} ASC"}
    if dk1:
        params["filter"] = '{"PriceArea":["DK1"]}'
    for attempt in range(5):
        r = requests.get(API + name, params=params, timeout=120)
        if r.status_code == 429:
            time.sleep(60 * (attempt + 1))
            continue
        r.raise_for_status()
        return pd.DataFrame(r.json()["records"])
    raise RuntimeError(f"{name}: still rate limited")


def reserves():
    """€ per day for 1 MW in each reserve market, by danish date."""
    out = []
    for market, (name, time_col, price, dk1) in MARKETS.items():
        d = download(name, time_col, dk1)
        day = pd.to_datetime(d[time_col], utc=True).dt.tz_convert("Europe/Copenhagen").dt.date
        out.append(d.groupby(day)[price].sum().rename(market))
        time.sleep(5)
    return pd.concat(out, axis=1)


def day_ahead():
    d = pd.read_csv("results/cost_daily.csv", parse_dates=["date"])
    d = d[(d["case"] == "main") & (d["plan"] == "in the plan")]
    return d.set_index(d["date"].dt.date)["net"].rename("day-ahead")


def nw_t(x, lags=7):
    x = np.asarray(x, float)
    n, m = len(x), x.mean()
    e = x - m
    v = e @ e / n
    for k in range(1, lags + 1):
        v += 2 * (1 - k / (lags + 1)) * (e[k:] @ e[:-k]) / n
    return m, m / np.sqrt(v / n)


def main():
    v = pd.concat([day_ahead(), reserves()], axis=1, join="inner").sort_index()[OPTIONS].dropna()
    v.index = pd.to_datetime(v.index)
    before = v.shift(1, freq="D").reindex(v.index)  # the calendar day before
    ok = before.notna().all(axis=1)
    v, pick = v[ok], before[ok].idxmax(axis=1)
    chosen = pd.Series([v.at[d, p] for d, p in zip(v.index, pick)], index=v.index)
    out = v.assign(rule=chosen, pick=pick, best=v[OPTIONS].max(axis=1))
    out.index.name = "date"
    out.round(2).to_csv("results/reserves_daily.csv")

    print(f"{len(v)} days, {v.index.min():%d %b %Y} to {v.index.max():%d %b %Y}, € per day for 1 MW")
    print(out[OPTIONS + ["rule", "best"]].mean().round(0).to_string())
    print("\npicked:\n" + pick.value_counts().to_string())
    m, t = nw_t(chosen - v["day-ahead"])
    print(f"\nrule minus day-ahead only: {m:.1f} €/day, newey-west t = {t:.2f}")
    print("\nper day, by month:\n" + out[OPTIONS + ["rule"]].groupby(out.index.to_period("M")).mean().round(0).to_string())


if __name__ == "__main__":
    main()
