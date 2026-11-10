"""Risk of a plan in pictures and plain words: the trade's densities, the order ticket and the backtest checks."""
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy.stats import gaussian_kde

from risk import ALPHA

INK, GREY, RED, BLUE, ORANGE, GREEN, BEIGE = "#1f2328", "#6b7280", "#dc2626", "#0ea5e9", "#f97316", "#16a34a", "#cfc6bb"
HATCH = dict(shape="/", fgcolor=RED, bgcolor="rgba(220,38,38,0.08)", size=6, solidity=0.3)


def legs(f, q, S, cost):
    """Per scenario: what the buying costs, what the selling earns and the profit kept, in euro."""
    P = f + S
    buy, sell = q < 0, q > 0
    paid = -(P[:, buy] @ q[buy])
    got = P[:, sell] @ q[sell]
    return {"paid": paid, "got": got, "profit": got - paid - cost,
            "buy_mwh": -q[buy].sum(), "sell_mwh": q[sell].sum()}


def round5(x):
    return int(5 * round(x / 5))


def plain_line(expected, floor, p_loss):
    """One sentence a trader without a model background can read."""
    bad = (f"On a bad day (1 in 20) it's closer to {round5(floor)} €." if floor >= 0 else
           f"On a bad day (1 in 20) we'd lose about {round5(-floor)} €.")
    n = round(p_loss * 100)
    chance = "less than 1 in 100" if n == 0 else f"{n} in 100"
    return f"We expect to make about {round5(expected)} €. {bad} Chance of losing money: {chance}."


def promise_strip(d, w=11, g=4, h=46):
    """Last days as tiny bars: grey from the bad case up to expected, a dot for what it earned (red below the bad case)."""
    if len(d) == 0:
        return ""
    lo = min(d["floor"].min(), d["realized"].min()); hi = max(d["expected"].max(), d["realized"].max())
    y = lambda v: h - 3 - (v - lo) / (hi - lo + 1e-9) * (h - 6)
    out = ""
    for i, r in enumerate(d.itertuples()):
        x = i * (w + g); miss = r.realized < r.floor
        out += (f"<g><title>{r.date:%a %d %b}: earned {r.realized:,.0f} €, expected {r.expected:,.0f}, bad day {r.floor:,.0f}</title>"
                f"<rect x='{x}' y='{y(r.expected):.1f}' width='{w}' height='{max(y(r.floor) - y(r.expected), 2):.1f}' rx='2' fill='#e7ded3'/>"
                f"<circle cx='{x + w / 2}' cy='{y(r.realized):.1f}' r='3.6' fill='{RED if miss else INK}'/></g>")
    W = len(d) * (w + g) - g
    return f"<svg class='pstrip' viewBox='0 0 {W} {h}' width='{W}' height='{h}'>{out}</svg>"


def odds(k, n):
    """'1 in 14' from k of n days."""
    return "never" if k == 0 else f"1 in {round(n / k)}"


def _kde(x, grid):
    if np.ptp(x) < 1e-9:
        return np.zeros_like(grid)
    return gaussian_kde(x)(grid)


def _side_density(fig, x0, width, values, tail, colour, name, col=1):
    """A density drawn sideways from x0, its bad tail hatched. tail: 'high' or 'low' is bad."""
    lo, hi = np.percentile(values, [0.5, 99.5])
    pad = 0.15 * (hi - lo + 1)
    grid = np.linspace(lo - pad, hi + pad, 200)
    d = _kde(values, grid)
    d = d / d.max() * width if d.max() > 0 else d
    fig.add_trace(go.Scatter(x=np.r_[x0, x0 + d, x0], y=np.r_[grid[0], grid, grid[-1]], fill="toself", mode="lines",
                             line=dict(color=colour, width=1.5), fillcolor=_rgba(colour, 0.18), name=name, hoverinfo="skip", showlegend=False), row=1, col=col)
    cut = np.quantile(values, 1 - ALPHA if tail == "high" else ALPHA)
    keep = grid >= cut if tail == "high" else grid <= cut
    if keep.any():
        g, dd = grid[keep], d[keep]
        fig.add_trace(go.Scatter(x=np.r_[x0, x0 + dd, x0], y=np.r_[g[0], g, g[-1]], fill="toself", mode="lines",
                                 line=dict(width=0), fillpattern=HATCH, hoverinfo="skip", showlegend=False),
                      row=1, col=col)
    return grid, d, cut


def _rgba(hex_colour, a):
    h = hex_colour.lstrip("#")
    return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})"


