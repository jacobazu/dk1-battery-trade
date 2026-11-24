"""Backfilled split days, made afterwards by the same rules as live.py (opportunity/RULES.md): capacity on the day
before's day-ahead and reserve prices, the day-ahead plan on the price repo's live forecast, saved before that day's
auction. Kept in their own files, never mixed into the live ones, and starred on the page.

- 13 Oct to 14 Nov 2026: between the backtest and the first live morning (15 Nov).
- 23 and 24 Nov 2026: no morning could be saved while Energinet's FCR prices were missing.
- 25 Nov 2026: saved live without FCR; made again with FCR now the prices are back (RULES.md, 23 November).
  The live day stays as saved; the remake is marked as one.
A day already in the file is never made again. Scored by live.py with the live days.
    python opportunity/backfill.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from data import live_prices  # noqa: E402
from live import CAP_BF, SCORED_BF, day, score  # noqa: E402
from opportunity import PRODUCTS, plan, reserve_prices  # noqa: E402

DAYS = list(pd.date_range("2026-10-13", "2026-11-14")) + [pd.Timestamp(d) for d in ("2026-11-23", "2026-11-24")]
REMAKE = [pd.Timestamp("2026-11-25")]


def main():
    old = pd.read_csv(CAP_BF, parse_dates=["date"]) if CAP_BF.exists() else pd.DataFrame(columns=["date"])
    if "remake" not in old:
        old["remake"] = False
    todo = [d for d in DAYS + REMAKE if d not in set(old.date)]
    res = reserve_prices(start=(min(DAYS + REMAKE) - pd.Timedelta(days=2)).strftime("%Y-%m-%d"))
    px = live_prices()
    made = "backfilled " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    new = []
    for d in todo:
        prev = d - pd.Timedelta(days=1)
        p, r = day(px, prev, ["price"])[:, 0], day(res, prev, PRODUCTS)
        # as live.py: a product with no price at all that morning is left out and named in "missing"
        gone = [k for i, k in enumerate(PRODUCTS) if np.isnan(r[:, i]).all()]
        if np.isnan(p).any() or len(gone) == len(PRODUCTS):
            print(f"{d:%d %b}: prices missing, skipped")
            continue
        _, cap = plan(p, np.where(np.isnan(r), -1e3, r))
        for k in gone:
            cap[:, PRODUCTS.index(k)] = 0
        new.append(pd.DataFrame({"made_utc": made, "date": d, "hour": range(24),
                                 **{k: np.round(cap[:, i], 3) for i, k in enumerate(PRODUCTS)},
                                 "missing": ", ".join(gone), "remake": d in REMAKE}))
        print(f"{d:%d %b}: " + ", ".join(f"{k} {cap[:, i].sum():.1f}" for i, k in enumerate(PRODUCTS))
              + (f" (no {', '.join(gone)})" if gone else ""))
    saved = pd.concat([old] + new, ignore_index=True) if new else old
    saved.sort_values(["date", "hour"]).to_csv(CAP_BF, index=False, date_format="%Y-%m-%d")
    sc = score(saved, res)
    sc.round(2).to_csv(SCORED_BF, index=False, date_format="%Y-%m-%d")
    print(f"{len(sc)} backfilled days scored")


if __name__ == "__main__":
    main()
