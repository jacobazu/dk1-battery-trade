"""Live challengers B and C (reserve_forecast/RULES.md), saved next to the split day, not shown.

Morning, before 07:25: tomorrow's capacity on each guess, to reserve_forecast/live_capacity.csv, saved once and never
changed. Every run scores the days that are over the same way as opportunity/live.py, to live_scored.csv.
Judged on 1 March 2027 against A (opportunity/live_scored.csv).
    python reserve_forecast/live.py
"""
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent / "opportunity")); sys.path.insert(0, str(HERE))
from data import live_prices  # noqa: E402
from opportunity import plan, reserve_prices  # noqa: E402
from guess import PRODUCTS, cube, guess  # noqa: E402

# opportunity/live.py, loaded by path: this file has the same name
_spec = importlib.util.spec_from_file_location("opportunity_live", HERE.parent / "opportunity" / "live.py")
_ol = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_ol)
day, score = _ol.day, _ol.score

CAP, SCORED = HERE / "live_capacity.csv", HERE / "live_scored.csv"
CHALLENGERS = ["B", "C"]


def main():
    now = datetime.now(ZoneInfo("Europe/Copenhagen"))
    today = pd.Timestamp(now.date()); tomorrow = today + pd.Timedelta(days=1)
    res = reserve_prices(start=(today - pd.Timedelta(days=75)).strftime("%Y-%m-%d"))   # c needs 56 + 7 days
    saved = pd.read_csv(CAP, parse_dates=["date"]) if CAP.exists() else pd.DataFrame(columns=["date"])

    if now.hour * 100 + now.minute >= 725:
        print(f"{now:%H:%M}: after 07:25, nothing saved for {tomorrow:%d %b}")
    elif tomorrow in set(saved.date):
        print(f"challengers for {tomorrow:%d %b} already saved")
    else:
        p = day(live_prices(), today, ["price"])[:, 0]
        if np.isnan(p).any():
            print(f"today's day-ahead prices aren't complete, nothing saved for {tomorrow:%d %b}")
        else:
            g = guess(cube(res), tomorrow)
            new = []
            for k in CHALLENGERS:
                _, cap = plan(p, g[k])
                new.append(pd.DataFrame({"made_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M"), "guess": k,
                                         "date": tomorrow, "hour": range(24),
                                         **{f"{pr} guess": np.round(g[k][:, i], 2) for i, pr in enumerate(PRODUCTS)},
                                         **{pr: np.round(cap[:, i], 3) for i, pr in enumerate(PRODUCTS)}}))
            saved = pd.concat([saved, *new]) if len(saved) else pd.concat(new)
            saved.to_csv(CAP, index=False, date_format="%Y-%m-%d")
            print(f"challengers saved for {tomorrow:%d %b}")

    if len(saved):
        old = pd.read_csv(SCORED, parse_dates=["date"]) if SCORED.exists() else pd.DataFrame(columns=["date", "guess"])
        done = set(zip(old.date, old.guess))
        new = []
        for k in CHALLENGERS:
            s = saved[(saved.guess == k) & ~saved.date.map(lambda d: (d, k) in done)]
            if len(s):
                sc = score(s, res)
                if len(sc):
                    new.append(sc.assign(guess=k))
        if new:
            sc = pd.concat([old, *new], ignore_index=True).sort_values(["date", "guess"])
            sc.round(2).to_csv(SCORED, index=False, date_format="%Y-%m-%d")
            print(sc.round(1).tail(4).to_string(index=False))


if __name__ == "__main__":
    main()
