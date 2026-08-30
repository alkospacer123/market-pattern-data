# Cycle 27 — Fixed-Stop Structural Event Search

Preregistered from the user's explicit instruction to continue autonomous discovery with a short fixed stop that must be hidden behind real market structure, and a take-profit of at least 1:3. Definitions below MUST NOT be changed after any Cycle-27 forward result is observed.

## Fences and status

- Research-only autonomous discovery.
- Read only Moscow 2026-01-05 through 2026-05-15.
- 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Jan-Feb is discovery/model-selection only.
- Mar-May15 is research walk-forward only, not fresh confirmation.
- No fallback to a least-bad candidate.

## Core hypothesis

A short fixed stop may be robust if the ENTRY itself is caused by a completed structural event and the fixed stop sits immediately behind the structure that invalidates that event. Cycle 27 therefore does NOT repeat Cycle 24/25's generic `structure happens to sit near the stop` design.

Every legal signal must satisfy BOTH:

1. a causal structural event has just completed;
2. the exact fixed stop, measured from exact next-M1-open entry, lies beyond the frozen protective anchor by a small buffer.

No valid structure = no trade.

## Fixed stop grids

One `point` means one minimum exchange-price increment in the repository data.

- CNYRUBF tick = 0.001. Legal fixed stops: **6, 8, 10 points only**. CNY stop >10 points is forbidden in Cycle 27.
- USDRUBF/Si tick = 0.01. Legal fixed stops: **6, 9, 12, 15 points only**.

Stop distance is EXACTLY `stop_points * tick` from the exact next-M1-open entry. It is never ATR-scaled and is never widened after entry.

## Causal structures

All structures are known at the completed M5 decision bar and use no future bars.

1. `PREV_DAY`: previous Moscow trading day's high/low.
2. `ROLL30`: prior 30-minute high/low, excluding the decision bar.
3. `ROLL60`: prior 60-minute high/low, excluding the decision bar.
4. `M5_FRACTAL`: latest confirmed five-bar M5 swing high/low; confirmation requires two completed M5 bars to the right of the swing.
5. `EQUAL_CLUSTER`: latest pair of prior M5 highs/lows in the previous 60 minutes within 2 ticks of one another; level is their mean.
6. `ROUND`: nearest round level relevant to the event; CNY step 0.05, Si step 0.10.
7. `OPEN30`: 09:00-09:25 Moscow opening-range high/low, available only from 09:30 onward on the same day.

For LONG rejection/sweep, the lower/support version is used. For SHORT rejection/sweep, the upper/resistance version is used. For breakout-retest the opposite pre-break structure is used: upper/resistance for LONG and lower/support for SHORT.

## Frozen event families

### 1. REJECTION

The completed M5 bar touches or modestly penetrates a pre-existing level and closes back on the trade side of the level.

- maximum penetration: 4 ticks;
- close must finish back beyond the level;
- protective-anchor alternatives: `LEVEL` or `EVENT_EXTREME` (decision-bar low for LONG / high for SHORT).

### 2. SWEEP_RECLAIM

The completed M5 bar sweeps the level by at least 1 tick but no more than 6 ticks and closes back across the level.

- LONG: low below support, close back above support;
- SHORT: high above resistance, close back below resistance;
- protective-anchor alternatives: `LEVEL` or `EVENT_EXTREME`.

### 3. BREAK_RETEST

A pre-existing level was already broken on the previous completed M5 bar; the current completed M5 bar retests that level from the new side and closes in continuation direction.

- retest tolerance: 3 ticks around the level;
- LONG: previous close above former resistance, current low retests it and current close remains above it;
- SHORT: previous close below former support, current high retests it and current close remains below it;
- protective-anchor alternatives: `LEVEL` or `EVENT_EXTREME`.

The event family, structure type, side and anchor mode are part of candidate identity and cannot change after discovery.

## Stop must actually be hidden

Let `stop = entry - side * stop_points * tick`.

For LONG the protective anchor must be below entry; for SHORT it must be above entry. A trade is structurally valid only when:

- anchor is strictly between entry and stop;
- stop lies beyond the anchor by at least 1 tick;
- stop-to-anchor buffer is at most **3 ticks**.

