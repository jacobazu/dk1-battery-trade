"""Dashboard for the battery. docs/index.html is the live page: tomorrow's plan, the P&L since launch and the
stress tests. docs/backtest.html has the backtest: track record, risk and the loss limit.

Runs daily after the price repo has saved tomorrow's forecast.
"""
from datetime import datetime, timezone
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from scipy.stats import binom

from battery import SETUP, battery_schedule
from data import load_all, wide
from risk import ALPHA, error_matrix, error_scenarios, ewma_vol, has_history, tail_stats
from stress import stress_tests

ORANGE, GREEN, RED, BLUE = "#f97316", "#16a34a", "#dc2626", "#0ea5e9"
INK, GREY, LINE, GRID, BEIGE = "#1f2328", "#6b7280", "#e5ddd3", "#f1ebe4", "#cfc6bb"
FONT = "IBM Plex Sans, Segoe UI, Helvetica Neue, Arial, sans-serif"
PLOTLY_JS = "https://cdn.jsdelivr.net/npm/plotly.js-dist-min@4.1.1/plotly.min.js"
LAUNCH = pd.Timestamp("2026-10-13")  # first day traded on a live forecast


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


def style(fig, height):
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=10, b=10), font=dict(family=FONT, color=GREY, size=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
        legend=dict(orientation="h", x=0, y=-0.15, font=dict(color=INK)),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor="#efe6dc", font=dict(color=INK, family=FONT)))
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=LINE, color=GREY)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=BEIGE, color=GREY)
    return fig.to_html(full_html=False, include_plotlyjs=False, config=dict(displayModeBar=False, responsive=True))


# every day with enough past errors: plan, risk and what it earned
fc = load_all()
dates, E = error_matrix(fc)
sig = ewma_vol(E)
F, A = wide(fc, "ensemble"), wide(fc, "actual")

rows = []
for i in range(len(dates)):
    if not has_history(dates, E, i):
        continue
    f, a = F[i], A[i]
    q = battery_schedule(f)
    S = error_scenarios(dates, E, sig, i)
    st = tail_stats(f @ q + S @ q)
    known = not np.isnan(a).any()
    rows.append({"date": pd.Timestamp(dates[i]), "live": pd.Timestamp(dates[i]) >= LAUNCH,
                 "expected": st["expected"], "floor": st["floor"],
                 "realized": a @ q if known else np.nan,
                 "perfect": battery_schedule(a) @ a if known else np.nan,
                 "q": q, "f": f, "S": S})
days = pd.DataFrame(rows)
done = days.dropna(subset=["realized"])
nxt = days.iloc[-1]

# tomorrow
f, q, S = nxt["f"], nxt["q"], nxt["S"]
q = np.where(np.abs(q) < 1e-6, 0, q)
lo, hi = np.percentile(f + S, 5, axis=0), np.percentile(f + S, 95, axis=0)
fill = battery_fill(q)
stress = stress_tests(f, q, S)
worst_name, worst_val = min(stress.items(), key=lambda kv: kv[1])

x, step = np.arange(24) + 0.5, np.arange(25)
pad = lambda v: np.append(v, v[-1])
fig = go.Figure()
fig.add_trace(go.Scatter(x=step, y=pad(lo), mode="lines", line=dict(width=0, shape="hv"), hoverinfo="skip",
                         showlegend=False))
fig.add_trace(go.Scatter(x=step, y=pad(hi), mode="lines", line=dict(width=0, shape="hv"), fill="tonexty",
                         fillcolor="rgba(107,114,128,0.15)", name="90% range", hoverinfo="skip"))
