"""Battery dashboard: docs/index.html (live) and docs/backtest.html. Runs daily."""
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.stats import binom

from battery import SETUP, battery_schedule
from costs import FEE, WEAR, cost_of, costs
from data import MODELS, load_all, wide
from risk import ALPHA, error_matrix, error_scenarios, ewma_vol, has_history, nw_test, tail_stats
from stress import stress_tests

ORANGE, GREEN, RED, BLUE = "#f97316", "#16a34a", "#dc2626", "#0ea5e9"
INK, GREY, LINE, GRID, BEIGE = "#1f2328", "#6b7280", "#e5ddd3", "#f1ebe4", "#cfc6bb"
FONT = "IBM Plex Sans, Segoe UI, Helvetica Neue, Arial, sans-serif"
# github icon, the same as on the other two dashboards (bootstrap icons)
GITHUB_ICON = ('<svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 '
               '3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94'
               '-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78'
               '-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27'
               's1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 '
               '3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8"/>'
               '</svg>')
PLOTLY_JS = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@4.1.1/plotly.min.js"
LAUNCH = pd.Timestamp("2026-10-13")  # first day traded on a live forecast
LABELS = {"ensemble": "Ensemble", "bmtx": "BMT-X", "learx": "LEAR-X", "xgbx": "XGBoost-X"}
COLORS = {"ensemble": ORANGE, "bmtx": "#7c3aed", "learx": BLUE, "xgbx": GREEN}  # as on the price dashboard
COSTS = costs()  # nord pool fee + wear


def eur(x):
    return f"{'-' if x < -0.5 else ''}{abs(x):,.0f} €"


def windows(mask):
    """Runs of hours where mask is true, as (first hour, end hour)."""
    out, start = [], None
    for h, m in enumerate(list(mask) + [False]):
        if m and start is None:
            start = h
        if not m and start is not None:
            out.append((start, h))
            start = None
    return out


def hours(ws):
    return ", ".join(f"{a:02d}-{b:02d}" for a, b in ws) or "none"


def battery_fill(q, setup=SETUP):
    eff = np.sqrt(setup["eff_rt"])
    return np.concatenate([[0], np.cumsum(np.where(q < 0, -q * eff, -q / eff))])


def kupiec_p(misses, n, alpha=ALPHA):
    """Exact binomial p-value for the number of days below the floor, as in R."""
    def lr(x):
        p = x / n
        ll = lambda a, b: 0 if a == 0 else a * np.log(b)
        return -2 * (ll(n - x, 1 - alpha) + ll(x, alpha) - ll(n - x, 1 - p) - ll(x, p))
    obs = lr(misses)
    return sum(binom.pmf(x, n, alpha) for x in range(n + 1) if lr(x) >= obs - 1e-9)


def holm(p):
    """Holm-adjusted p-values."""
    p = np.asarray(p, float)
    o = np.argsort(p)
    adj = np.minimum(1, np.maximum.accumulate(p[o] * (len(p) - np.arange(len(p)))))
    out = np.empty(len(p))
    out[o] = adj
    return out


def style(fig, height):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=10, b=10), font=dict(family=FONT, color=GREY, size=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
        legend=dict(orientation="h", x=0, y=-0.15, font=dict(color=INK)),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#efe6dc", font=dict(color=INK, family=FONT)))
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=LINE, color=GREY)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=BEIGE, color=GREY)
    return fig.to_html(full_html=False, include_plotlyjs=False, config=dict(displayModeBar=False, responsive=True))


def run(m):
    """Every day with enough past errors: the plan on forecast m, its risk and what it earned."""
    dates, E = error_matrix(fc, m)
    sig = ewma_vol(E)
    F, A = wide(fc, m), wide(fc, "actual")
    rows = []
    for i in range(len(dates)):
        if np.isnan(F[i]).any() or not has_history(dates, E, i):
            continue
        f, a = F[i], A[i]
        q = battery_schedule(f, costs=COSTS)
        S = error_scenarios(dates, E, sig, i)
        cost = cost_of(q, COSTS)
        st = tail_stats(f @ q + S @ q - cost)
        known = not np.isnan(a).any()
        qp = battery_schedule(a, costs=COSTS) if known else None
        rows.append({"date": pd.Timestamp(dates[i]), "live": pd.Timestamp(dates[i]) >= LAUNCH,
                     "expected": st["expected"], "floor": st["floor"], "cost": cost,
                     "gross": a @ q if known else np.nan,
                     "realized": a @ q - cost if known else np.nan,
                     "perfect": a @ qp - cost_of(qp, COSTS) if known else np.nan,
                     "q": q, "f": f, "S": S})
    return pd.DataFrame(rows)