Thus a 10-point CNY stop is not legal merely because some level exists somewhere nearby. The frozen invalidation structure must sit close to the actual stop.

## Optional discovery context

The machine may attach either no additional context or exactly ONE frozen causal state from this target-free whitelist:

- `ret_15m_atr`
- `ret_30m_atr`
- `pos_30m`
- `pos_60m`
- `pos_120m`
- `eff_30m`
- `eff_60m`
- `vol_15m_60m`
- `vol_30m_120m`
- `relvol_60m`
- `dist_pdh_atr`
- `dist_pdl_atr`
- `session_pos`
- `clock_bucket`

Numeric states are LOW25, HIGH25, LOW10 or HIGH10. Clock buckets are fixed PRE_09, 09_12, 12_15, 15_18, 18_PLUS. Quantile cutpoints are fitted on Jan5-Feb28 only and then frozen unchanged for Mar-May.

Depth >1 is forbidden in Cycle 27. Context is optional; the structural event remains the primary signal.

## Entry and execution

- decision only after a completed M5 bar;
- eligible decision times 09:00 through 16:30 Moscow;
- exact next M1 open entry;
- one position at a time per instrument;
- same Moscow date only;
- STOP_FIRST if stop and target are both touched in the same M1 bar;
- adverse stop gaps fill at M1 open;
- favorable target gaps fill conservatively at target;
- force close no later than 17:00;
- GROSS = 0 adverse ticks/side, BASE = 1 adverse tick/side, STRESS = 2 adverse ticks/side;
- commission excluded and reported explicitly.

## Reward grid

Target is fixed from entry and is NOT required to coincide with another structure.

- 3R, maximum hold 120 minutes;
- 4R, maximum hold 180 minutes;
- 5R, maximum hold 240 minutes;
- 6R, hold until target/stop/17:00.

No target below 3R is legal.

## Candidate identity

`instrument | direction | event | structure | anchor_mode | stop_points | target_R | optional_context`

Candidate masks are generated deterministically. Exact duplicate masks are deduplicated before ranking.

No ML, adaptive beam search, March-May feedback, post-hoc level substitution or stop widening is allowed.

## Jan-Feb discovery gate

The SAME complete candidate must satisfy January and February separately.

Per month:

- >= 5 executable trades;
- >= 4 distinct dates;
- BASE PF >= 1.20;
- BASE mean realized R > 0;
- STRESS mean realized R > 0.

Combined Jan5-Feb28:

- >= 14 trades;
- >= 9 distinct dates;
- BASE PF >= 2.00;
- STRESS PF >= 1.40;
- BASE mean realized R >= +0.30R/trade;
- STRESS mean realized R >= +0.10R/trade;
- BASE and STRESS expectancy in bps > 0;
- largest BASE winner share <= 0.35;
- GROSS total bps >= BASE >= STRESS.

No pass means no candidate.

## Frozen shortlist

Rank discovery-passing candidates only by:

1. minimum(January STRESS mean R, February STRESS mean R);
2. combined STRESS PF;
3. combined BASE PF;
4. combined STRESS mean R;
5. distinct discovery dates;
6. canonical candidate id.

Freeze at most 60 candidates per instrument, with at most 3 candidates sharing the same `(direction,event,structure,anchor_mode,optional_context)` semantic bucket.

## Mar-May research forward gate

Apply the complete frozen candidate unchanged through 2026-05-15.

A candidate is a `FIXED_STOP_STRUCTURAL_EVENT_SURVIVOR` only if ALL hold:

- BASE PF >= 2.00;
- STRESS PF >= 1.50;
- BASE mean realized R >= +0.30R/trade;
- STRESS mean realized R >= +0.10R/trade;
- whole-trading-date bootstrap P10 BASE mean R > 0, seed 20260401;
- >= 30 trades;
- >= 15 unique trading dates;
- March, April and May1-15 BASE total bps are all > 0;
- March, April and May1-15 STRESS total bps are all > 0;
- largest BASE winner share <= 0.25;
- GROSS total bps >= BASE >= STRESS.

A survivor remains research-only. Retired May16-Jul1 and 2025 remain sealed and require explicit authorization before any future access.
