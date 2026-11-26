# A better guess of tomorrow's reserve prices

Written and committed before any forecast below was run (26 November 2026).

## Question

The split day (opportunity/) picks capacity for FCR, aFRR up and mFRR up at 07:15 the day before, with the day
before's reserve prices as the guess for the day's. Does a better guess earn more, after the day is paid at the real
prices?

Already seen before this was written (26 November 2026, a quick check, not a test): on 411 days from 2 October 2025
to 21 November 2026, the split day made 608 € a day and would have made 746 knowing the day's real reserve prices.
No guess below has been run.

## Battery and day

As in opportunity/RULES.md: 1 MW / 2 MWh, 90% round trip, at most one full cycle a day, fees and 20 €/MWh wear on
each MWh sold, ends the day with at least the charge it started with. Capacity at 07:15 the day before on the guess
and the day before's day-ahead prices, then the day-ahead plan at 10:30 on the price repo's ensemble forecast in what
is left. Paid at day D's real day-ahead and reserve prices. Only the guess of the reserve prices changes.

## Guesses

Each is € per MW and hour, per product and hour of the day, using only reserve prices known at 07:15 the day before
(day D-1 and earlier). Below 0 is set to 0.

- A, now: day D-1, same hour.
- B, last week: median of the same hour on D-7 to D-1.
- C, a small model: per product and hour of the day, ridge regression (alpha 1, inputs standardized on the fit days)
  on D-1, D-2, D-7, the median of D-7 to D-1 (all the same hour), and the day of the week of D (6 dummies). Fitted
  each day on the 56 days up to D-1 whose inputs and target are all known at 07:15 on D-1. No other settings tried.

A missing price in an input is replaced by B for that hour. A product with no prices at all in the last 7 days is
not held that day, as in opportunity/.

## Data

Reserve prices as in opportunity/ (FcrDK1, AfrrReservesNordic, mFRRCapacityMarket, DK1, hourly mean), from
1 August 2025 so C has its 56 days. Days scored: the days opportunity/ scores, from 2 October 2025 to
25 November 2026.

## Tests

- Main: C against A, € per day.
- Second: B against A, € per day.
- Newey-West t with 7 lags on the daily difference, one sided, Holm over the two. A guess wins only if its Holm
  p < 0.05.
- Shown as well, not tested: mean absolute error of each guess per product, and the share of the 746 € headroom
  each guess takes.

## Live

From the first morning after the backtest is run, whatever it shows, B and C are saved each morning at 07:15 next to
the current rule, as challengers: the guess, the capacity they would hold, then their € when the day is over. Not
shown on the dashboard. Judged on 1 March 2027 with the same tests on live days only. The current rule stays until
then.

## Left out

As in opportunity/: activation energy and its pay, wear from activations, bids that don't clear, intraday trading.
Price taker.
