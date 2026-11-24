# Solar panel with the battery as its buffer

Written and committed before anything was run (24 November 2026).

## Question

A solar park sells its forecast day-ahead. When the sun gives more or less than sold, the difference is settled at
the imbalance price. If the park has a battery, the battery can take the surplus and fill the shortfall instead. Is
that worth what the battery gives up in trading and in Energinet's reserves?

## Setup

- Panel: 1 MWp. It produces like DK1's solar fleet on average: each hour, 1 MW times DK1 solar divided by the fleet
  size used by the renewables repo. Real parks see more cloud than all of DK1, so this flatters the buffer a bit.
- Battery: 1 MW / 2 MWh, 90% round trip, at most one full cycle a day, as in the rest of the repo.
- Grid connection: 1 MW, shared. What goes out (solar sold plus battery) and what comes in are each at most 1 MW.
- The battery can charge from the panel and from the grid.
- The panel can be turned down, for example at negative prices.
- Costs: Nord Pool fee on all MWh bought or sold, 20 €/MWh wear on each MWh the battery sells. Energinet's imbalance
  fee and grid tariffs are left out.

## Data

- Solar forecast: the renewables repo's final solar model (results/final_forecasts.csv, the same model that runs
  live), made at 10:00 the day before.
- Solar output: Energinet's settled DK1 solar, scaled the same way.
- Prices: day-ahead from the price repo's forecast and the real prices; FCR, aFRR up and mFRR up as in
  opportunity/; imbalance from Energi Data Service (ImbalancePrice, DK1), one price for both directions.
- Period: 1 January to 11 October 2026. January only builds the error history. Scored from 1 February.

## The buffer

- In each hour the plan keeps room to take in the surplus and charge to fill the shortfall.
- Size: the 1 in 20 worst error of the solar forecast for that hour of the day, up and down separately, as a share
  of the fleet, over the 60 settled days up to 10 days before (settled output comes 8 to 10 days late).
- The buffer comes on top of capacity held for Energinet. Held capacity must be there in full, so it is never
  counted as buffer.

## Order of the day

1. 07:15 the day before, before Energinet's auctions: capacity for FCR, aFRR up and mFRR up, chosen on what is known
   then. As in opportunity/, the day before's day-ahead and reserve prices stand in for the day's. The day before's
   solar forecast stands in for the day's solar, and the buffer is sized on it.
2. 10:30: with the capacity fixed, the day-ahead plan on the price forecast and the 10:00 solar forecast: how much
   solar to sell, when the battery buys and sells, and the buffer in what is left. If the capacity leaves too little
   room for the full buffer, the buffer is smaller that hour and that is counted.
3. The day itself, hour by hour: the battery covers actual minus sold solar as far as the buffer, its power and its
   charge allow. The rest is settled at the imbalance price.

Activation of reserves is not counted, as in opportunity/.

## Compared

- A: no battery. Solar forecast sold day-ahead, all errors at the imbalance price.
- B: solar and battery, day-ahead only, with the buffer.
- C: B plus Energinet's reserves, the order of the day above.

Main test: C against A, € per day, Newey-West t with 7 lags. C wins only if t > 2. B against A is shown as well.

Imbalance left: in hours with sun, the share where some error still went past the battery. Aim: at most 1 in 20.
Shown with how many MWh and what they cost.

## Live

Paper trade from 1 March 2027, when there is sun again, on the live solar forecast, with the same rules. Saved
before each auction and never changed. First judged on 1 September 2027.

## Left out, said on the page

Cloud swings inside the hour, a single park's own weather, intraday trading, activation energy, imbalance fees.