# the same battery planned on each of the four forecasts
fc = load_all()
latest = fc["date"].max()
day = latest.strftime("%a %d %b")
runs = {m: run(m) for m in MODELS}

# what each plan earned, side by side
cmp_days = runs["ensemble"].dropna(subset=["realized"])[["date", "live", "perfect"]]
for m in MODELS:
    done_m = runs[m].dropna(subset=["realized"])[["date", "realized"]].rename(columns={"realized": m})
    cmp_days = cmp_days.merge(done_m, on="date", how="left")
lc, bc = cmp_days[cmp_days["live"]], cmp_days[~cmp_days["live"]]


def compare(d, tests):
    """One row per forecast: P&L after costs, share of perfect, and the daily difference to the ensemble."""
    rows, ps = [], []
    for m in MODELS:
        x = d.dropna(subset=[m])
        r = {"model": m, "days": len(x), "total": x[m].sum(), "share": x[m].sum() / x["perfect"].sum(),
             "loss_days": int((x[m] < 0).sum()), "diff": np.nan, "p": np.nan}
        if tests and m != "ensemble":
            r["diff"], r["p"] = nw_test((x[m] - x["ensemble"]).to_numpy())
            ps.append(r["p"])
        rows.append(r)
    out = pd.DataFrame(rows)
    if tests:
        out.loc[out["model"] != "ensemble", "p"] = holm(ps)
    return out


def pval(p):
    return "< 0.001" if p < 0.001 else f"{p:.3f}"


def compare_table(c, tests, sel):
    head = ("<tr><th>Forecast</th><th class='n'>Days</th><th class='n'>After costs</th><th class='n'>Share of perfect</th>"
            + ("<th class='n'>Loss days</th><th class='n'>vs ensemble, a day</th>" if tests else "") + "</tr>")
    body = "".join(
        f"<tr{' class=sel' if r.model == sel else ''}><td>{LABELS[r.model]}</td>"
        f"<td class='n'>{r.days}</td><td class='n'>{eur(r.total)}</td><td class='n'>{r.share:.0%}</td>"
        + (f"<td class='n'>{r.loss_days}</td><td class='n'>"
           f"{'' if np.isnan(r.p) else f'{r.diff:+.1f} € (p {pval(r.p)})'}</td>" if tests else "") + "</tr>"
        for r in c.itertuples())
    return f"<table>{head}{body}</table>"


live_cmp = compare(lc, tests=False) if len(lc) else None
bt_cmp = compare(bc, tests=True)


def cum_lines(fig, d, x, sel, markers):
    """Added-up P&L of every forecast, the chosen one on top and thicker."""
    mode = "lines+markers" if markers else "lines"
    first = [0] if markers else []
    for m in [k for k in MODELS if k != sel] + [sel]:
        fig.add_trace(go.Scatter(x=x, y=first + list(d[m].fillna(0).cumsum()), mode=mode, name=LABELS[m],
                                 line=dict(color=COLORS[m], width=3 if m == sel else 1.5),
                                 marker=dict(size=7 if m == sel else 5), opacity=1 if m == sel else 0.75,
                                 hovertemplate="%{y:,.0f} €"))


def kpi(label, value, sub, accent):
    return (f"<div class='card kpi' style='--accent:{accent}'><div class='kpi-label'>{label}</div>"
            f"<div class='kpi-value'>{value}</div><div class='kpi-sub'>{sub}</div></div>")


def card(title, body, extra=""):
    return f"<div class='card {extra}'><div class='card-title'>{title}</div>{body}</div>"


