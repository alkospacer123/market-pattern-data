# Cycle 5 — Causal Adaptive Weekly Selector

Preregistered before Cycle 5 results.

## Purpose

Static Jan-Feb-selected rules repeatedly failed when market regime changed. Cycle 5 tests a trading algorithm whose rule selection is itself causal and adaptive.

## Data fences

- Only 2026-01-05 through 2026-05-15 may be read.
- Retired Internal Confirmation 2026-05-16 onward MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Results are research-only until genuinely new untouched data exists.

## Signal timeframe and execution

- Signal timeframe: M5 only.
- Execution: exact next M1 open.
- Same Moscow day only.
- STOP_FIRST intrabar tie rule.
- BASE = 1 adverse tick per side; STRESS = 2 adverse ticks per side.
- Commission excluded.

## Fixed strategy library

The selector may choose only from a finite canonical subset of the Cycle 4 event families:

- rolling sweep/reclaim
- previous-day sweep/reclaim
- compression breakout
- impulse pullback
- round-level sweep/reclaim
- range breakout

Both long and short versions are allowed where defined. Pattern thresholds and execution parameters are fixed in source before the run; the weekly selector does not optimize stop/target/hold.

## Weekly causal selection

At each Monday-like 7-calendar-day block start from 2026-02-16 onward:

1. Score each library model on the trailing 35 calendar days ending strictly before the block start.
2. Also score it on the trailing 18 calendar days ending strictly before block start.
3. Eligibility requires, on the 35-day window, at least 8 STRESS trades, STRESS PF >= 1.20, STRESS expectancy > 0, and BASE expectancy > 0.
4. The recent 18-day window must have at least 3 STRESS trades and positive STRESS expectancy.
5. Choose the single eligible model with maximum `STRESS expectancy * sqrt(STRESS trades)`.
6. Freeze that one model for the next 7 calendar days. If no model qualifies, stay flat for the block.
7. Repeat using only information available before the next block.

No future block outcome is used to choose the model traded in that block.

## Aggregate research gates

For each instrument independently and for the combined two-instrument portfolio:

- BASE PF >= 1.5
- STRESS PF >= 1.2
- BASE and STRESS expectancy > 0
- >= 30 total trades for combined portfolio (>= 15 for an individual instrument)
- >= 15 unique days combined
- at least 2 positive calendar months in BASE and STRESS
- largest winner share <= 0.25

These gates are intentionally research-stage, not a replacement for fresh confirmation. No Cycle 5 result authorizes opening 2025.
