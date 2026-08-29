# Cycle 4 Event Discovery Protocol

Status: preregistered before Cycle 4 search.

## Data fences

- Discovery data: Moscow 2026-01-05 00:00 inclusive through 2026-05-16 00:00 exclusive.
- Candidate semantics and execution parameters are selected only from Jan-Feb 2026.
- Frozen forward folds are March, April, and 2026-05-01 through 2026-05-15.
- The previously opened 2026-05-16 through 2026-07-01 Internal Confirmation is RETIRED and MUST NOT be read, scored, filtered, or used to retune Cycle 4 candidates.
- 2025 TRUE OOS remains SEALED.
- No fresh confirmation window currently exists in the repository; any Cycle 4 discovery survivor is `AWAITING_NEW_CONFIRMATION_DATA`, not production-approved.

## Event families

Cycle 4 searches only preregistered event semantics, not arbitrary state intersections:

1. `rolling_sweep_reclaim`: price sweeps a prior rolling high/low and closes back inside.
2. `prev_day_sweep_reclaim`: price sweeps previous-day high/low and closes back across it.
3. `compression_breakout`: prior rolling range is compressed relative to ATR, then close breaks the prior range with directional body.
4. `impulse_pullback`: a fixed-horizon ATR-normalized impulse is followed by a controlled retracement candle while price remains beyond the impulse origin.
5. `round_level_sweep_reclaim`: price crosses a nearest round level intrabar and closes back across it.
6. `range_breakout`: close breaks a prior rolling range with minimum body and optional relative-volume threshold.

All lookbacks and numeric thresholds come from finite preregistered grids in the source. No Cycle 4 code reads rows at or after 2026-05-16.

## Execution

- Signal is known only after signal candle close.
- Entry is the exact next M1 open.
- One position at a time per candidate.
- Same Moscow trading day only.
- STOP_FIRST when stop and target are both touched intrabar.
- GROSS 0 adverse ticks/side, BASE 1 adverse tick/side, STRESS 2 adverse ticks/side.
- Commission excluded and reported explicitly.

## Selection stability

A candidate must have positive BASE and STRESS expectancy separately in January and February before it may be frozen for forward evaluation. Parameter selection is from Jan-Feb only.

## Strict forward gates

- BASE PF >= 2.0
- STRESS PF >= 1.5
- BASE expectancy > 0
- STRESS expectancy > 0
- >= 30 trades
- >= 15 unique trading days
- 3 positive months
- 3 positive forward folds in BASE and STRESS
- largest winner share <= 0.25
- >= 2 stable neighboring execution parameter sets

Cycle 4 survivors remain awaiting a genuinely untouched future confirmation set. The retired May16-Jul1 window and sealed 2025 set are not substitutes.
