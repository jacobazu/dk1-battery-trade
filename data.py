"""Forecasts and prices from the price repo on GitHub."""
import pandas as pd

REPO = "https://raw.githubusercontent.com/jacobazu/dk1-price-forecasting/master/"
PARTS = ["bmtx", "learx", "xgbx"]  # the ensemble is their average


def load_backtest():
    """Backtest days: date, hour, actual price and the ensemble forecast."""
    fc = pd.read_csv(REPO + "results/backtest_forecasts.csv", parse_dates=["date"])
    fc["ensemble"] = fc[PARTS].mean(axis=1)
    return fc[["date", "hour", "actual", "ensemble"]].sort_values(["date", "hour"])


def live_prices():
    """Live DK1 prices by Danish date and hour, as build_daily() in R."""
    p = pd.read_csv(REPO + "live/prices_dk1_live.csv", parse_dates=["time"])
    local = p["time"].dt.tz_convert("Europe/Copenhagen")
    p["date"] = local.dt.tz_localize(None).dt.normalize()
    p["hour"] = local.dt.hour
    return p.groupby(["date", "hour"], as_index=False)["price"].mean()  # autumn dst: average the double hour


def load_live(after):
    """Live forecasts after `after`, with actual prices where known."""
    lv = pd.read_csv(REPO + "forecasts/forecasts_live.csv", parse_dates=["date"])
    lv = lv[lv["date"] > after].drop_duplicates(["date", "hour"], keep="last")
    lv["ensemble"] = lv[PARTS].mean(axis=1)
    lv = lv.dropna(subset=["ensemble"]).groupby("date").filter(lambda d: len(d) == 24)
    lv = lv.merge(live_prices().rename(columns={"price": "actual"}), on=["date", "hour"], how="left")
    return lv[["date", "hour", "actual", "ensemble"]]


def load_all():
    """Backtest and live days together, sorted, with a source column."""
    bt = load_backtest().assign(source="backtest")
    live = load_live(bt["date"].max()).assign(source="live")
    return pd.concat([bt, live]).sort_values(["date", "hour"]).reset_index(drop=True)


def wide(fc, col):
    """Days x 24 matrix of one column."""
    return fc.pivot(index="date", columns="hour", values=col).reindex(columns=range(24)).to_numpy()