def model_pages(m):
    """Plan, P&L and stress tests (live page), track record and risk (backtest page) for forecast m."""
    days, label = runs[m], LABELS[m]
    done = days.dropna(subset=["realized"])
    nxt = days.iloc[-1]
    live = {}

    # tomorrow
    if nxt["date"] == latest:
        f, q, S = nxt["f"], nxt["q"], nxt["S"]
        q = np.where(np.abs(q) < 1e-6, 0, q)
        lo, hi = np.percentile(f + S, 5, axis=0), np.percentile(f + S, 95, axis=0)
        stress = {k: v - nxt["cost"] for k, v in stress_tests(f, q, S).items()}
        worst_name, worst_val = min(stress.items(), key=lambda kv: kv[1])

        x, step = np.arange(24) + 0.5, np.arange(25)
        pad = lambda v: np.append(v, v[-1])
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=step, y=pad(lo), mode="lines", line=dict(width=0, shape="hv"), hoverinfo="skip",
                                 showlegend=False))
        fig.add_trace(go.Scatter(x=step, y=pad(hi), mode="lines", line=dict(width=0, shape="hv"), fill="tonexty",
                                 fillcolor="rgba(107,114,128,0.15)", name="90% range", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=step, y=pad(f), mode="lines", line=dict(color=INK, width=2, shape="hv"),
                                 name=f"Forecast ({label})", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x, y=f, mode="markers", marker=dict(size=20, color="rgba(0,0,0,0)"), showlegend=False,
                                 customdata=np.c_[lo, hi, q],
                                 hovertemplate="%{y:.0f} €/MWh (90%: %{customdata[0]:.0f}-%{customdata[1]:.0f})"
                                               "<br>Plan: %{customdata[2]:.2f} MWh<extra></extra>"))
        for mask, colour, word in [(q < 0, BLUE, "Buy"), (q > 0, ORANGE, "Sell")]:
            for a_, b_ in windows(mask):
                fig.add_vrect(x0=a_, x1=b_, fillcolor=colour, opacity=0.12, line_width=0, layer="below",
                              annotation_text=word, annotation_position="top left",
                              annotation_font=dict(color=colour, size=12))
        ticks = dict(range=[0, 24], tickvals=list(range(0, 25, 3)), ticktext=[f"{h:02d}:00" for h in range(0, 25, 3)])
        fig.update_xaxes(**ticks)
        fig.update_yaxes(title_text="€/MWh")
        plan_chart = style(fig, 330)

        fig = go.Figure()
        fig.add_trace(go.Bar(x=x[q < 0], y=q[q < 0], marker=dict(color=BLUE, cornerradius=4), width=0.6, name="Buy",
                             hovertemplate="Buy %{y:.2f} MWh<extra></extra>"))
        fig.add_trace(go.Bar(x=x[q > 0], y=q[q > 0], marker=dict(color=ORANGE, cornerradius=4), width=0.6, name="Sell",
                             hovertemplate="Sell %{y:.2f} MWh<extra></extra>"))
        fig.add_trace(go.Scatter(x=step, y=battery_fill(q), mode="lines", line=dict(color=GREY, width=2), name="Stored",
                                 hovertemplate="Stored %{y:.2f} MWh<extra></extra>"))
        fig.update_xaxes(**ticks)
        fig.update_yaxes(title_text="MWh", range=[-1.2, 2.2])
        fill_chart = style(fig, 220)

        orders = "".join(
            f"<tr><td>{h:02d}:00-{h + 1:02d}:00</td><td>{'Buy' if v < 0 else 'Sell'}</td><td class='n'>{abs(v):.2f}</td>"
            f"<td class='n'>{f[h]:.0f}</td><td class='n'>{lo[h]:.0f}-{hi[h]:.0f}</td></tr>"
            for h, v in enumerate(q) if v != 0)

        names = ["Expected", "1 day in 20 below"] + list(stress)
        vals = [nxt["expected"], nxt["floor"]] + list(stress.values())
        fig = go.Figure(go.Bar(y=names, x=vals, orientation="h",
                               marker=dict(color=[RED if v < 0 else BEIGE for v in vals], cornerradius=4),
                               text=[eur(v) for v in vals], textposition="outside", cliponaxis=False, width=0.6,
                               hovertemplate="%{y}: %{x:.0f} €<extra></extra>"))
        fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
        fig.update_xaxes(ticksuffix=" €", zeroline=True, zerolinecolor=BEIGE, showgrid=True, gridcolor=GRID)
        stress_chart = style(fig, 330)

        live["Plan"] = f"""
<div class='kpis'>
{kpi(f"Buy {day}", hours(windows(q < 0)), f"{-q[q < 0].sum():.1f} MWh", BLUE)}
{kpi("Sell", hours(windows(q > 0)), f"{q[q > 0].sum():.1f} MWh", ORANGE)}
{kpi("Expected, after costs", eur(nxt['expected']), f"Fees and wear: {eur(nxt['cost'])}", GREEN)}
{kpi("1 day in 20 below", eur(nxt['floor']), f"Worst stress test: {escape(worst_name.lower())}, {eur(worst_val)}", RED)}
</div>
<div class='grid2'>
{card(f"{label} forecast for {day}, with the hours to buy and sell", plan_chart + fill_chart)}
{card("Orders", f"<table><tr><th>Hour</th><th>Order</th><th class='n'>MWh</th><th class='n'>€/MWh</th><th class='n'>90% range</th></tr>{orders}</table>")}
</div>"""
        live["Stress tests"] = f"""
{card(f"What {day} earns on the {label} plan if it goes like this", stress_chart)}
<p class='note'>Worst past day: the worst forecast error of the last 250 days. Peak doesn't come: selling hours
fall to the median price. Negative prices: -50 €/MWh 11-15. Errors x3: the worst 5% with errors three times as big.</p>"""
    else:
        live["Plan"] = live["Stress tests"] = card(f"No {label} forecast for {day}",
                                                   "<p class='note'>The model didn't run for this day. Pick another "
                                                   "forecast at the top.</p>")

    # live: every day traded on a live forecast since launch
    lv = done[done["live"]]
    pnl = lv["realized"].cumsum()
    drawdown = (pnl - np.maximum.accumulate(np.r_[0, pnl.to_numpy()])[1:]).min() if len(lv) else 0.0
    lv_miss = int((lv["realized"] < lv["floor"]).sum())

    # start at 0 the day before launch, show at least a week
    DAY = pd.Timedelta(days=1)
    start = LAUNCH - DAY
    x_range = [start - DAY / 2, max(lc["date"].max() if len(lc) else LAUNCH, LAUNCH + 6 * DAY) + DAY / 2]
    x_axis = dict(tickformat="%d %b", range=x_range, dtick=DAY / pd.Timedelta(milliseconds=1) * (1 if len(lc) < 15 else 7))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[start] + list(lc["date"]), y=[0] + list(lc["perfect"].cumsum()), mode="lines+markers",
                             name="Perfect foresight", line=dict(color=BEIGE, width=2, dash="dot"),
                             hovertemplate="%{y:,.0f} €"))
    cum_lines(fig, lc, [start] + list(lc["date"]), m, markers=True)
    fig.update_yaxes(ticksuffix=" €", rangemode="tozero")
    fig.update_xaxes(**x_axis)
    pnl_chart = style(fig, 320)

    fig = go.Figure(go.Bar(x=lv["date"], y=lv["realized"], width=0.6 * DAY / pd.Timedelta(milliseconds=1),
                           marker=dict(color=np.where(lv["realized"] < 0, RED, GREEN), cornerradius=4),
                           hovertemplate="%{x|%d %b}: %{y:,.0f} €<extra></extra>"))
    fig.update_yaxes(ticksuffix=" €")
    fig.update_xaxes(**x_axis)
    daily_chart = style(fig, 220)

    live_rows = "".join(
        f"<tr><td>{r.date:%a %d %b}</td><td class='n'>{eur(r.expected)}</td><td class='n'>{eur(r.floor)}</td>"
        f"<td class='n'>{eur(r.cost)}</td><td class='n'><b>{eur(r.realized)}</b></td><td class='n'>{eur(r.perfect)}</td>"
        f"<td>{'below the floor' if r.realized < r.floor else ''}</td></tr>"
        for r in lv.iloc[::-1].itertuples())
    cmp_html = compare_table(live_cmp, False, m) if live_cmp is not None else "<p class='note'>Starts after the first day.</p>"

    live["P&L"] = f"""
<div class='kpis'>
{kpi(f"P&L since launch, after costs ({label})", eur(pnl.iloc[-1]) if len(lv) else "-", f"{len(lv)} day{'s' * (len(lv) != 1)} since {LAUNCH:%d %b %Y}, before costs {eur(lv['gross'].sum())}" if len(lv) else "", GREEN)}
{kpi("Last day", eur(lv['realized'].iloc[-1]) if len(lv) else "-", f"{lv['date'].iloc[-1]:%a %d %b}" if len(lv) else "", ORANGE)}
{kpi("Share of perfect foresight", f"{lv['realized'].sum() / lv['perfect'].sum():.0%}" if len(lv) else "-", "What a plan on the real prices would make", BLUE)}
{kpi("Max drawdown", eur(drawdown), f"Days below the 1 in 20 floor: {lv_miss} of {len(lv)}", RED)}
</div>
<div class='grid2'>
<div>{card("P&L since launch, added up", pnl_chart)}{card(f"P&L per day ({label})", daily_chart)}</div>
<div>{card("Each forecast, the same battery", cmp_html)}
{card(f"Every day since launch ({label})", "<table><tr><th>Day</th><th class='n'>Expected</th><th class='n'>1 in 20 floor</th>"
      f"<th class='n'>Costs</th><th class='n'>Earned</th><th class='n'>Perfect</th><th></th></tr>{live_rows}</table>"
      "<p class='note'>Planned the day before on the live forecast, paid the real price. "
      f"After the Nord Pool fee ({FEE} €/MWh) and wear ({WEAR:.0f} €/MWh sold). No grid tariffs or taxes.</p>")}</div>
</div>"""

    # backtest track record
    bt = done[~done["live"]]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bc["date"], y=bc["perfect"].cumsum(), mode="lines", line=dict(color=BEIGE, width=2),
                             name="Perfect foresight", hovertemplate="%{y:,.0f} €"))
    cum_lines(fig, bc, bc["date"], m, markers=False)
    fig.update_yaxes(ticksuffix=" €")
    track_chart = style(fig, 380)

    month = bt.groupby(bt["date"].dt.to_period("M")).agg(realized=("realized", "sum"), perfect=("perfect", "sum"))
    fig = go.Figure(go.Bar(x=month.index.strftime("%b %Y"), y=month["realized"] / month["perfect"] * 100,
                           marker=dict(color=COLORS[m], cornerradius=4), width=0.6,
                           hovertemplate="%{x}: %{y:.0f}% of perfect<extra></extra>"))
    fig.update_yaxes(ticksuffix="%", range=[0, 105])
    month_chart = style(fig, 260)

    # backtest risk
    miss = bt["realized"] < bt["floor"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=bt["date"], y=bt["expected"], mode="lines", line=dict(color=GREY, width=1.5),
                             name="Expected", hovertemplate="Expected %{y:.0f} €"))
    fig.add_trace(go.Scatter(x=bt["date"], y=bt["floor"], mode="lines", line=dict(color=RED, width=1.5, dash="dot"),
                             name="1 day in 20 below", hovertemplate="Floor %{y:.0f} €"))
    fig.add_trace(go.Scatter(x=bt["date"], y=bt["realized"], mode="markers",
                             marker=dict(size=6, color=np.where(miss, RED, INK), opacity=0.8), name="What it earned",
                             hovertemplate="Earned %{y:.0f} €"))
    fig.update_yaxes(ticksuffix=" €")
    risk_chart = style(fig, 380)

    n, k = len(bt), int(miss.sum())
    back = {
        "Track record": f"""
<div class='kpis'>
{kpi(f"Share of perfect foresight ({label})", f"{bt['realized'].sum() / bt['perfect'].sum():.0%}", f"{n} days", ORANGE)}
{kpi("Earned in total, after costs", eur(bt['realized'].sum()), f"{eur(bt['realized'].mean())} a day, before costs {eur(bt['gross'].sum())}", GREEN)}
{kpi("Days with a loss", str(int((bt['realized'] < 0).sum())), f"Worst: {eur(bt['realized'].min())}", RED)}
</div>
{card("What the battery would have earned after costs, added up", track_chart)}
{card("Each forecast, the same battery", compare_table(bt_cmp, True, m) + "<p class='note'>Difference to the ensemble "
      "per day, p: Newey-West, Holm for the three.</p>")}
{card(f"Share of perfect foresight by month ({label})", month_chart)}""",
        "Risk": f"""
<div class='kpis'>
{kpi(f"Days below the 1 in 20 floor ({label})", f"{k / n:.1%}", f"{k} of {n} days, target 5%", RED)}
{kpi("Kupiec test", f"p = {kupiec_p(k, n):.2f}", "Is the share of days below the floor 5%?", GREY)}
{kpi("Average expected", eur(bt['expected'].mean()), "Per day", GREEN)}
{kpi("Average earned", eur(bt['realized'].mean()), "Per day", ORANGE)}
</div>
{card("Expected revenue, the 1 in 20 floor and what the battery earned (red: below the floor)", risk_chart)}""",
    }
    return live, back, {"lv": lv, "pnl": pnl, "n": n}


