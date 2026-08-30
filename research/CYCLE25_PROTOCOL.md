# Cycle 25 — Fixed-Point Structural Stops + Direct Structural Targets

Preregistered after Cycle 24 completed. Cycle 25 preserves the user's fixed-stop concept but removes the artificial fixed-R target. The target itself is now a causal structural level, and the trade is legal only when that level offers >3R.

## Fences

- Research-only.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- March–May is research walk-forward only.

## Fixed stop

One point = one repository tick.

- CNYRUBF: fixed SL candidates 4, 6, 8, 10 points; never >10.
- USDRUBF/Si: fixed SL candidates 6, 9, 12, 15 points.

Stop distance is exactly `stop_points * tick` from exact next-M1-open entry. No ATR scaling and no widening.

The same Cycle-24 causal protective anchors are used:
- EXT5
- EXT15
- EXT30
- latest confirmed five-bar M1 FRACTAL
- ROUND_RETEST

The selected fixed stop must sit beyond the selected anchor by at least 1 point and by no more than `min(4, max(1, round(stop_points*0.25)))` points. No fitting anchor = no trade.

## Direct structural target

Target context is one of:
- EXT30 favorable extreme of previous 30 completed M1 bars;
- EXT60 favorable extreme of previous 60 completed M1 bars;
- ROUND_NEXT favorable round level;
- PREV_DAY high for LONG / low for SHORT.

Actual take-profit is placed **one point before** the frozen structural objective:
- LONG: `target = objective - tick`
- SHORT: `target = objective + tick`

The target is legal only when its exact initial reward/risk ratio, based on the fixed stop, is in **[3.25R, 8.00R]**. No target <=3R is allowed. The structural objective and target price are frozen at entry and never moved.

## Execution

- completed M5 decision bar, eligible 09:00–16:50 Moscow;
- exact next M1 open;
- same Moscow day only;
- STOP_FIRST on same-bar ambiguity;
- adverse stop gap at M1 open;
- favorable target gap conservatively at target;
- position may remain open until target/stop or 17:00;
- GROSS/BASE/STRESS = 0/1/2 adverse ticks per side;
- commission excluded.

## Candidate family

Candidate identity:
`instrument | direction | stop_anchor_type | stop_points | target_context_type`

All combinations are generated before outcome inspection. Signal = false-to-true onset of the complete structural-validity state. Exact duplicate signal masks are deduplicated before ranking.

No ML, adaptive search, post-hoc target substitution or March–May feedback is allowed.

## January–February discovery gate

Same candidate must satisfy January and February separately:
- >=5 trades;
- >=4 distinct days;
- BASE PF >=1.20;
- BASE mean R >0;
- STRESS mean R >0.

Combined Jan5–Feb28:
- >=14 trades;
- >=9 distinct days;
- BASE PF >=2.00;
- STRESS PF >=1.40;
- BASE mean R >=+0.30R;
- STRESS mean R >=+0.10R;
- BASE/STRESS bps expectancy >0;
- largest BASE winner share <=0.35;
- GROSS total bps >= BASE >= STRESS.

Shortlist max 40/instrument, ranked by minimum Jan/Feb STRESS mean R, then combined STRESS PF, BASE PF, STRESS mean R, days, candidate id.

## March–May forward gate

Apply candidate unchanged through 2026-05-15. Strict `DIRECT_STRUCTURAL_TARGET_SURVIVOR` requires:
- BASE PF >=2.00;
- STRESS PF >=1.50;
- BASE mean R >=+0.30R;
- STRESS mean R >=+0.10R;
- day-bootstrap P10 BASE mean R >0, seed 20260401;
- >=20 trades;
- >=12 unique days;
- >=2 positive BASE months;
- >=2 positive STRESS months;
- largest BASE winner share <=0.30;
- GROSS total bps >= BASE >= STRESS.

Report instruments independently. Any pass remains research-only and requires genuinely new untouched confirmation data.