"""Guesses of day D's reserve prices at 07:15 on D-1. Rules in reserve_forecast/RULES.md."""
import numpy as np
import pandas as pd

PRODUCTS = ["FCR", "aFRR up", "mFRR up"]
GUESSES = ["A", "B", "C"]
FIT_DAYS = 56


def cube(res):
    """Reserve prices as {date: 24 x 3}."""
    return {d: g.set_index("hour").reindex(range(24))[PRODUCTS].to_numpy(float) for d, g in res.groupby("date")}


def get(R, d):
    return R.get(d, np.full((24, len(PRODUCTS)), np.nan))


def last_week(R, d):
    """Median of the same hour on d-7 to d-1."""
    with np.errstate(all="ignore"), __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        return np.nanmedian(np.stack([get(R, d - pd.Timedelta(days=k)) for k in range(1, 8)]), axis=0)


def inputs(R, d):
    """Inputs of the small model for target day d: 24 x 3 x 10, gaps filled with B."""
    b = last_week(R, d)
    lags = [get(R, d - pd.Timedelta(days=k)) for k in (1, 2, 7)]
    lags = [np.where(np.isnan(x), b, x) for x in lags]
    wd = np.zeros(6)
    if d.dayofweek < 6:
        wd[d.dayofweek] = 1
    x = np.stack(lags + [b], axis=-1)
    return np.concatenate([x, np.broadcast_to(wd, x.shape[:2] + (6,))], axis=-1)


def ridge(X, y, x0, alpha=1.0):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1
    Z = (X - mu) / sd
    ym = y.mean()
    w = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - ym))
    return ym + ((x0 - mu) / sd) @ w


def model(R, d):
    """C: ridge per product and hour on the 56 days up to d-1."""
    days = [d - pd.Timedelta(days=k) for k in range(1, FIT_DAYS + 1)]
    X = np.stack([inputs(R, t) for t in days])          # days x 24 x 3 x 10
    Y = np.stack([get(R, t) for t in days])             # days x 24 x 3
    x0 = inputs(R, d)
    out = np.full((24, len(PRODUCTS)), np.nan)
    for h in range(24):
        for j in range(len(PRODUCTS)):
            X_, y = X[:, h, j], Y[:, h, j]
            ok = ~np.isnan(y) & ~np.isnan(X_).any(1)
            if ok.sum() >= 14 and not np.isnan(x0[h, j]).any():
                out[h, j] = ridge(X_[ok], y[ok], x0[h, j])
    return out


def guess(R, d):
    """The three guesses for day d, each 24 x 3, € per MW and hour, never below 0, 0 where nothing is known."""
    a = get(R, d - pd.Timedelta(days=1))
    b = last_week(R, d)
    c = model(R, d)
    c = np.where(np.isnan(c), b, c)
    return {k: np.clip(np.nan_to_num(v), 0, None) for k, v in zip(GUESSES, (a, b, c))}
