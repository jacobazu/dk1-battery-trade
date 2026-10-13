# DK1 battery trading

Python on top of my [DK1 price forecasts](https://github.com/jacobazu/dk1-price-forecasting) (R). It plans a 2 MWh / 1 MW battery from each day's forecast and measures the risk of the plan.

- `battery.py`: the battery plan. Gives the same result as the R version on 363 of 375 days. On the other 12, two plans are equally good and R and Python pick different ones.
- `risk.py`: revenue at risk, same method as in R. Matches on 325 of 327 days.
- `limit_backtest.py`: a loss limit on the plan. It costs more than it saves for this battery.
- `stress.py`: stress tests on the plan.
- `plan_page.py`: a page that shows when to buy and when to sell.

## Next

Daily run (WIP)
