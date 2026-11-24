"""Live paper version of the split day (opportunity/RULES.md).

Morning, before Energinet's capacity auctions close (07:30): choose tomorrow's capacity per hour on today's day-ahead
and reserve prices, and save it to opportunity/live_capacity.csv. Saved once per day and never changed; a run after
07:25 saves nothing, so a missed morning is a gap.
Every run also scores the days that are over: the day-ahead plan in the power left (on the price repo's live forecast),
paid at the real prices, plus the capacity at the real reserve prices. To opportunity/live_scored.csv
    python opportunity/live.py
"""
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from data import live_prices, load_live  # noqa: E402
from opportunity import PRODUCTS, da_value, plan, reserve_prices  # noqa: E402

CAP = HERE / "live_capacity.csv"
SCORED = HERE / "live_scored.csv"
CAP_BF, SCORED_BF = HERE / "live_capacity_backfill.csv", HERE / "live_scored_backfill.csv"   # backfill.py
START = pd.Timestamp("2026-11-13")


def day(df, d, cols):
    g = df[df.date == d].set_index("hour").reindex(range(24))
    return g[cols].to_numpy(dtype=float)


def main():
    now = datetime.now(ZoneInfo("Europe/Copenhagen"))
    today = pd.Timestamp(now.date()); tomorrow = today + pd.Timedelta(days=1)
    res = reserve_prices(start=(today - pd.Timedelta(days=10)).strftime("%Y-%m-%d"))
    px = live_prices()
    saved = pd.read_csv(CAP, parse_dates=["date"]) if CAP.exists() else pd.DataFrame(columns=["date"])

    # 1. the morning choice
    if now.hour * 100 + now.minute >= 725:
        print(f"{now:%H:%M}: after 07:25, the capacity auctions close at 07:30. nothing saved for {tomorrow:%d %b}")
    elif tomorrow in set(saved.date):
        print(f"capacity for {tomorrow:%d %b} already saved")
    else:
        p, r = day(px, today, ["price"])[:, 0], day(res, today, PRODUCTS)
        # a product energinet hasn't published at all today is left out: no capacity in it, noted in "missing".
        # since 23 nov 2026 for fcr (FcrDK1 stopped after 21 nov); see RULES.md
        gone = [k for i, k in enumerate(PRODUCTS) if np.isnan(r[:, i]).all()]
        if np.isnan(p).any() or len(gone) == len(PRODUCTS):
            print(f"today's day-ahead or reserve prices aren't complete, nothing saved for {tomorrow:%d %b}: "
                  f"{int(np.isnan(p).sum())} day-ahead hours missing, reserve hours per product "
                  f"{dict(zip(PRODUCTS, (~np.isnan(r)).sum(axis=0).tolist()))}")
        else:
            r = np.where(np.isnan(r), -1e3, r)               # a price no plan would sell at
            _, cap = plan(p, r)
            for k in gone:
                cap[:, PRODUCTS.index(k)] = 0
            if gone:
                print(f"no {', '.join(gone)} prices today, left out for {tomorrow:%d %b}")
            new = pd.DataFrame({"made_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M"), "date": tomorrow,
                                "hour": range(24), **{k: np.round(cap[:, i], 3) for i, k in enumerate(PRODUCTS)},
                                "missing": ", ".join(gone)})
            saved = pd.concat([saved, new]) if len(saved) else new
            saved.to_csv(CAP, index=False, date_format="%Y-%m-%d")
            print(f"saved capacity for {tomorrow:%d %b}: " +
                  ", ".join(f"{k} {cap[:, i].sum():.1f} MW-hours" for i, k in enumerate(PRODUCTS)))

    # 2. score the days that are over, live and backfilled, each in its own file
    for cap_file, out_file in ((CAP, SCORED), (CAP_BF, SCORED_BF)):
        if cap_file.exists():
            s = pd.read_csv(cap_file, parse_dates=["date"])
            # days already scored stay as they are; res only reaches 10 days back
            old = pd.read_csv(out_file, parse_dates=["date"]) if out_file.exists() else pd.DataFrame(columns=["date"])
            new = score(s[~s.date.isin(set(old.date))], res) if (~s.date.isin(set(old.date))).any() else pd.DataFrame()
            sc = pd.concat([old, new], ignore_index=True).sort_values("date") if len(new) else old
            if len(new):
                sc.round(2).to_csv(out_file, index=False, date_format="%Y-%m-%d")
                print(cap_file.name, "\n", sc.round(1).tail(5).to_string(index=False))


def score(saved, res):
    """days that are over: the day-ahead plan in the power left, paid at the real prices, plus the capacity"""
    lv = load_live(saved.date.min() - pd.Timedelta(days=1))
    rows = []
    for d in sorted(set(saved.date)):
        g = lv[lv.date == d].sort_values("hour")
        cap = day(saved, d, PRODUCTS)
        r_real = day(res, d, PRODUCTS) if d in set(res.date) else None
        if len(g) != 24 or g.actual.isna().any() or r_real is None:
            continue
        # a product with no real prices can only be scored if no capacity was held in it
        if any(np.isnan(r_real[:, i]).all() and cap[:, i].sum() > 0 for i in range(len(PRODUCTS))):
            continue
        p_hat, p = g.ensemble.to_numpy(), g.actual.to_numpy()
        q, _ = plan(p_hat, None, fix=cap)
        q0, _ = plan(p_hat, None, cyclic=False)           # day-ahead only, as the live page
        miss = saved.loc[saved.date == d, "missing"].dropna() if "missing" in saved else pd.Series(dtype=str)
        rows.append({"date": d, "missing": miss.iloc[0] if len(miss) else "",
                     **({"remake": bool(saved.loc[saved.date == d, "remake"].iloc[0])} if "remake" in saved else {}),
                     "day-ahead part": da_value(q, p), "capacity part": float(np.nansum(cap * r_real)),
                     "day-ahead only": da_value(q0, p),
                     **{f"MWh {k}": cap[:, i].sum() for i, k in enumerate(PRODUCTS)}})
    sc = pd.DataFrame(rows)
    if len(sc):
        sc["split day"] = sc["day-ahead part"] + sc["capacity part"]
    return sc


if __name__ == "__main__":
    main()
