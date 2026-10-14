"""Revenue at risk for a plan, the ewma method from R/risk.R. Revenue = planned + errors @ plan."""
import numpy as np
from scipy.stats import norm

ALPHA = 0.05   # 95% var and es
LAMBDA = 0.94  # ewma weight, riskmetrics' daily value
K_LONG = 250   # days of past errors
MIN_DAYS = 48  # days with errors needed in the 60 before


def error_matrix(fc, col="ensemble"):
    """Days x 24 matrix of errors (actual - forecast)."""
    dates = np.sort(fc["date"].unique())
    E = np.full((len(dates), 24), np.nan)
    E[np.searchsorted(dates, fc["date"]), fc["hour"]] = fc["actual"] - fc[col]
    return dates, E


def ewma_vol(E, lam=LAMBDA):
    """Expected error volatility per day, from the days before."""
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
    """Past 24-hour errors scaled to day i's expected volatility."""
    D = dates[i]
    long = (dates >= D - np.timedelta64(K_LONG, "D")) & (dates < D) & ~np.isnan(E).any(axis=1)
    return E[long] / sig[long, None] * sig[i]


def tail_stats(r, alpha=ALPHA):
    """Expected revenue, floor (5% quantile) and the average below it."""
    floor = np.quantile(r, alpha)
    return {"expected": r.mean(), "floor": floor, "tail": r[r <= floor].mean()}


def worst_mean(r, alpha=ALPHA):
    """Exact average of the worst 5%, as the limit in battery.py."""
    r = np.sort(r)
    k = alpha * len(r)
    j = int(np.floor(k))
    return (r[:j].sum() + (k - j) * (r[j] if j < len(r) else 0)) / k


def nw_test(x, lag=7):
    """Mean of a daily series and its newey-west p-value."""
    n = len(x)
    e = x - x.mean()
    v = e @ e / n
    for k in range(1, lag + 1):
        v += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    t = x.mean() / np.sqrt(v / n)
    return x.mean(), 2 * norm.sf(abs(t))
