"""Are batteries eating their own prices in DK1? Month by month: what 1 MW earns in each market, and how much is
bought and from where. Descriptive, not a test. Writes cannibal/results/monthly.csv
    python cannibal/cannibal.py
"""
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

API = "https://api.energidataservice.dk/dataset/"
START = "2023-07-01"
OUT = Path(__file__).parent / "results"
EFF = np.sqrt(0.9)


def get(name, time_col, dk1=True, start=START):
    params = {"start": start, "end": "now", "limit": 0, "sort": f"{time_col} ASC"}
    if dk1:
        params["filter"] = '{"PriceArea":["DK1"]}'
    for _ in range(8):
        r = requests.get(API + name, params=params, timeout=300)
        if r.status_code == 429:   # wait what it asks
            wait = int(re.search(r"(\d+) seconds", r.text).group(1)) if "seconds" in r.text else 120
            print(name, "rate limited, waiting", wait, flush=True)
            time.sleep(wait + 5)
            continue
        r.raise_for_status()
        d = pd.DataFrame(r.json()["records"])
        t = pd.to_datetime(d[time_col], utc=True).dt.tz_convert("Europe/Copenhagen").dt.tz_localize(None)
        print(name, len(d), "rows from", t.min(), flush=True)
        time.sleep(10)
        return d.assign(t=t)
    raise RuntimeError(name + ": still rate limited")


def best_cycle(p):
    """one full cycle on 1 MW / 2 MWh with hindsight: sell the 2 dearest hours, buy the 2 cheapest"""
    p = np.sort(p)
    return max(0.0, p[-2:].sum() * EFF - p[:2].sum() / EFF)


def main():
    OUT.mkdir(exist_ok=True)
    fcr = get("FcrDK1", "HourUTC", dk1=False)
    afrr = get("AfrrReservesNordic", "TimeUTC")
    mfrr = get("mFRRCapacityMarket", "TimeUTC")
    old = get("Elspotprices", "HourUTC", start=START)
    new = get("DayAheadPrices", "TimeUTC", start="2025-10-01")

    da = pd.concat([pd.DataFrame({"t": old.t, "p": old.SpotPriceEUR}),
                    pd.DataFrame({"t": new.t, "p": new.DayAheadPriceEUR})]).dropna()
    da = da[~da.t.duplicated(keep="last")]
    hourly = da.groupby(da.t.dt.floor("h")).p.mean()
    spread = hourly.groupby(hourly.index.normalize()).apply(lambda x: best_cycle(x.to_numpy()) if len(x) >= 23 else np.nan)

    def hourly_mean(d, cols):
        return d.groupby(d.t.dt.floor("h"))[cols].mean()

    f = hourly_mean(fcr, ["FCRdk_EUR", "FCRdomestic_MW", "FCRabroad_MW"])
    a = hourly_mean(afrr, ["UpPriceEUR", "UpDemandMW", "UpProcuredMW"])
    m = hourly_mean(mfrr, ["UpPriceEUR", "UpDemandMW", "UpProcuredMW"])

    def monthly(x, how):
        return x.groupby(x.index.to_period("M")).agg(how)

    out = pd.concat({
        "FCR € per MW-day": monthly(f.FCRdk_EUR, "mean") * 24,
        "aFRR up € per MW-day": monthly(a.UpPriceEUR, "mean") * 24,
        "mFRR up € per MW-day": monthly(m.UpPriceEUR, "mean") * 24,
        "day-ahead best cycle € a day": monthly(spread, "mean"),
        "FCR bought in DK1 MW": monthly(f.FCRdomestic_MW, "mean"),
        "FCR bought abroad MW": monthly(f.FCRabroad_MW, "mean"),
        "aFRR up demand MW": monthly(a.UpDemandMW, "mean"),
        "aFRR up bought MW": monthly(a.UpProcuredMW, "mean"),
        "mFRR up demand MW": monthly(m.UpDemandMW, "mean"),
        "mFRR up bought MW": monthly(m.UpProcuredMW, "mean"),
        "hours": monthly(hourly, "size"),
    }, axis=1)
    out["FCR share bought in DK1"] = out["FCR bought in DK1 MW"] / (out["FCR bought in DK1 MW"] + out["FCR bought abroad MW"])
    out.index = out.index.astype(str)
    out = out[out.hours >= 24 * 20]   # whole months only
    out.round(3).to_csv(OUT / "monthly.csv", index_label="month")
    print(out.round(1).to_string())


if __name__ == "__main__":
    main()