pages = {m: model_pages(m) for m in MODELS}
ens = pages["ensemble"][2]

# fees and wear, from cost_backtest.py (ensemble plan)
bt_dates = cmp_days.loc[~cmp_days["live"], "date"]
bt_span = f"{bt_dates.min():%d %b %Y} to {bt_dates.max():%d %b %Y}"
cs = pd.read_csv("results/cost_summary.csv")
case_names = {"none": "No costs", "main": f"Fee + wear {WEAR:.0f} €/MWh", "wear 10": "Fee + wear 10 €/MWh",
              "wear 40": "Fee + wear 40 €/MWh", "with tariffs": f"Fee + wear {WEAR:.0f} €/MWh + Energinet's tariffs"}
cost_rows = "".join(
    f"<tr><td>{case_names[r.case]}</td><td>{r.plan}</td><td class='n'>{eur(r.cost)}</td><td class='n'><b>{eur(r.net)}</b></td>"
    f"<td class='n'>{r.sold_per_day:.2f}</td><td class='n'>{r.days_no_trade}</td><td class='n'>{r.loss_days}</td>"
    f"<td class='n'>{'' if np.isnan(r.p) else f'{r.diff_per_day:+.2f} € (p {r.p:.3f})'}</td></tr>"
    for r in cs.itertuples())
