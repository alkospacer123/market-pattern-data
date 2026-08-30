# Cycle 30 — Passive Probe + Confirmed Reclaim Fixed Stop

Preregistered after Cycle 28 showed several broad structural families with positive BASE performance but insufficient STRESS robustness, while Cycle 29 was cancelled before producing a result. Cycle 30 tests a new causal entry hypothesis rather than replaying Cycle 29.

## Fences

- Research-only autonomous discovery.
- Read only Moscow 2026-01-05 through 2026-05-15.
- 2026-05-16 through 2026-07-01 is retired and MUST NOT be read, selected on, tuned on, or reused.
- 2025 TRUE OOS remains SEALED.
- Jan-Feb is discovery only; Mar-May15 is retrospective research-forward only.
- Any survivor still requires genuinely new untouched confirmation data.

## Hypothesis

The structural signal may be real, but entering immediately on the first touch/retest can create adverse-selection losses. A structure-aligned passive price is therefore used only as a **probe**, not as an executable fill. The trade becomes eligible only after an M1 candle touches the probe and causally reclaims it; entry is the exact next M1 open.

## Structural setup

Reuse frozen Cycle-27 M5 structural-event definitions:

- structures: PREV_DAY, ROLL30, ROLL60, M5_FRACTAL, EQUAL_CLUSTER, ROUND, OPEN30;
- events: REJECTION, SWEEP_RECLAIM, BREAK_RETEST;
- protective anchors: LEVEL, EVENT_EXTREME.

For completed M5 setup anchor `A`, fixed stop size `S`, and buffer `B`, define the probe exactly as Cycle 29:

- LONG probe = `A + (S-B)*tick`;
- SHORT probe = `A - (S-B)*tick`.

The probe must be passive relative to the completed setup close. Buffers are 1, 2, 3 ticks.

## Fixed stop grids

- CNYRUBF: 6, 8, 10 points only; never >10.
- USDRUBF: 6, 9, 12, 15 points only.

After confirmed reclaim, entry is exact next M1 open and stop is exactly `S` points from that actual entry. The trade is skipped unless this fixed stop still lies at least `B` ticks beyond the frozen structural anchor. The stop is never widened.

## Reclaim layers

Within 15 or 30 minutes after the completed M5 setup:

- GROSS: M1 touches probe and closes back through probe by >=0 ticks;
- BASE: M1 touches probe and closes back through probe by >=1 tick;
- STRESS: M1 touches probe and closes back through probe by >=2 ticks.

LONG requires touch from above and close at/above the reclaim threshold; SHORT is symmetric. Entry occurs only at the next M1 open after the completed reclaim candle, so no intrabar look-ahead is used.

Exit friction is additionally 0/1/2 adverse ticks for GROSS/BASE/STRESS. STOP_FIRST applies, adverse stop gaps exit at M1 open, favorable target gaps are credited only at target, force close is 17:00 Moscow, commission excluded.

## Reward grid

Targets from actual entry: 3R, 4R, 5R, 6R.

- 3R max hold 120m;
- 4R max hold 180m;
- 5R max hold 240m;
- 6R max hold to 17:00.

No target below 3R.

## Optional context

No context or exactly one frozen broad M5 causal state from the Cycle-29 whitelist: clock buckets and LOW25/HIGH25 numeric states only. Jan-Feb quantile cuts are frozen unchanged for forward use. No LOW10/HIGH10.

## Candidate identity

`instrument | direction | event | structure | anchor_mode | stop_points | anchor_buffer | probe_ttl | target_R | RECLAIM | optional_context`

No ML, no adaptive beam search, no seed shopping, no March-May feedback, no post-hoc anchor substitution, no stop widening.

## Jan-Feb discovery gate

Use the exact Cycle-29 preregistered discovery gate unchanged:

Per January and February separately using BASE: >=5 trades, >=4 dates, BASE PF >=1.20, BASE E[R] >0, with positive STRESS E[R] whenever STRESS trades exist.

Combined Jan5-Feb28: BASE >=14 trades and >=9 dates; STRESS >=10 trades; STRESS/BASE count ratio >=0.50; BASE PF >=2.00; STRESS PF >=1.40; BASE E[R] >=+0.30; STRESS E[R] >=+0.10; positive BASE/STRESS bps expectancy; largest BASE winner share <=0.35.

Freeze at most 60 candidates/instrument, max 3 per identical semantic `(direction,event,structure,anchor_mode,context)` bucket. Rank exactly as Cycle 29 by worst monthly STRESS E[R], then STRESS PF, BASE PF, STRESS E[R], BASE dates, canonical id.

## Mar-May15 strict research gate

Use the exact Cycle-29 survivor gate unchanged:

- BASE PF >=2.00;
- STRESS PF >=1.50;
- BASE E[R] >=+0.30;
- STRESS E[R] >=+0.10;
- day-bootstrap P10 BASE E[R] >0, seed 20260401;
- BASE >=30 trades and >=15 dates;
- STRESS >=20 trades;
- STRESS/BASE count ratio >=0.50;
- March, April, May1-15 total bps each >0 in BASE and STRESS;
- largest BASE winner share <=0.25.

No gate may be weakened after results are observed. A survivor is research-only and awaits genuinely untouched future data.