# DK1 battery trading

Python layer on top of my [DK1 price forecasts](https://github.com/jacobazu/dk1-price-forecasting) (built in R). It turns the daily price forecast into a battery plan, measures the plan's risk and tests a loss limit on it.

## Check against R

`battery.py` plans a 2 MWh / 1 MW battery (90% round trip, one cycle a day) on a price forecast, and the battery is paid the actual price. `check_vs_r.py` runs it on the 375 backtest days and compares with `results/battery_daily.csv` from the R project.

- 363 of 375 days match to the cent for every model
- On the other 12, two plans earn exactly the same at the forecast prices. R and Python each pick one of them, so the actual revenue differs
- Totals agree within 0.02%
- The check found one real difference: scipy's MIP solver stops at a 0.01% gap by default, which gave a slightly worse plan on 4 days. The gap is now set to 0

## Revenue at risk

`risk.py` is the method the R project uses for the battery's revenue at risk. The plan is fixed before the auction, so the day's revenue is the planned revenue plus the forecast errors times the plan. The scenarios are the 24-hour errors of up to 250 past days, scaled by an EWMA of the error volatility (λ = 0.94). `check_risk_vs_r.py` compares expected revenue, the 5% floor, the average below it and the realized revenue with `results/battery_risk_daily.csv`: 325 of 327 days match to the cent, and the other 2 are tie days from above.

## A loss limit

`limit_backtest.py` adds a limit to the plan: the average revenue of the worst 5% of scenarios may not fall below minus the limit. It is written the Rockafellar–Uryasev way, so the plan is still a linear program. The limits and the tests were set before running.

| Loss limit | Days it binds | Revenue vs no limit | Change per day | p (Newey-West) | Days with a loss | Worst day |
|---|---|---|---|---|---|---|
| None | 0 | 70,205 € | | | 2 | −22 € |
| 100 € | 5 | −0.3% | −0.60 € | 0.19 | 2 | −22 € |
| 50 € | 24 | −1.3% | −2.76 € | 0.017 | 2 | −22 € |
| 25 € | 57 | −2.8% | −6.09 € | 0.001 | 2 | −14 € |
| 0 € | 102 | −7.5% | −16.03 € | < 0.001 | 0 | 0 € |

327 days, 18 Nov 2025 to 10 Oct 2026.

For this battery a loss limit costs more than it saves. Losses are rare (2 of 327 days, the worst −22 €), and the days the limit flags are the volatile ones, which are also the days the battery earns the most. On the 24 days a 50 € limit binds, the battery earned 192 € a day without it and 155 € with it. A 0 € limit removes the loss days, but it stops trading on 33 days and costs 7.5% of the revenue. Where to set a limit depends on how much a bad day would hurt, and the table shows what each level costs.

## Next

Stress tests on past bad days, and a daily run with a short note on the plan and its risk.
