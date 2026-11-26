"""Backtest of the reserve price guesses, rules in reserve_forecast/RULES.md.
Writes reserve_forecast/results/daily.csv, error.csv and summary.csv
    python reserve_forecast/backtest.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent)); sys.path.insert(0, str(HERE.parent / "opportunity")); sys.path.insert(0, str(HERE))
from data import load_all  # noqa: E402
from opportunity import da_value, plan, reserve_prices  # noqa: E402
from reserves import nw_t  # noqa: E402
from guess import GUESSES, PRODUCTS, cube, guess  # noqa: E402

OUT = HERE / "results"
FIRST, LAST = pd.Timestamp("2025-10-02"), pd.Timestamp("2026-11-25")


def main():
    OUT.mkdir(exist_ok=True)
    fc = load_all()
    res = reserve_prices(start="2025-08-01")
    res.to_csv(OUT / "reserve_prices.csv", index=False)
    R = cube(res)
    days, err = [], []
    for d, g in fc.groupby("date"):
        prev = d - pd.Timedelta(days=1)
        if not FIRST <= d <= LAST or len(g) != 24 or g.actual.isna().any():
            continue
        # the same days as opportunity/
        if prev not in R or d not in R or np.isnan(R[prev]).all(axis=0).any() or np.isnan(R[d]).all(axis=0).any():
            continue
        p_prev = fc[fc.date == prev].sort_values("hour").actual.to_numpy()
        if len(p_prev) != 24 or np.isnan(p_prev).any():
            continue
        g = g.sort_values("hour")
        p_hat, p = g.ensemble.to_numpy(), g.actual.to_numpy()
        real = np.nan_to_num(R[d])
        row = {"date": d}
        for k, r_hat in {**guess(R, d), "real reserve prices": real}.items():
            _, cap = plan(p_prev, r_hat)
            q, _ = plan(p_hat, None, fix=cap)
            row[k] = da_value(q, p) + float((cap * real).sum())
            if k in GUESSES:
                ok = ~np.isnan(R[d])
                err += [{"date": d, "guess": k, "product": pr, "abs error": np.abs(r_hat - R[d])[:, j][ok[:, j]].mean()}
                        for j, pr in enumerate(PRODUCTS)]
        days.append(row)
        print(d.date(), {k: round(v) for k, v in row.items() if k != "date"}, flush=True)

    daily = pd.DataFrame(days).set_index("date")
    daily.round(2).to_csv(OUT / "daily.csv")
    mae = pd.DataFrame(err).groupby(["guess", "product"])["abs error"].mean().unstack().round(1)
    mae.to_csv(OUT / "error.csv")

    head = daily["real reserve prices"].mean() - daily["A"].mean()
    tests = []
    for k in ["C", "B"]:   # main test first
        m, t = nw_t(daily[k] - daily["A"])
        tests.append({"guess": k, "€ a day": round(daily[k].mean(), 1), "minus A": round(m, 1),
                      "newey-west t": round(t, 2), "p one sided": 1 - norm.cdf(t),
                      "share of headroom": round(m / head, 3)})
    s = pd.DataFrame(tests).sort_values("p one sided")
    s["holm p"] = (s["p one sided"] * [2, 1]).cummax().clip(upper=1)
    s["wins"] = s["holm p"] < 0.05
    s = s.set_index("guess").loc[["C", "B"]]
    s.insert(0, "days", len(daily)); s.insert(1, "first", daily.index.min().date()); s.insert(2, "last", daily.index.max().date())
    s.insert(3, "A € a day", round(daily["A"].mean(), 1)); s.insert(4, "real prices € a day", round(daily["real reserve prices"].mean(), 1))
    s.round(4).to_csv(OUT / "summary.csv")
    print(s.T.to_string())
    print(mae.to_string())


if __name__ == "__main__":
    main()
