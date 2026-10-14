# DK1 battery trading

Python on top of my [DK1 price forecasts](https://github.com/jacobazu/dk1-price-forecasting) (R). It plans a 2 MWh / 1 MW battery from each day's forecast and measures the risk of the plan. On the dashboard you pick the forecast: the ensemble (the default) or one of the three models alone, to compare.

Dashboard: [jacobazu.github.io/dk1-battery-trade](https://jacobazu.github.io/dk1-battery-trade/)

Methods: [one page (PDF)](notes/method.pdf)

## The real test

A backtest shows that the battery would have earned money. It doesn't show that it will. I made my choices with the backtest period in view, so the backtest is probably a bit too good. The live plans are made from forecasts saved before the auction, so they can't be adjusted afterwards. That's the interesting part, so the dashboard's main page only shows the P&L since launch on 13 Oct 2026. The backtest has its own page.

## Files

- `battery.py`: the plan. Same as the R version on 363 of 375 days, the other 12 are ties.
- `risk.py`: revenue at risk, same method as R. Matches on 325 of 327 days.
- `limit_backtest.py`: a loss limit. It costs more than it saves for this battery.
- `stress.py`: stress tests on the plan.
- `costs.py`, `cost_backtest.py`: fees and battery wear. They take 17% of the revenue. With the costs in the plan it only trades when the spread pays for them, which halves the loss days.
- `dashboard.py`: makes both pages. It runs every morning on GitHub Actions.

## Where the costs come from

- Nord Pool fee: 0.055 €/MWh bought or sold ([fee schedule 2026](https://www.nordpoolgroup.com/4a7ad8/globalassets/trading-and-services/nord-pool-fee-schedule-2026-nordic-and-baltic-market.pdf)). The yearly fee is left out.
- Wear: 20 €/MWh sold, my assumption. A system cost about $177/kWh in Europe in 2025 ([BNEF](https://www.energy-storage.news/?p=92133)). Over about 6,000 full cycles, also my assumption, that is about $30/MWh. The backtest also tries 10 and 40. Pricing wear per MWh in the plan is how [Modo Energy](https://ercotforecastdocs.modoenergy.com/docs/battery-degradation) does it.
- Energinet's tariffs, side case only: 11.5 øre/kWh charging, 1.03 øre/kWh discharging ([tariff catalogue 2026](https://www.energinet.dk/media/ikylsqle/energinets-tarifkatalog-2026.pdf)). It isn't clear a battery like this pays them. Local grid tariffs and taxes are left out.
- DKK to EUR at 7.46, the krone's peg.
