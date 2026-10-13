# DK1 battery trading

A Python project on top of my [DK1 price forecasts](https://github.com/jacobazu/dk1-price-forecasting), which are made in R. It plans a battery from each day's forecast. It also measures the risk of the plan and tests a loss limit.

## Check against R

`battery.py` plans a 2 MWh / 1 MW battery. It has 90% round trip efficiency and does at most one cycle a day. The plan is made on the forecast and paid the actual price.

`check_vs_r.py` runs it on the 375 backtest days and compares with `results/battery_daily.csv` from the R project.

- 363 of 375 days match to the cent for every model.
- The other 12 days are ties. Two plans earn the same at the forecast prices, and R and Python pick different ones.
- The totals agree within 0.02%.
- scipy stops at a 0.01% gap by default. That gave a slightly worse plan on 4 days, so the gap is set to 0.

## Revenue at risk

`risk.py` uses the same method as the R project. The plan is fixed before the auction. So the revenue of a day is the planned revenue plus the forecast errors times the plan.

The scenarios are the 24-hour errors of up to 250 past days. They are scaled by an EWMA of the error volatility (lambda = 0.94).

`check_risk_vs_r.py` compares with `results/battery_risk_daily.csv`. 325 of 327 days match to the cent. The other 2 are tie days from above.

## Loss limit

`limit_backtest.py` adds a limit to the plan. The average revenue of the worst 5% of scenarios can't go below minus the limit. The limit uses the Rockafellar-Uryasev form, so the problem stays linear. I set the limits and the tests before running it.

| Loss limit | Days it binds | Revenue vs no limit | Change per day | p (Newey-West) | Days with a loss | Worst day |
|---|---|---|---|---|---|---|
| None | 0 | 70,205 € | | | 2 | -22 € |
| 100 € | 5 | -0.3% | -0.60 € | 0.19 | 2 | -22 € |
| 50 € | 24 | -1.3% | -2.76 € | 0.017 | 2 | -22 € |
| 25 € | 57 | -2.8% | -6.09 € | 0.001 | 2 | -14 € |
| 0 € | 102 | -7.5% | -16.03 € | < 0.001 | 0 | 0 € |

327 days, 18 Nov 2025 to 10 Oct 2026.

For this battery the limit costs more than it saves. Losses are rare. There were 2 in 327 days, and the worst was -22 €. The limit mostly hits volatile days, and those are the days the battery earns the most. On the 24 days a 50 € limit binds, the battery earned 192 € a day without it and 155 € with it.

## Next

Stress test (WIP)
