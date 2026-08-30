# Cycle 24 — Fixed-Point Structural Stops + High-R Structural Targets

Preregistered from the user's explicit instruction while prior high-R research cycles were still active. Cycle 24 is a new independent research class; its definitions MUST NOT be changed after seeing its forward results.

## Fences and status

- Research-only autonomous discovery.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- March–May is research walk-forward only, not fresh confirmation.

## Research question

Can a short fixed stop in instrument-specific price points become robust when it is permitted only when the stop is genuinely hidden behind pre-existing causal market structure, and when the profit target is >3R and aligned with a known favorable structural objective?

The machine may remain flat. There is no fallback to an unanchored fixed stop and no least-bad candidate.

## Point definition and fixed stop grids

For this engine one `point` means one minimum exchange-price increment used in the repository data:

- CNYRUBF tick = 0.001. Fixed stop candidates: **4, 6, 8, 10 points only**. No CNY stop >10 points is legal.
- USDRUBF/Si tick = 0.01. Fixed short-stop candidates: **6, 9, 12, 15 points only**.

For a chosen stop candidate the stop distance is EXACTLY `stop_points * tick` from the next-M1-open entry. It is never ATR-scaled and never widened after entry.

## Stop must be hidden behind causal structure

For each completed M5 decision bar, using only completed M1 bars strictly before the next-M1-open entry, define side-specific protective anchors:

1. `EXT5`: lowest low / highest high of the previous 5 completed M1 bars;
2. `EXT15`: lowest low / highest high of the previous 15 completed M1 bars;
3. `EXT30`: lowest low / highest high of the previous 30 completed M1 bars;
4. `FRACTAL`: latest confirmed five-bar M1 swing low/high (two completed bars on each side) found in the prior 30 completed M1 bars;
5. `ROUND_RETEST`: nearest round price level behind the entry, but only when that exact level was touched by the completed M1 high-low range during the prior 30 minutes.

For LONG the structural anchor must be below entry; for SHORT it must be above entry.

A fixed stop is structurally valid only when:

- the anchor is strictly between entry and stop;
- the stop lies beyond the anchor by at least 1 point;
- the stop-to-anchor buffer is no larger than `min(4, max(1, round(stop_points * 0.25)))` points.

Therefore a 10-point CNY stop cannot be accepted merely because some irrelevant low is 2 points away: the selected protective structure must sit near the actual fixed stop. If no structural anchor fits the fixed stop, no trade exists for that stop profile.

The anchor type is part of the frozen candidate identity. The machine is not allowed to choose a different anchor after entry.

## High-R target must also have structural context

Frozen target-R candidates are:

- 3.5R
- 4R
- 5R
- 6R

No target <=3R is legal.

The target price remains exactly `entry +/- target_R * fixed_risk`. However it is valid only when a pre-existing favorable structural objective lies just beyond that target. Target context types are:

1. `EXT30`: previous 30 completed M1 bars favorable extreme;
2. `EXT60`: previous 60 completed M1 bars favorable extreme;
3. `ROUND_NEXT`: next round price level in the favorable direction;
4. `PREV_DAY`: previous Moscow trading day's high for LONG / low for SHORT.

For a target context to validate a fixed target, the objective must be in the favorable direction and its distance from entry, measured in fixed initial R, must lie in `[target_R, target_R + 1.0]`.

Thus a fixed 4R take-profit is used only when there is a known structural objective between 4R and 5R from entry. A target with no nearby causal objective is not traded.

The target-context type is part of the candidate identity and cannot change after entry.

## Entry and execution semantics

- decision only after a completed M5 bar;
- eligible decision times 09:00 through 16:50 Moscow;
- exact next M1 open entry;
- one fixed stop and one fixed target from entry;
- same Moscow date only;
- STOP_FIRST if stop and target are both touched in the same M1 bar;
- adverse stop gaps filled at the M1 open;
- favorable target gaps filled conservatively at the target;
- force close no later than 17:00;
- maximum hold by target: 3.5R = 90m, 4R = 120m, 5R = 240m, 6R = to 17:00;
- GROSS = 0 adverse ticks/side, BASE = 1 adverse tick/side, STRESS = 2 adverse ticks/side;
- commission excluded and explicitly reported.

## Candidate family

Candidate identity is exactly:

`instrument | direction | stop_anchor_type | stop_points | target_context_type | target_R`

All combinations from the frozen stop-anchor, stop-grid, target-context and target-R sets are generated deterministically before any outcome is inspected.

For each candidate, the signal is the false-to-true onset of its complete structural-validity state within a Moscow date. A continuously valid state does not fire repeatedly. Exact duplicate signal masks are deduplicated deterministically before outcome ranking.

No ML, adaptive beam search, PF-driven interaction generation, parameter interpolation or post-hoc anchor substitution is allowed in Cycle 24.

## January–February discovery gate

The SAME complete candidate must satisfy January and February separately.

Per month:

- >= 5 executable trades;
- >= 4 distinct trading dates;
- BASE PF >= 1.20;
- BASE mean realized R > 0;
- STRESS mean realized R > 0.

Combined 2026-01-05 through 2026-02-28:

- >= 14 trades;
- >= 9 distinct trading dates;
- BASE PF >= 2.00;
- STRESS PF >= 1.40;
- BASE mean realized R >= +0.30R/trade;
- STRESS mean realized R >= +0.10R/trade;
- BASE and STRESS expectancy in bps > 0;
- largest BASE winner share <= 0.35;
- GROSS total bps >= BASE >= STRESS.

No pass means no candidate. There is no least-bad fallback.

## Frozen shortlist

Rank discovery-passing candidates only by:

1. minimum(January STRESS mean R, February STRESS mean R);
2. combined STRESS PF;
3. combined BASE PF;
4. combined STRESS mean R;
5. distinct discovery dates;
6. canonical candidate id.

Freeze at most 40 candidates per instrument. At most 2 candidates may share the same exact signal-mask digest and direction.

## March–May research forward gate

Apply the complete frozen candidate unchanged from 2026-03-01 through 2026-05-15. No March–May value may modify stop points, anchor type, target R, target context, execution or ranking.

A candidate is a `FIXED_POINT_STRUCTURAL_SURVIVOR` only if ALL hold:

- BASE PF >= 2.00;
- STRESS PF >= 1.50;
- BASE mean realized R >= +0.30R/trade;
- STRESS mean realized R >= +0.10R/trade;
- whole-trading-date bootstrap P10 BASE mean R > 0, seed 20260401;
- >= 20 trades;
- >= 12 unique trading dates;
- >= 2 positive BASE calendar months;
- >= 2 positive STRESS calendar months;
- largest BASE winner share <= 0.30;
- GROSS total bps >= BASE >= STRESS.

Report CNY and Si independently. A weak instrument does not invalidate a strong instrument.

Any survivor remains research-only and requires genuinely new untouched future confirmation data. Retired May16–Jul1 and 2025 stay sealed.