main_after = cs[(cs["case"] == "main") & (cs["plan"] == "after the fact")].iloc[0]
main_in = cs[(cs["case"] == "main") & (cs["plan"] == "in the plan")].iloc[0]
gross_total = cs[cs["case"] == "none"].iloc[0]

# loss limit, from limit_backtest.py (ensemble plan)
lim = pd.read_csv("results/limit_summary.csv")
lim_rows = "".join(
    f"<tr><td>{'None' if r.limit == 'none' else str(r.limit) + ' €'}</td><td class='n'>{r.days_bound}</td>"
    f"<td class='n'>{(r.share_of_no_limit - 1) * 100:+.1f}%</td>"
    f"<td class='n'>{'' if r.limit == 'none' else ('< 0.001' if r.p < 0.001 else f'{r.p:.3f}')}</td>"
    f"<td class='n'>{r.loss_days}</td><td class='n'>{eur(r.worst_day)}</td></tr>"
    for r in lim.itertuples())
lim2 = lim[lim["limit"] != "none"]
fig = go.Figure(go.Bar(x=[f"{L} €" for L in lim2["limit"]], y=(lim2["share_of_no_limit"] - 1) * 100,
                       marker=dict(color=RED, cornerradius=4), width=0.5,
                       text=[f"{d} days" for d in lim2["days_bound"]], textposition="outside", cliponaxis=False,
                       hovertemplate="Limit %{x}: %{y:.1f}% revenue<extra></extra>"))