fig.add_trace(go.Scatter(x=step, y=pad(f), mode="lines", line=dict(color=INK, width=2, shape="hv"),
                         name="Forecast", hoverinfo="skip"))
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
fig.add_trace(go.Scatter(x=step, y=fill, mode="lines", line=dict(color=GREY, width=2), name="Stored",
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
fig = go.Figure(go.Bar(y=names, x=vals, orientation="h", marker=dict(color=[RED if v < 0 else BEIGE for v in vals],
                                                                     cornerradius=4),
                       text=[eur(v) for v in vals], textposition="outside", cliponaxis=False, width=0.6,
                       hovertemplate="%{y}: %{x:.0f} €<extra></extra>"))
fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
fig.update_xaxes(ticksuffix=" €", zeroline=True, zerolinecolor=BEIGE, showgrid=True, gridcolor=GRID)
stress_chart = style(fig, 330)

# live: every day traded on a live forecast since launch
lv, bt = done[done["live"]], done[~done["live"]]
pnl = lv["realized"].cumsum()
drawdown = (pnl - np.maximum.accumulate(np.r_[0, pnl.to_numpy()])[1:]).min() if len(lv) else 0.0
lv_miss = int((lv["realized"] < lv["floor"]).sum())

# both charts start at 0 the day before launch and show at least the first week
DAY = pd.Timedelta(days=1)
start = LAUNCH - DAY
x_range = [start - DAY / 2, max(lv["date"].max() if len(lv) else LAUNCH, LAUNCH + 6 * DAY) + DAY / 2]
x_axis = dict(tickformat="%d %b", range=x_range, dtick=DAY / pd.Timedelta(milliseconds=1) * (1 if len(lv) < 15 else 7))
cum_x = [start] + list(lv["date"])
fig = go.Figure()
fig.add_trace(go.Scatter(x=cum_x, y=[0] + list(lv["perfect"].cumsum()), mode="lines+markers", name="Perfect foresight",
                         line=dict(color=BEIGE, width=2, dash="dot"), hovertemplate="%{y:,.0f} €"))
fig.add_trace(go.Scatter(x=cum_x, y=[0] + list(pnl), mode="lines+markers", name="P&L", line=dict(color=ORANGE, width=3),
                         hovertemplate="%{y:,.0f} €"))
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
    f"<td class='n'><b>{eur(r.realized)}</b></td><td class='n'>{eur(r.perfect)}</td>"
    f"<td>{'below the floor' if r.realized < r.floor else ''}</td></tr>"
    for r in lv.iloc[::-1].itertuples())

# backtest track record
cum = bt.assign(battery=bt["realized"].cumsum(), perfect_c=bt["perfect"].cumsum())
fig = go.Figure()
fig.add_trace(go.Scatter(x=cum["date"], y=cum["perfect_c"], mode="lines", line=dict(color=BEIGE, width=2),
                         name="Perfect foresight", hovertemplate="%{y:,.0f} €"))
fig.add_trace(go.Scatter(x=cum["date"], y=cum["battery"], mode="lines", line=dict(color=ORANGE, width=2),
                         name="Plan on the forecast", hovertemplate="%{y:,.0f} €"))
fig.update_yaxes(ticksuffix=" €")
track_chart = style(fig, 380)

month = bt.groupby(bt["date"].dt.to_period("M")).agg(realized=("realized", "sum"), perfect=("perfect", "sum"))
fig = go.Figure(go.Bar(x=month.index.strftime("%b %Y"), y=month["realized"] / month["perfect"] * 100,
                       marker=dict(color=ORANGE, cornerradius=4), width=0.6,
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

# loss limit, from limit_backtest.py
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

# pages
n, m = len(bt), int(miss.sum())
bt_span = f"{bt['date'].min():%d %b %Y} to {bt['date'].max():%d %b %Y}"
updated = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")


def kpi(label, value, sub, accent):
    return (f"<div class='card kpi' style='--accent:{accent}'><div class='kpi-label'>{label}</div>"
            f"<div class='kpi-value'>{value}</div><div class='kpi-sub'>{sub}</div></div>")


def card(title, body, extra=""):
    return f"<div class='card {extra}'><div class='card-title'>{title}</div>{body}</div>"


day = nxt["date"].strftime("%a %d %b")
backtest_link = "<a class='bt-link' href='backtest.html'>Want to see the backtest? Click here &rarr;</a>"
live_tabs = {
    "Plan": f"""
<div class='kpis'>
{kpi(f"Buy {day}", hours(windows(q < 0)), f"{-q[q < 0].sum():.1f} MWh", BLUE)}
{kpi("Sell", hours(windows(q > 0)), f"{q[q > 0].sum():.1f} MWh", ORANGE)}
{kpi("Expected revenue", eur(nxt['expected']), f"At the forecast prices: {eur(f @ q)}", GREEN)}
{kpi("1 day in 20 below", eur(nxt['floor']), f"Worst stress test: {escape(worst_name.lower())}, {eur(worst_val)}", RED)}
</div>
<div class='grid2'>
{card(f"Price forecast for {day}, with the hours to buy and sell", plan_chart + fill_chart)}
{card("Orders", f"<table><tr><th>Hour</th><th>Order</th><th class='n'>MWh</th><th class='n'>€/MWh</th><th class='n'>90% range</th></tr>{orders}</table>")}
</div>""",
    "P&L": f"""
<div class='kpis'>
{kpi("P&L since launch", eur(pnl.iloc[-1]) if len(lv) else "-", f"{len(lv)} day{'s' * (len(lv) != 1)} since {LAUNCH:%d %b %Y}", GREEN)}
{kpi("Last day", eur(lv['realized'].iloc[-1]) if len(lv) else "-", f"{lv['date'].iloc[-1]:%a %d %b}" if len(lv) else "", ORANGE)}
{kpi("Share of perfect foresight", f"{lv['realized'].sum() / lv['perfect'].sum():.0%}" if len(lv) else "-", "What a plan on the real prices would make", BLUE)}
{kpi("Max drawdown", eur(drawdown), f"Days below the 1 in 20 floor: {lv_miss} of {len(lv)}", RED)}
</div>
<div class='grid2'>
<div>{card("P&L since launch, added up", pnl_chart)}{card("P&L per day", daily_chart)}</div>
{card("Every day since launch", "<table><tr><th>Day</th><th class='n'>Expected</th><th class='n'>1 in 20 floor</th>"
      f"<th class='n'>Earned</th><th class='n'>Perfect</th><th></th></tr>{live_rows}</table>"
      "<p class='note'>Each plan is made the day before from the live forecast and paid the actual day-ahead price. "
      "Revenue before fees and battery wear.</p>")}
</div>
<p>{backtest_link}</p>""",
    "Stress tests": f"""
{card(f"What {day} earns if it goes like this", stress_chart)}
<p class='note'>Worst of the last 250 days: the plan put through the worst past forecast error. The peak doesn't
come: the selling hours fall to the day's median price. Negative prices: -50 €/MWh from 11:00 to 15:00.
Errors 3 times as big: the average of the worst 5% of scenarios with errors three times as big.</p>""",
    "Method": f"""
{card("How it works", f'''
<p>The forecast is the ensemble from my <a href="https://github.com/jacobazu/dk1-price-forecasting">DK1 price
forecasts</a> (R), made before the day-ahead auction at noon the day before.</p>
<p>The plan is a mixed-integer linear program in Python (scipy). It buys and sells to make the most at the
forecast prices. The battery is 2 MWh / 1 MW with 90% round trip efficiency and one cycle a day. The plan gives
the same result as the R version on 363 of 375 backtest days. On the other 12, two plans are equally good.</p>
<p>The risk comes from the 24-hour forecast errors of up to 250 past days, scaled by an EWMA of the error
volatility (lambda 0.94). It matches the R version on 325 of 327 days.</p>
<p>The P&L counts from {LAUNCH:%d %b %Y}, the first day traded on a live forecast. {backtest_link}</p>''')}""",
}

backtest_tabs = {
    "Track record": f"""
<div class='kpis'>
{kpi("Share of perfect foresight", f"{bt['realized'].sum() / bt['perfect'].sum():.0%}", f"{n} days", ORANGE)}
{kpi("Earned in total", eur(bt['realized'].sum()), f"{eur(bt['realized'].mean())} a day", GREEN)}
{kpi("Days with a loss", str(int((bt['realized'] < 0).sum())), f"Worst: {eur(bt['realized'].min())}", RED)}
</div>
{card("What the battery would have earned, added up", track_chart)}
{card("Share of perfect foresight by month", month_chart)}""",
    "Risk": f"""
<div class='kpis'>
{kpi("Days below the 1 in 20 floor", f"{m / n:.1%}", f"{m} of {n} days, target 5%", RED)}
{kpi("Kupiec test", f"p = {kupiec_p(m, n):.2f}", "Is the share of days below the floor 5%?", GREY)}
{kpi("Average expected", eur(bt['expected'].mean()), "Per day", GREEN)}
{kpi("Average earned", eur(bt['realized'].mean()), "Per day", ORANGE)}
</div>
{card("Expected revenue, the 1 in 20 floor and what the battery earned (red: below the floor)", risk_chart)}""",
    "Loss limit": f"""
<div class='grid2'>
{card("Revenue given up for each loss limit", limit_chart)}
{card(f"Loss limit backtest, {bt_span}",
      "<table><tr><th>Limit</th><th class='n'>Days it binds</th><th class='n'>Revenue</th><th class='n'>p</th>"
      f"<th class='n'>Loss days</th><th class='n'>Worst day</th></tr>{lim_rows}</table>"
      "<p>The limit is on the average of the worst 5% of scenarios. It costs more than it saves for this "
      "battery. Losses are rare, and the days the limit hits are the volatile days, which pay the most.</p>")}
</div>""",
}


def render(title, tabs, link, banner=""):
    nav = "".join(f"<button data-tab='t{i}'{' class=active' if i == 0 else ''}>{k}</button>"
                  for i, k in enumerate(tabs))
    panes = "".join(f"<section id='t{i}'{' class=active' if i == 0 else ''}>{v}</section>"
                    for i, v in enumerate(tabs.values()))
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
  header .links {{ margin-left: auto; font-size: 13px; display: flex; gap: 16px; }}
  header .links a {{ color: {GREY}; }}
  .banner {{ background: #fff7ed; border-bottom: 1px solid #fed7aa; color: #9a3412; font-size: 14px;
            padding: 8px 20px; }}
  main {{ max-width: 1280px; margin: 0 auto; padding: 18px 16px 40px; }}
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
  .n {{ text-align: right; font-variant-numeric: tabular-nums; }}
  p {{ color: #3b3f45; }}
  .note {{ color: {GREY}; font-size: 13px; max-width: 900px; }}
  a {{ color: #c2410c; }}
  .bt-link {{ font-weight: 500; }}
  footer {{ color: {GREY}; font-size: 12px; text-align: center; padding-bottom: 24px; }}
</style>
</head>
<body>
<header><h1>{title}</h1><nav>{nav}</nav>
<span class="links">{link}<a href="https://github.com/jacobazu/dk1-battery-trade">GitHub</a></span></header>
{banner}
<main>{panes}</main>
<footer>Updated {updated}</footer>
<script>
document.querySelectorAll("nav button").forEach(b => b.onclick = () => {{
  document.querySelectorAll("nav button, section").forEach(e => e.classList.remove("active"));
  b.classList.add("active");
  const s = document.getElementById(b.dataset.tab);
  s.classList.add("active");
  s.querySelectorAll(".plotly-graph-div").forEach(g => Plotly.Plots.resize(g));
}});
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
print(f"docs/index.html: {len(lv)} live days, P&L {eur(pnl.iloc[-1]) if len(lv) else '-'}, "
      f"next plan {nxt['date']:%d %b %Y}")
print(f"docs/backtest.html: {n} backtest days")
