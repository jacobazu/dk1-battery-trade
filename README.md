# DK1 battery trading

Python layer on top of my [DK1 price forecasts](https://github.com/jacobazu/dk1-price-forecasting) (built in R). It turns the daily price forecast into a battery plan. Step 1 is the optimiser, ported from R and checked against the R results.

## Check against R

`battery.py` plans a 2 MWh / 1 MW battery (90% round trip, one cycle a day) on a price forecast, and the battery is paid the actual price. `check_vs_r.py` runs it on the 375 backtest days and compares with `results/battery_daily.csv` from the R project.

- 363 of 375 days match to the cent for every model
- On the other 12, two plans earn exactly the same at the forecast prices. R and Python each pick one of them, so the actual revenue differs
- Totals agree within 0.02%
- The check found one real difference: scipy's MIP solver stops at a 0.01% gap by default, which gave a slightly worse plan on 4 days. The gap is now set to 0

## Next

A risk limit on the plan, stress tests on past bad days, and a daily run.