fig.update_yaxes(ticksuffix="%")
fig.update_xaxes(title_text="Loss limit")
limit_chart = style(fig, 300)

updated = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
per_model = lambda page, tab: {m: pages[m][page][tab] for m in MODELS}

live_tabs = {
    "Plan": per_model(0, "Plan"),
    "P&L": per_model(0, "P&L"),
    "Stress tests": per_model(0, "Stress tests"),
    "Method": f"""
{card("How it works", f'''
<p>Pick the forecast at the top: the ensemble (the default, the average of BMT-X, LEAR-X and XGBoost-X) or one model
alone, all from my <a href="https://github.com/jacobazu/dk1-price-forecasting">DK1 price forecasts</a> (R), made before
the noon auction the day before. The plan, P&L, risk and stress tests then use that forecast. The cost and loss limit
backtests are for the ensemble.</p>
<p>The plan is a mixed-integer program (scipy): 2 MWh / 1 MW, 90% round trip, one cycle a day. It includes the
Nord Pool fee and {WEAR:.0f} €/MWh wear, so it only trades when the spread pays for them. Without costs it gives the same
plan as the R version on 363 of 375 days.</p>
<p>Risk: past days' 24-hour forecast errors, scaled by an EWMA of their volatility, run through the plan.</p>
<p>The P&L counts from {LAUNCH:%d %b %Y}.</p>''')}""",
}