def trade_chart(f, q, S, cost, label, windows):
    """Jacob's sketch: forecast price steps, sideways densities of the prices on the buy and sell hours, and the
    profit density on the right. Hatched: the worst 1 in 20."""
    L = legs(f, q, S, cost)
    P = f + S
    fig = make_subplots(rows=1, cols=2, column_widths=[0.74, 0.26], horizontal_spacing=0.07,
                        subplot_titles=("Price, €/MWh", "Profit kept, €"))
    step = np.arange(25)
    lo, hi = np.percentile(P, 5, axis=0), np.percentile(P, 95, axis=0)
    pad = lambda v: np.append(v, v[-1])
    fig.add_trace(go.Scatter(x=step, y=pad(lo), mode="lines", line=dict(width=0, shape="hv"), hoverinfo="skip",
                             showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=step, y=pad(hi), mode="lines", line=dict(width=0, shape="hv"), fill="tonexty",
                             fillcolor="rgba(107,114,128,0.10)", name="9 in 10 days inside", hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=step, y=pad(f), mode="lines", line=dict(color=INK, width=2, shape="hv"),
                             name=f"Forecast ({label})", hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=np.arange(24) + 0.5, y=f, mode="markers", marker=dict(size=18, color="rgba(0,0,0,0)"),
                             showlegend=False, customdata=np.c_[lo, hi],
                             hovertemplate="%{x|.0f}: %{y:.0f} €/MWh, 9 in 10 days %{customdata[0]:.0f}-"
                                           "%{customdata[1]:.0f}<extra></extra>"), row=1, col=1)

    for mask, colour, word, tail, title in [(q < 0, BLUE, "Buy", "high", "What we might pay"),
                                            (q > 0, ORANGE, "Sell", "low", "What we might get")]:
        if not mask.any():
            continue
        for a, b in windows(mask):
            fig.add_vrect(x0=a, x1=b, fillcolor=colour, opacity=0.10, line_width=0, layer="below", row=1, col=1)
        # one density per side: the average price over all its hours, weighted by the MWh
        w = np.abs(q[mask]) / np.abs(q[mask]).sum()
        avg = P[:, mask] @ w
        a, _ = windows(mask)[0]
        x0 = a + 0.1
        grid, d, cut = _side_density(fig, x0, 2.6, avg, tail, colour, title)
        fig.add_annotation(x=x0, y=grid[-1], yanchor="bottom", xanchor="left", showarrow=False, align="left",
                           text=f"<b>{title}</b><br>about {np.median(avg):.0f} €/MWh<br><span style='color:{RED}'>1 in 20: "
                                f"{'above' if tail == 'high' else 'below'} {cut:.0f}</span>",
                           font=dict(size=11, color=colour), bgcolor="rgba(255,255,255,0.8)", row=1, col=1)

    # profit density, sideways, from zero
    prof = L["profit"]
    grid, d, cut = _side_density(fig, 0, 1, prof, "low", GREEN, "Profit", col=2)
    exp = prof.mean()
    e_d = np.interp(exp, grid, d)
    fig.add_trace(go.Scatter(x=[0, e_d], y=[exp, exp], mode="lines", line=dict(color=INK, width=2), showlegend=False,
                             hovertemplate=f"Expected {exp:.0f} €<extra></extra>"), row=1, col=2)
    fig.add_annotation(x=e_d, y=exp, text=f"Expected {exp:.0f} €", showarrow=False, xanchor="left",
                       font=dict(size=11, color=INK), row=1, col=2)
    fig.add_annotation(x=np.interp(cut, grid, d), y=cut, text=f"Bad day (1 in 20) {cut:.0f} €", showarrow=False,
                       xanchor="left", yanchor="top", font=dict(size=11, color=RED), row=1, col=2)
    if grid[0] < 0 < grid[-1]:
        fig.add_hline(y=0, line=dict(color=BEIGE, width=1, dash="dot"), row=1, col=2)

    fig.update_xaxes(range=[0, 24], tickvals=list(range(0, 25, 3)), ticktext=[f"{h:02d}" for h in range(0, 25, 3)],
                     row=1, col=1)
    fig.update_xaxes(visible=False, range=[0, 1.9], row=1, col=2)
    fig.update_annotations(selector=dict(text="Price, €/MWh"), font=dict(size=12, color=GREY))
    fig.update_annotations(selector=dict(text="Profit kept, €"), font=dict(size=12, color=GREY))
    return fig, L


def ticket(f, q, L, cost, hours_of, windows):
    """Order ticket: each order around what we expect, on one shared scale of how far it can move."""
    rows = []
    if L["buy_mwh"] > 0:
        rows.append(("Buy", hours_of(windows(q < 0)), L["buy_mwh"], L["paid"], BLUE, "costs", "high"))
    if L["sell_mwh"] > 0:
        rows.append(("Sell", hours_of(windows(q > 0)), L["sell_mwh"], L["got"], ORANGE, "earns", "low"))
    rows.append(("Profit kept", f"after {cost:.0f} € fees and wear", None, L["profit"], GREEN, "keeps", "low"))
    qs = [(np.percentile(v, 5), v.mean(), np.percentile(v, 95)) for *_, v, _, _, _ in rows]
    reach = max(max(m - a, c - m) for a, m, c in qs) * 1.35  # room for the numbers at the ends
    pos = lambda d: 50 + d / reach * 50  # distance from expected, in % of the bar
    out = ""
    for (name, when, mwh, v, colour, verb, bad), (a, m, c) in zip(rows, qs):
        bad_end = (f"<span class='rbad' style='left:{pos(c - m) - 3:.1f}%'></span>" if bad == "high" else
                   f"<span class='rbad' style='left:{pos(a - m):.1f}%'></span>")
        out += (f"<div class='order'><div><b style='color:{colour}'>{name}</b> <span class='sub'>{when}"
                f"{f', {mwh:.1f} MWh' if mwh else ''}</span></div>"
                f"<div class='sub'>{verb} about <b>{m:,.0f} €</b></div>"
                f"<div class='rbar'><span class='rr' style='left:{pos(a - m):.1f}%;width:{pos(c - m) - pos(a - m):.1f}%;"
                f"background:{_rgba(colour, 0.35)}'></span>{bad_end}<span class='rm' style='left:50%;"
                f"background:{colour}'></span>"
                f"<span class='rl' style='right:{100 - pos(a - m) + 1:.1f}%'>{a:,.0f}</span>"
                f"<span class='rl' style='left:{pos(c - m) + 1:.1f}%'>{c:,.0f}</span></div></div>")
    key = (f"<div class='key'><span class='kd' style='background:{INK}'></span>expected <span class='kb'></span>9 in 10 "
           f"<span class='kd' style='background:{RED}'></span>bad side</div>")
    return f"<div class='ticket'>{out}</div>{key}"


