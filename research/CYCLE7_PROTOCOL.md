# Cycle 7 — Equal High/Low at Round Level

Preregistered before Cycle 7 results on the current repository price series.

## Data fence
- Only 2026-01-05 through 2026-05-15 may be read.
- Retired 2026-05-16 onward data MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Research-only until new untouched data exists.

## Core M5 signal

Round step:
- CNYRUBF: 0.05
- USDRUBF: 0.10

SHORT:
- current M5 high is at a round level within `tolerance_ticks`;
- at least one earlier M5 high in the same trading session and within the last `touch_lookback_bars` was at the same round level within the same tolerance;
- current close is at least `rejection_ticks` below the round level.

LONG is symmetric using lows and a close at least `rejection_ticks` above the round level.

Only the first qualifying second-touch condition in a contiguous cluster is a signal.

Finite semantic neighbourhood:
- `tolerance_ticks`: 0 or 1
- `touch_lookback_bars`: 1, 3, or 6
- `rejection_ticks`: 0 or 1

## Sessions
- M5 signal bars starting 10:00 through 12:55 Moscow.
- M5 signal bars starting 14:00 through 16:50 Moscow.
- Previous touch must be in the same session.
- No overnight carry.

## Execution
- Signal known after M5 close.
- Exact next M1 open.
- One position at a time per instrument.
- SHORT stop = round level + 1 tick; LONG stop = round level - 1 tick.
- If next M1 open is already beyond the stop, skip the trade.
- Target = 3R.
- Force close at 17:00 Moscow.
- STOP_FIRST if stop and target touch in same M1 bar.
- GROSS 0, BASE 1, STRESS 2 adverse ticks per side.
- Commission excluded.

## Research gate per instrument
- BASE PF >= 1.5
- STRESS PF >= 1.2
- positive BASE/STRESS expectancy
- >= 25 trades
- >= 15 unique days
- >= 3 positive calendar months
- largest winner share <= 0.25

Semantic robustness is reported across neighboring tolerance/lookback/rejection variants. A research pass is not confirmation and does not authorize opening 2025.