backtest_tabs = {
    "Track record": per_model(1, "Track record"),
    "Risk": per_model(1, "Risk"),
    "Costs": f"""
<div class='kpis'>
{kpi("Before costs", eur(gross_total['net']), f"{gross_total['sold_per_day']:.2f} MWh sold a day", GREY)}
{kpi("Costs", eur(main_in['cost']), f"{main_in['cost'] / main_in['revenue']:.0%} of the revenue", RED)}
{kpi("After costs", eur(main_in['net']), f"{eur(main_in['net_per_day'])} a day", GREEN)}
{kpi("Days it doesn't trade", str(main_in['days_no_trade']), f"Loss days {main_after['loss_days']} &rarr; {main_in['loss_days']}", BLUE)}
</div>
{card(f"Fees and wear, {bt_span}, ensemble plan",
      "<table><tr><th>Costs</th><th>Plan</th><th class='n'>Costs</th><th class='n'>After costs</th>"
      "<th class='n'>MWh sold a day</th><th class='n'>Days no trade</th><th class='n'>Loss days</th>"
      f"<th class='n'>In the plan vs after (per day)</th></tr>{cost_rows}</table>"
      "<p>After the fact: costs taken off afterwards. In the plan: it only trades when the spread pays for them. "
      "At 20 €/MWh wear the total is the same, but loss days halve. The higher the costs, the more it pays to plan "
      "with them. Wear is an assumption, sources in the README. p: Newey-West.</p>")}""",
    "Loss limit": f"""
<div class='grid2'>
{card("Revenue given up for each loss limit", limit_chart)}
{card(f"Loss limit backtest, {bt_span}, ensemble plan",
      "<table><tr><th>Limit</th><th class='n'>Days it binds</th><th class='n'>Revenue</th><th class='n'>p</th>"
      f"<th class='n'>Loss days</th><th class='n'>Worst day</th></tr>{lim_rows}</table>"
      "<p>The limit is on the average of the worst 5% of scenarios. It costs more than it saves: losses are rare, "
      "and the days it hits are the volatile ones, which pay the most. Before fees and wear.</p>")}
</div>""",
}


def render(title, tabs, link, banner=""):
    nav = "".join(f"<button data-tab='t{i}'{' class=active' if i == 0 else ''}>{k}</button>"
                  for i, k in enumerate(tabs))
    # a tab is the same for every forecast, or one block per forecast
    blocks = lambda v: v if isinstance(v, str) else "".join(f"<div class='m m-{m}'>{v[m]}</div>" for m in MODELS)
    cls = lambda i, v: " ".join(c for c in ["active" if i == 0 else "", "shared" if isinstance(v, str) else ""] if c)
    panes = "".join(f"<section id='t{i}' class='{cls(i, v)}'>{blocks(v)}</section>"
                    for i, v in enumerate(tabs.values()))
    picker = "".join(f"<button data-model='{m}'{' class=active' if m == 'ensemble' else ''}>{LABELS[m]}</button>"
                     for m in MODELS)
    show = " ".join(f"body[data-model={m}] .m-{m} {{ display: block; }}" for m in MODELS)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="{PLOTLY_JS}"></script>