def promise_chart(bt):
    """Backtest, each day: a line from the bad case up to expected, and what it earned as a dot."""
    miss = (bt["realized"] < bt["floor"]).to_numpy()
    xs, ys = [], []
    for r in bt.itertuples():
        xs += [r.date, r.date, None]
        ys += [r.floor, r.expected, None]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=BEIGE, width=2), name="Expected, down to a bad day",
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=bt["date"], y=bt["realized"], mode="markers", name="What it earned",
                             marker=dict(size=6, color=np.where(miss, RED, INK), opacity=0.85),
                             customdata=np.c_[bt["expected"], bt["floor"]],
                             hovertemplate="%{x|%d %b %Y}: earned %{y:.0f} €<br>expected %{customdata[0]:.0f} €, "
                                           "bad day %{customdata[1]:.0f} €<extra></extra>"))
    fig.update_yaxes(ticksuffix=" €")
    return fig


def surprise_scatter(bt):
    """How far a bad day could fall (expected - floor) against what happened (earned - expected)."""
    room = (bt["expected"] - bt["floor"]).to_numpy()
    surprise = (bt["realized"] - bt["expected"]).to_numpy()
    miss = surprise < -room
    fig = go.Figure()
    m = room.max() * 1.05
    fig.add_trace(go.Scatter(x=[0, m], y=[0, -m], mode="lines", line=dict(color=RED, width=1.5, dash="dot"),
                             name="The bad case", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=room, y=surprise, mode="markers", name="A day",
                             marker=dict(size=6, color=np.where(miss, RED, INK), opacity=0.7),
                             customdata=bt["date"].dt.strftime("%d %b %Y"),
                             hovertemplate="%{customdata}: could fall %{x:.0f} €, came in %{y:+.0f} €<extra></extra>"))
    fig.add_hline(y=0, line=dict(color=BEIGE, width=1))
    fig.update_xaxes(title_text="How far a bad day could fall, €", rangemode="tozero")
    fig.update_yaxes(title_text="Earned minus expected, €")
    return fig


def surprise_groups(bt, band=25):
    """Surprise (earned - expected) by calm, normal and risky days, a third of the days each."""
    room = bt["expected"] - bt["floor"]
    s = bt["realized"] - bt["expected"]
    cuts = np.quantile(room, [1 / 3, 2 / 3])
    groups = {"Calm days": room <= cuts[0], "Normal days": (room > cuts[0]) & (room <= cuts[1]),
              "Risky days": room > cuts[1]}
    stats = {k: {"n": int(g.sum()), "near": float((s[g].abs() <= band).mean()),
                 "below": float((bt["realized"][g] < bt["floor"][g]).mean())} for k, g in groups.items()}
    lo, hi = np.percentile(s, [1, 99])
    grid = np.linspace(lo, hi, 300)
    fig = go.Figure()
    fig.add_vrect(x0=-band, x1=band, fillcolor=GREEN, opacity=0.08, line_width=0, layer="below")
    for (k, g), colour in zip(groups.items(), [GREEN, GREY, RED]):
        fig.add_trace(go.Scatter(x=grid, y=_kde(s[g].to_numpy(), grid), mode="lines", line=dict(color=colour, width=2.5),
                                 name=f"{k}: {stats[k]['near']:.0%} within ±{band} €", hoverinfo="skip"))
    fig.add_vline(x=0, line=dict(color=BEIGE, width=1))
    fig.update_xaxes(title_text="Earned minus expected, €")
    fig.update_yaxes(showticklabels=False, title_text="How often")
    return fig, stats, cuts


def shape(bt, band=25):
    """The three before/after numbers: peakedness, left tail, skew."""
    s = (bt["realized"] - bt["expected"]).to_numpy()
    z = (s - s.mean()) / s.std()
    return {"near": float((np.abs(s) <= band).mean()), "below": float((bt["realized"] < bt["floor"]).mean()),
            "skew": float((z ** 3).mean())}
