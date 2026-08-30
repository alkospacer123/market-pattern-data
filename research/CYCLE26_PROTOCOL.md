# Cycle 26 — Sparse High-R Atomic Rule Ensemble

Preregistered while Cycle 22 was still running, after Cycles 21/23 established the frequency-vs-edge trade-off: narrow atomic high-R states can be very strong but too rare, while deterministic widening raises frequency and dilutes PF. Cycle 26 tests aggregation of several distinct rare rules without relaxing any component.

## Fences and status

- Research-only.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- March–May has already been inspected in other cycles; it is research stability evidence only.

## Atomic rule universe

Use exactly the Cycle-21 target-free rule universe:
- causal numeric M5 fields from `autonomous_search_v3.build_features`, excluding `fwd_*`;
- January-fitted LOW10/LOW25/HIGH25/HIGH10 states;
- fixed one-hour states 09:00–16:59;
- all univariate rules;
- target-free SHA256 first 1,500 eligible depth-2 interactions;
- exact-mask dedupe before outcome evaluation;
- false-to-true onset within the same Moscow date;
- eligible bars 09:00–16:50.

No Cycle-23 relaxed/OR family masks may enter this cycle.

## Frozen high-R profiles

- E1: 0.75 ATR stop, 4R target, max hold 90m
- E2: 0.75 ATR stop, 5R target, max hold 120m
- E3: 0.75 ATR stop, 6R target, max hold 120m
- E4: 1.00 ATR stop, 4R target, max hold 120m
- E5: 1.00 ATR stop, 5R target, force close 17:00

Execution is exact next M1 open, same Moscow day, STOP_FIRST, conservative target-gap fill, force close 17:00, GROSS/BASE/STRESS = 0/1/2 adverse ticks per side, commission excluded.

## Stage A — January component qualification only

For every atomic rule x direction x profile, January standalone performance must satisfy ALL:
- >= 6 executable trades;
- >= 4 distinct dates;
- BASE PF >= 2.00;
- STRESS PF >= 1.50;
- BASE mean R >= +0.35R/trade;
- STRESS mean R >= +0.15R/trade;
- target-hit rate >= theoretical gross break-even `1/(target_R+1) + 0.04`;
- largest BASE winner share <= 0.40.

Rank qualified January components by:
1. STRESS mean R descending;
2. min(BASE PF, STRESS PF) descending;
3. distinct January dates descending;
4. canonical `rule_id|direction|profile` ascending.

Keep at most 60 before diversity filtering.

## Stage B — diversity filter frozen before February PnL

Process components in frozen January rank order. Keep a component only if:
- its January onset mask is not an exact duplicate of any kept component;
- onset Jaccard overlap with every kept component is <= 0.50;
- it contributes at least 3 January onset dates not already covered by kept components of the same direction.

Keep at most 12 components/instrument. Diversity uses only January onset masks/dates, never February or March–May PnL.

## Stage C — February portfolio validation

Component membership, profile, direction and priority are frozen before February outcomes are inspected.

On each February M5 bar:
- if multiple frozen components fire in one direction, use the highest January-priority component;
- if both LONG and SHORT components fire on that bar, stay flat;
- one open position at a time per instrument;
- no February re-ranking, removal or parameter change.

The frozen ensemble is allowed to proceed only if February portfolio performance satisfies ALL:
- >= 8 BASE trades;
- >= 5 distinct dates;
- at least 2 distinct atomic components actually execute;
- BASE PF >= 1.50;
- STRESS PF >= 1.20;
- BASE mean R >= +0.20R/trade;
- STRESS mean R > 0;
- largest BASE winner share <= 0.35;
- GROSS total bps >= BASE >= STRESS.

If February fails, March–May performance may still be reported diagnostically but the ensemble cannot be labeled a research survivor.

## Stage D — frozen March–May research stability

No component membership, priority, direction or execution geometry may change.

Strict `SPARSE_HIGH_R_ENSEMBLE_RESEARCH_SURVIVOR` requires ALL:
- February gate passed;
- BASE PF >= 2.00;
- STRESS PF >= 1.50;
- BASE mean R >= +0.30R/trade;
- STRESS mean R >= +0.10R/trade;
- whole-trading-date bootstrap P10 BASE mean R > 0, seed 20260401, 1,000 reps;
- >= 25 BASE trades;
- >= 15 unique trading dates;
- >= 2 positive BASE calendar months;
- >= 2 positive STRESS calendar months;
- largest BASE winner share <= 0.25;
- >= 3 distinct atomic components actually execute in March–May;
- >= 2 distinct executed target-R values;
- GROSS total bps >= BASE >= STRESS.

Report component contribution and leave-one-component-out portfolio metrics descriptively. These diagnostics must not feed back into the frozen ensemble.

Any pass remains research-only and awaits genuinely new untouched future confirmation data.