<style>
  body {{ margin: 0; background: #faf6f1; color: {INK}; font: 15px/1.5 {FONT}; }}
  header {{ background: #fff; border-bottom: 1px solid #efe6dc; padding: 0 20px; display: flex; flex-wrap: wrap;
           align-items: center; gap: 4px 24px; }}
  header h1 {{ font-size: 17px; font-weight: 600; margin: 14px 0; }}
  nav {{ display: flex; flex-wrap: wrap; }}
  nav button {{ font: 500 14px {FONT}; color: {GREY}; background: none; border: 0; padding: 14px 10px; cursor: pointer; }}
  nav button.active {{ color: {INK}; box-shadow: inset 0 -2px 0 {ORANGE}; }}
  header .links {{ margin-left: auto; font-size: 13px; display: flex; align-items: center; gap: 16px; }}
  header .links a {{ color: {GREY}; }}
  header .links svg {{ display: block; }}
  .banner {{ background: #fff7ed; border-bottom: 1px solid #fed7aa; color: #9a3412; font-size: 14px;
            padding: 8px 20px; }}
  main {{ max-width: 1280px; margin: 0 auto; padding: 18px 16px 40px; }}
  .models {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 16px; }}
  .models span {{ color: {GREY}; font-size: 13px; margin-right: 4px; }}
  .models button {{ font: 600 13px {FONT}; color: {INK}; background: #fff7ed; border: 1px solid #fed7aa;
                   border-radius: 999px; padding: 6px 16px; cursor: pointer; }}
  .models button.active {{ color: #fff; background: {ORANGE}; border-color: {ORANGE}; }}
  .m {{ display: none; }}
  {show}
  section {{ display: none; }}
  section.active {{ display: block; }}
  .card {{ background: #fff; border: 1px solid #efe6dc; border-radius: 16px; box-shadow: 0 4px 14px rgba(120,72,20,.06);
          padding: 14px 16px; margin-bottom: 16px; min-width: 0; }}
  .card-title {{ font-weight: 600; margin-bottom: 8px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }}
  .kpi {{ border-left: 4px solid var(--accent); }}
  .kpi-label {{ color: {GREY}; font-size: 13px; }}
  .kpi-value {{ font-size: 24px; font-weight: 600; margin: 2px 0; }}
  .kpi-sub {{ color: {GREY}; font-size: 13px; }}
  .grid2 {{ display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 16px; }}
  .grid2 > * {{ min-width: 0; }}
  @media (max-width: 900px) {{ .grid2 {{ grid-template-columns: 1fr; }} }}
  table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
  th, td {{ text-align: left; padding: 6px 8px 6px 0; border-bottom: 1px solid #f1ebe4; }}
  th {{ color: {GREY}; font-weight: 500; font-size: 13px; }}
  tr.sel td {{ font-weight: 600; }}
  .n {{ text-align: right; font-variant-numeric: tabular-nums; }}
  p {{ color: #3b3f45; }}
  .note {{ color: {GREY}; font-size: 13px; max-width: 900px; }}
  a {{ color: #c2410c; }}
  footer {{ color: {GREY}; font-size: 12px; text-align: center; padding-bottom: 24px; }}
</style>
</head>
<body data-model="ensemble">
<header><h1>{title}</h1><nav>{nav}</nav>
<span class="links">{link}<a href="https://github.com/jacobazu/dk1-battery-trade" aria-label="GitHub">{GITHUB_ICON}</a></span></header>
{banner}
<main><div class="models"><span>Forecast</span>{picker}</div>{panes}</main>
<footer>Updated {updated}</footer>
<script>
const resize = () => {{
  // no forecast buttons on tabs that are the same for every forecast
  document.querySelector(".models").style.display = document.querySelector("section.active.shared") ? "none" : "";
  document.querySelectorAll("section.active .plotly-graph-div").forEach(g => {{ if (g.offsetParent) Plotly.Plots.resize(g); }});
}};
document.querySelectorAll("nav button").forEach(b => b.onclick = () => {{
  document.querySelectorAll("nav button, section").forEach(e => e.classList.remove("active"));
  b.classList.add("active");
  document.getElementById(b.dataset.tab).classList.add("active");
  resize();
}});
// the chosen forecast, kept when going between the live and backtest pages
const pick = m => {{
  document.body.dataset.model = m;
  document.querySelectorAll(".models button").forEach(b => b.classList.toggle("active", b.dataset.model === m));
  try {{ localStorage.setItem("battery-model", m); }} catch (e) {{}}
  resize();
}};
document.querySelectorAll(".models button").forEach(b => b.onclick = () => pick(b.dataset.model));
let saved = null;
try {{ saved = localStorage.getItem("battery-model"); }} catch (e) {{}}
if (saved && document.querySelector(`.models button[data-model="${{saved}}"]`)) pick(saved);
</script>
</body>
</html>
"""


Path("docs").mkdir(exist_ok=True)
Path("docs/index.html").write_text(
    render("DK1 battery trading", live_tabs, "<a href='backtest.html'>Backtest</a>"), encoding="utf-8")
Path("docs/backtest.html").write_text(
    render("DK1 battery trading: backtest", backtest_tabs, "<a href='index.html'>&larr; Live</a>",
           f"<div class='banner'>Backtest, {bt_span}. Each day was planned on a forecast made without that day's "
           f"prices, but the forecasts were made afterwards. The live P&L is on the "
           f"<a href='index.html'>main page</a>.</div>"), encoding="utf-8")
print(f"docs/index.html: {len(ens['lv'])} live days, P&L {eur(ens['pnl'].iloc[-1]) if len(ens['lv']) else '-'} "
      f"(ensemble), next plan {latest:%d %b %Y}")
print(f"docs/backtest.html: {ens['n']} backtest days")
