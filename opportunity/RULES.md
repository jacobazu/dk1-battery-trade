# What does it cost a battery to help Energinet?

Written and committed before anything was run (12 November 2026).

## Question

A DK1 battery can keep power free for Energinet (FCR, aFRR up, mFRR up) and be paid for the capacity, or use that power
in the day-ahead market. Holding capacity costs day-ahead profit: the battery must keep power and charge free. How
much, in which hours, and does splitting the day between the two beat both of today's rules?

## Battery

1 MW / 2 MWh, 90% round trip, at most one full cycle a day, fees and 20 €/MWh wear on each MWh sold (the main case in
this repo). Day-ahead only starts and ends the day empty, as in the rest of the repo. Holding capacity at midnight needs
charge, so in the split day the battery ends the day with at least the charge it started with (added before any run,
12 November 2026).

## Holding capacity, per hour

- Power: day-ahead discharge plus capacity held for discharging ≤ 1 MW. FCR works both ways, so day-ahead charging
  plus FCR ≤ 1 MW too.
- Charge: at the start of an hour the battery holds enough to deliver aFRR up and mFRR up for the full hour, and FCR for
  15 minutes. For FCR it also keeps room to take in 15 minutes of charging.
- Capacity can be any amount from 0 to 1 MW in each hour and product.
- Price taker: capacity is paid the hourly clearing price. Activation energy is not paid or counted.

## Information, in two steps (corrected 12 November 2026, see below)

- 07:15 the day before, capacity: Energinet's capacity auctions close around 07:30 (FCR 08:00), before the price
  forecast is out. So the capacity for day D is chosen on what is known then: D-1's day-ahead prices as D's, and D-1's
  reserve prices.
- About 10:30, the day-ahead plan: with the capacity fixed, the price repo's ensemble forecast plans day-ahead
  trading in the power and charge that are left.
- Both are then paid at the real prices of day D.

Correction: the first run (early on 12 November) chose the capacity on the 10:30 price forecast, which doesn't exist at 07:15.
It gave 650 € a day. It stays in results/daily.csv as "split, forecast at 07:15 (not possible)", but the test uses the
corrected rule.

## Rules compared, on the days in results/reserves_daily.csv

1. Day-ahead only (this repo's plan).
2. Whole day in the market that paid most on D-1 (reserves.py).
3. Split day: the two steps above.

Main test: 3 against 2, € per day, Newey-West t with 7 lags. Split day wins only if t > 2.

## The opportunity cost

For each day and hour: the day-ahead profit lost by holding 1 MW of aFRR up in that hour alone, everything else as in
rule 1. Both plans are made on the real prices, so the number is what the hour is worth, not a forecast error. Shown by hour of day, next to the aFRR up price for that hour.

## Left out, said on the page

Activation energy and its pay, wear from activations, bids that don't clear, intraday trading.
