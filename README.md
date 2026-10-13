# DK1 battery trading

Python on top of my [DK1 price forecasts](https://github.com/jacobazu/dk1-price-forecasting) (R). It plans a 2 MWh / 1 MW battery from each day's forecast and measures the risk of the plan.

Dashboard: [jacobazu.github.io/dk1-battery-trade](https://jacobazu.github.io/dk1-battery-trade/)

## The real test

A backtest shows that the battery would have earned money. It doesn't show that it will. I made my choices with the backtest period in view, so the backtest is probably a bit too good. The live plans are made from forecasts saved before the auction, so they can't be adjusted afterwards. That's the interesting part, so the dashboard's main page only shows the P&L since launch on 13 Oct 2026. The backtest has its own page.

## Files

- `battery.py`: the battery plan. Gives the same result as the R version on 363 of 375 days. On the other 12, two plans are equally good and R and Python pick different ones.
- `risk.py`: revenue at risk, same method as in R. Matches on 325 of 327 days.
- `limit_backtest.py`: a loss limit on the plan. It costs more than it saves for this battery.
- `stress.py`: stress tests on the plan.
- `dashboard.py`: makes both pages. It runs every morning on GitHub Actions.
