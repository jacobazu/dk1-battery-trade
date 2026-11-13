"""Forecasts and prices from the price repo on GitHub."""
import pandas as pd

REPO = "https://raw.githubusercontent.com/jacobazu/dk1-price-forecasting/master/"
PARTS = ["bmtx", "learx", "xgbx"]  # the ensemble is their average
MODELS = ["ensemble"] + PARTS      # the plan uses the ensemble, the others are compared


def load_backtest():
    """Backtest days: date, hour, actual price and the four forecasts."""
    fc = pd.read_csv(REPO + "results/backtest_forecasts.csv", parse_dates=["date"])
    fc["ensemble"] = fc[PARTS].mean(axis=1)
    return fc[["date", "hour", "actual"] + MODELS].sort_values(["date", "hour"])


def eds_prices(days_back=4):
    """The newest DK1 day-ahead prices straight from Energi Data Service, up to tomorrow once Nord Pool has published
    them (about 13:00). The price repo's file only gets them with its next morning run. Empty if it fails."""
    try:
        import requests
        start = (pd.Timestamp.now(tz="Europe/Copenhagen") - pd.Timedelta(days=days_back)).strftime("%Y-%m-%d")
        r = requests.get("https://api.energidataservice.dk/dataset/DayAheadPrices", timeout=60,
                         params={"start": start, "end": "now+P2D", "filter": '{"PriceArea":["DK1"]}', "limit": 0})
        r.raise_for_status()
        d = pd.DataFrame(r.json()["records"])
        return pd.DataFrame({"time": pd.to_datetime(d["TimeUTC"], utc=True), "price": d["DayAheadPriceEUR"]}).dropna()
    except Exception as e:
        print("energi data service prices skipped:", e)
        return pd.DataFrame(columns=["time", "price"])


def live_prices():
    """Live DK1 prices by Danish date and hour, as build_daily() in R."""
    p = pd.read_csv(REPO + "live/prices_dk1_live.csv", parse_dates=["time"])
    new = eds_prices()
    if len(new):   # quarter-hours from energi data service where the file has nothing yet
        new = new[new["time"] > p["time"].max()]
        p = pd.concat([p[["time", "price"]], new], ignore_index=True)
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
    return lv[["date", "hour", "actual"] + MODELS]


def load_all():
    """Backtest and live days together, sorted, with a source column."""
    bt = load_backtest().assign(source="backtest")
    live = load_live(bt["date"].max()).assign(source="live")
    return pd.concat([bt, live]).sort_values(["date", "hour"]).reset_index(drop=True)


def wide(fc, col):
    """Days x 24 matrix of one column."""
    return fc.pivot(index="date", columns="hour", values=col).reindex(columns=range(24)).to_numpy()
