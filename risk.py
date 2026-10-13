"""Revenue at risk for a battery plan, the EWMA method from R/risk.R in dk1-price-forecasting.

The plan is fixed before the auction, so revenue = planned + errors @ plan. Scenarios are the 24-hour
errors of up to 250 past days, each divided by the error volatility expected for its own day and
multiplied by the one expected for the day being planned.
"""
import numpy as np
from scipy.stats import norm

ALPHA = 0.05   # 95% var and es
LAMBDA = 0.94  # ewma weight, riskmetrics' daily value
K_LONG = 250   # days of past errors
MIN_DAYS = 48  # a day needs this many days of errors in the 60 before it, as in R


def error_matrix(fc):
    """Days x 24 matrix of errors (actual - ensemble) from a date, hour, actual, ensemble table."""
    dates = np.sort(fc["date"].unique())
    E = np.full((len(dates), 24), np.nan)
    E[np.searchsorted(dates, fc["date"]), fc["hour"]] = fc["actual"] - fc["ensemble"]
    return dates, E


def ewma_vol(E, lam=LAMBDA):
    """Error volatility expected for each day, from the days before it. Starts at the first 30 days."""
    m = np.mean(E ** 2, axis=1)
    v = np.empty(len(m))
    v[0] = np.nanmean(m[:30])
    for i in range(1, len(m)):
        v[i] = v[i - 1] if np.isnan(m[i - 1]) else lam * v[i - 1] + (1 - lam) * m[i - 1]
    return np.sqrt(v)


def has_history(dates, E, i):
    """Enough past errors for a risk estimate on day i."""
    D = dates[i]
    past = (dates >= D - np.timedelta64(60, "D")) & (dates < D) & ~np.isnan(E).any(axis=1)
    return past.sum() >= MIN_DAYS


def error_scenarios(dates, E, sig, i):
    """Rows of 24-hour errors that could happen on day i, scaled to its expected volatility."""
    D = dates[i]
    long = (dates >= D - np.timedelta64(K_LONG, "D")) & (dates < D) & ~np.isnan(E).any(axis=1)
    return E[long] / sig[long, None] * sig[i]


def tail_stats(r, alpha=ALPHA):
    """Expected revenue, floor (5% quantile) and the average below the floor, as in R."""
    floor = np.quantile(r, alpha)
    return {"expected": r.mean(), "floor": floor, "tail": r[r <= floor].mean()}


def worst_mean(r, alpha=ALPHA):
    """Average of the worst 5% (the exact version the limit in battery.py uses)."""
    r = np.sort(r)
    k = alpha * len(r)
    j = int(np.floor(k))
    return (r[:j].sum() + (k - j) * (r[j] if j < len(r) else 0)) / k


def nw_test(x, lag=7):
    """Mean of a daily series and its p-value with a Newey-West variance, as R/tests.R."""
    n = len(x)
    e = x - x.mean()
    v = e @ e / n
    for k in range(1, lag + 1):
        v += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    t = x.mean() / np.sqrt(v / n)
    return x.mean(), 2 * norm.sf(abs(t))
