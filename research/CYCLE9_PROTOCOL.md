# Cycle 9 — Equal-Level Liquidity Breakout

Preregistered before Cycle 9 results.

## Data status
- Research-only.
- Read only 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 confirmation data MUST NOT be read.
- 2025 TRUE OOS remains SEALED.

## Hypothesis
Repeated tests of the same round level may create a liquidity pool that is more useful as a breakout trigger than as a reversal trigger.

## M5 signal construction
Round steps remain 0.05 for CNYRUBF and 0.10 for USDRUBF.

An upper level is armed after two M5 highs touch the same round level within the same session. A lower level is armed symmetrically after two M5 lows.

Finite signal grid:
- touch_tolerance_ticks: 0 or 1
- touch_lookback_bars: 3, 6, or 12
- breakout_confirm_ticks: 1 or 2

Sessions:
- 10:00 through 12:55 M5 starts
- 14:00 through 16:50 M5 starts
- arming touches and breakout must occur in the same session

Breakout:
- Armed upper level: first M5 close at or above `level + breakout_confirm_ticks*tick` creates LONG signal.
- Armed lower level: first M5 close at or below `level - breakout_confirm_ticks*tick` creates SHORT signal.
- A level can trigger at most once per session.
- A breakout candle cannot use its own high/low as one of the two prior arming touches; only completed earlier M5 candles count.

## Entry and execution
- Signal known after breakout M5 candle close.
- Enter exact next M1 open only if the open remains beyond the round level in breakout direction; otherwise skip.
- One position at a time per instrument.
- Stop is back inside the broken round level:
  - stop_buffer_ticks: 3, 5, 8, 13
  - LONG stop = level - buffer*tick
  - SHORT stop = level + buffer*tick
- Target grid: 2R, 3R, 4R, where R is actual entry-to-stop distance.
- Force close at 17:00 Moscow.
- STOP_FIRST for intrabar ambiguity.
- GROSS 0, BASE 1, STRESS 2 adverse ticks per side.
- Commission excluded.

## Causal retrospective selection
For each instrument and each signal variant:
1. Select stop buffer and RR using only Jan-Feb 2026.
2. Training eligibility: >=12 BASE trades, BASE/STRESS PF > 1, positive BASE/STRESS expectancy.
3. Rank by lower(BASE PF, STRESS PF), then STRESS expectancy.
4. Freeze execution.
5. Evaluate on March, April, and May 1-15 separately and combined.

March-May is not untouched OOS; it is only a retrospective robustness set.

## Forward research gate
- BASE PF >= 1.50
- STRESS PF >= 1.20
- positive BASE/STRESS expectancy
- >=20 BASE trades
- >=12 unique days
- 3/3 positive BASE folds
- >=2/3 positive STRESS folds
- largest winner share <=0.25
- >=1 adjacent execution neighbor with BASE PF >=1.25, STRESS PF >=1.0 and positive BASE/STRESS expectancy

Any survivor remains research-only and awaits genuinely new confirmation data. Cycle 9 does not authorize opening 2025.
