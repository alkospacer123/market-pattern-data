# Cycle 10 — CNY/USDRUB Relative-Value Spread

Preregistered before Cycle 10 results.

## Motivation
CNYRUBF and USDRUBF are both 1,000-unit currency futures. Their price ratio is a tradable proxy for USD/CNY plus relative futures basis. Cycle 10 trades temporary intraday deviations in this ratio rather than taking outright RUB direction.

## Data fence and status
- Research-only.
- Read only 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 data MUST NOT be read.
- 2025 TRUE OOS remains SEALED.

## Contract model
- USDRUBF: 1 contract = 1,000 USD; price tick 0.01 RUB per USD.
- CNYRUBF: 1 contract = 1,000 CNY; price tick 0.001 RUB per CNY.
- At each entry, trade 1 USDRUBF contract versus `round(USDRUBF_entry / CNYRUBF_entry)` CNYRUBF contracts, minimum 1. This produces approximately equal RUB notionals causally from available entry prices.

## Spread and causal z-score
On synchronized M5 closes:
- `spread = log(USDRUBF_close / CNYRUBF_close)`.
- Rolling mean and standard deviation use only earlier bars from the same Moscow calendar day (`shift(1)` before rolling).
- No overnight observations enter a day's rolling statistics.

Parameter grid:
- rolling_window_minutes: 60, 120, 240
- entry_z: 1.5, 2.0, 2.5
- exit_z: 0.25, 0.50
- max_hold_minutes: 60, 120
- adverse spread stop: `entry_z + 1.0` in the same direction

## Signals
Trade only M5 starts 10:00-12:55 and 14:00-16:50 Moscow.

- z crosses from below to at/above +entry_z: SHORT ratio = short 1 USDRUBF, long hedge CNYRUBF.
- z crosses from above to at/below -entry_z: LONG ratio = long 1 USDRUBF, short hedge CNYRUBF.
- Signal is known only after the M5 close.
- Enter both legs at the exact synchronized next M1 open.
- Only the first threshold crossing in an excursion is a signal; no repeated entry until z returns inside the entry band.
- One pair trade at a time.

## Exit
For a SHORT-ratio trade:
- mean-reversion exit when a completed M5 z <= +exit_z;
- spread stop when completed M5 z >= +(entry_z + 1.0).

For a LONG-ratio trade:
- mean-reversion exit when completed M5 z >= -exit_z;
- spread stop when completed M5 z <= -(entry_z + 1.0).

Exit signal executes at exact next synchronized M1 open. Also exit at max_hold_minutes or 17:00, whichever comes first, using the synchronized M1 open at that time when available.

## Friction and PnL
Both contract multipliers are 1,000.

- GROSS: 0 adverse ticks per leg per side.
- BASE: 1 adverse price tick on each leg at entry and at exit.
- STRESS: 2 adverse price ticks on each leg at entry and at exit.
- No favorable gap improvement is credited beyond the observed M1 open.
- Commission is excluded and reported explicitly.
- Pair PnL is calculated in RUB across both integer-contract legs.
- Performance bps use combined gross RUB notional of the two legs at entry.

## Causal retrospective selection
Use Jan-Feb only for parameter selection.

Training eligibility:
- >=15 BASE trades
- BASE PF >=1.20
- STRESS PF >=1.00
- positive BASE and STRESS expectancy
- positive BASE total PnL in January and February separately
- positive STRESS total PnL in January and February separately

Rank eligible models by lower(BASE PF, STRESS PF), then STRESS expectancy.
Freeze the best model before evaluating March, April, and May 1-15.

## Retrospective forward research gate
Combined March-May folds:
- BASE PF >=1.50
- STRESS PF >=1.20
- positive BASE and STRESS expectancy
- >=20 BASE trades
- >=12 unique days
- 3/3 positive BASE folds
- >=2/3 positive STRESS folds
- largest winner share <=0.25
- >=2 adjacent parameter neighbors with BASE PF >=1.20, STRESS PF >=1.0 and positive BASE/STRESS expectancy

March-May is not untouched OOS. Any survivor remains research-only and requires genuinely new confirmation data. Cycle 10 never authorizes opening 2025.
