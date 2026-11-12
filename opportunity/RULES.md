# What does it cost a battery to help Energinet?

Written and committed before anything was run (12 November 2026).

## Question

A DK1 battery can keep power free for Energinet (FCR, aFRR up, mFRR up) and be paid for the capacity, or use that power
in the day-ahead market. Holding capacity costs day-ahead profit: the battery must keep power and charge free. How
much, in which hours, and does splitting the day between the two beat both of today's rules?

## Battery

1 MW / 2 MWh, 90% round trip, at most one full cycle a day, empty at the start and end of each day, fees and 20 €/MWh
wear on each MWh sold (the main case in this repo).

## Holding capacity, per hour

- Power: day-ahead discharge plus capacity held for discharging ≤ 1 MW. FCR works both ways, so day-ahead charging
  plus FCR ≤ 1 MW too.
- Charge: at the start of an hour the battery holds enough to deliver aFRR up and mFRR up for the full hour, and FCR for
  15 minutes. For FCR it also keeps room to take in 15 minutes of charging.
- Capacity can be any amount from 0 to 1 MW in each hour and product.
- Price taker: capacity is paid the hourly clearing price. Activation energy is not paid or counted.

## Information, decided at 07:30 the day before

- Reserve prices for day D: the same hour on D-1, the last known (the same rule as reserves.py).
- Day-ahead prices for day D: the price repo's ensemble forecast, made before the auction.
- One linear program per day picks capacity and the day-ahead plan together. Both are then paid at the real prices of
  day D.

## Rules compared, on the days in results/reserves_daily.csv

1. Day-ahead only (this repo's plan).
2. Whole day in the market that paid most on D-1 (reserves.py).
3. Split day: the linear program above.

Main test: 3 against 2, € per day, Newey-West t with 7 lags. Split day wins only if t > 2.

## The opportunity cost

For each day and hour: the day-ahead profit lost by holding 1 MW of aFRR up in that hour alone, everything else as in
rule 1. Both plans are made on the real prices, so the number is what the hour is worth, not a forecast error. Shown by hour of day, next to the aFRR up price for that hour.

## Left out, said on the page

Activation energy and its pay, wear from activations, bids that don't clear, intraday trading.
