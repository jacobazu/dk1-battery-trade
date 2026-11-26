# DK1 battery trading

Python on top of my [DK1 price forecasts](https://github.com/jacobazu/dk1-price-forecasting) (R). It plans a 2 MWh / 1 MW battery from each day's forecast and measures the risk of the plan. On the dashboard you pick the forecast: the ensemble (the default) or one of the three models alone, to compare.

Dashboard: [jacobazu.github.io/dk1-battery-trade](https://jacobazu.github.io/dk1-battery-trade/)

Methods: [one page (PDF)](notes/method.pdf)

## Live first

The dashboard's main page shows only the paper P&L since 13 Oct 2026, planned on forecasts saved before each auction. The backtest is on its own page, and is probably a bit flattering since I built the plan with that period in view.

## Day-ahead or Energinet's reserves

Instead of trading, the battery can keep power free for Energinet (FCR, aFRR, mFRR) and be paid for standing ready. The
rules were committed before the run ([opportunity/RULES.md](opportunity/RULES.md)). Backtest, 1 MW, 19 Nov 2025 to
10 Oct 2026, a day after fees and wear:

| Rule | € a day |
|---|---|
| Day-ahead trading only | 177 |
| The whole day in the market that paid most yesterday | 521 |
| Split hour by hour: capacity chosen at 07:15, before Energinet's auctions, day-ahead in the rest | 634 |

- The split beats one market a day by 112 € a day (Newey-West t = 6.5).
- Holding power for Energinet is cheap in the evening peak and dear in the morning: the day-ahead profit given up for
  1 MW of aFRR is about 40 € an hour at 08:00–10:00 and under 15 € at 17:00–20:00, when aFRR pays 30–40 €.
- A first version chose the capacity on the 10:30 price forecast, which isn't out before the 07:30 auctions. It gave
  650 € a day. The corrected rule is the one that counts.
- Price taker: DK1's reserve markets are small, and activation energy isn't counted.
- Runs live as a paper trade from 14 Nov 2026: the capacity is saved each morning before the auctions and scored when
  the day is over (the Helping Energinet tab on the dashboard).

## A better guess of tomorrow's reserve prices

The split day picks its capacity on yesterday's reserve prices. Two other guesses, rules committed before the run
([reserve_forecast/RULES.md](reserve_forecast/RULES.md)), 415 days from 2 Oct 2025 to 25 Nov 2026, € a day:

| Guess | € a day |
|---|---|
| Yesterday (now) | 606 |
| Median of the last 7 days | 575 |
| A small ridge model | 586 |
| Knowing the real prices | 744 |

Neither beats yesterday. The median is off by less on aFRR and mFRR but smooths away the spikes that pay most. Both
keep running live next to the split day, judged 1 Mar 2027.

## Are batteries eating their own prices?

What 1 MW earns in each market, month by month since Jul 2023 ([cannibal/results/monthly.csv](cannibal/results/monthly.csv)),
€ a day:

| | Oct 2024 | Oct 2025 | Oct 2026 |
|---|---|---|---|
| aFRR up | 2,079 | 449 | 180 |
| FCR | 341 | 373 | 386 |
| mFRR up | 28 | 222 | 187 |
| Day-ahead, best cycle with hindsight | 185 | 174 | 231 |

- aFRR up fell about 90% in two years while Energinet buys the same 90-100 MW. That is what new batteries
  competing for a fixed need looks like, but nothing here says who bid.
- FCR has no trend, only summer highs. Most of DK1's FCR is bought abroad, so the price is set in a much bigger market.
  The share bought inside DK1 went from about 10% to 30-40% since Apr 2025.
- Day-ahead spreads grew, mostly in summer.
- No public month-by-month count of DK1 batteries, so this is the price side only.

## Where the costs come from

- Nord Pool fee: 0.055 €/MWh bought or sold ([fee schedule 2026](https://www.nordpoolgroup.com/4a7ad8/globalassets/trading-and-services/nord-pool-fee-schedule-2026-nordic-and-baltic-market.pdf)). The yearly fee is left out.
- Wear: 20 €/MWh sold, my assumption. A system cost about $177/kWh in Europe in 2025 ([BNEF](https://www.energy-storage.news/?p=92133)). Over about 6,000 full cycles, also my assumption, that is about $30/MWh. The backtest also tries 10 and 40. Pricing wear per MWh in the plan is how [Modo Energy](https://ercotforecastdocs.modoenergy.com/docs/battery-degradation) does it.
- Energinet's tariffs, side case only: 11.5 øre/kWh charging, 1.03 øre/kWh discharging ([tariff catalogue 2026](https://www.energinet.dk/media/ikylsqle/energinets-tarifkatalog-2026.pdf)). It isn't clear a battery like this pays them. Local grid tariffs and taxes are left out.
- DKK to EUR at 7.46.

## License

Code: [MIT](LICENSE). Not trading advice.

Prices from [Energi Data Service](https://www.energidataservice.dk) (Energinet), used under "Conditions for use of Danish public-sector data". Not covered by the MIT License or endorsed by Energinet.
