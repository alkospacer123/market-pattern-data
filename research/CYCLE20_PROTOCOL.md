# Cycle 20 — Structural Ultra-Short Stop / 4R–6R Discovery

Preregistered while Cycle 18 was running, before Cycle 18 or Cycle 19 results were available.

## Fences

- Research-only.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.

## Motivation

High-R research can fail because an ATR-distance stop is not located at a meaningful market invalidation point. Cycle 20 therefore makes the stop structural and lets the target remain large.

## Structural stop family

At the close of each eligible M5 decision bar, use only already completed M1 bars.

For LONG:
- structural reference = minimum M1 low over the last N completed minutes;
- raw stop = structural reference - 1 tick.

For SHORT:
- structural reference = maximum M1 high over the last N completed minutes;
- raw stop = structural reference + 1 tick.

N is frozen to one of 3, 5, or 10 completed M1 bars.

Entry is exact next M1 open. Convert the structural reference to entry risk after the entry price is known:
- risk must be on the correct side of entry;
- minimum raw risk = 5 ticks; if structural distance is smaller, widen only to exactly 5 ticks;
- maximum allowed raw risk = 0.60 ATR14 known at M5 close; if wider, SKIP the candidate bar rather than widening the permitted stop.

Thus every executed stop is both local-structure-based and short relative to current volatility.

## Targets and holds

Every target is >=4R:
- 3-minute structural stop -> 4R / 5R / 6R, max holds 60 / 90 / 120m;
- 5-minute structural stop -> 4R / 5R / 6R, max holds 60 / 90 / 120m;
- 10-minute structural stop -> 4R / 5R / 6R, max holds 60 / 90 / 120m.

Nine frozen profiles total. No 3R target is tested in this cycle because Cycle 17 showed weaker realized forward economics for the 3R bucket than the farther target buckets; this is a new preregistered research revision, not a rewrite of Cycle 17.

## Discovery model

Use instrument-specific dual-model barrier discovery:
1. regression model predicts executable BASE realized R;
2. classifier predicts target-before-stop.

CNY and Si labels/models are isolated as in Cycle 19. Cross-instrument completed-price context may remain a causal predictor.

Training = trailing 56 calendar days, latest 14 days validation only. Weekly future blocks start 2026-03-02.

Frozen model grid:
- HistGradientBoostingRegressor + HistGradientBoostingClassifier;
- max_leaf_nodes 7, 15;
- min_samples_leaf 20, 40;
- l2 1, 10;
- learning_rate 0.05;
- max_iter 120;
- seed 20260401.

Frozen validation signal thresholds:
- regression prediction >= validation P95;
- target probability >= validation P75.

Qualification per instrument/profile/direction:
- >=12 dual-tail observations;
- >=5 dates;
- BASE PF >=2.0;
- STRESS PF >=1.35;
- BASE mean R >=+0.40R;
- STRESS mean R >=+0.15R;
- positive bps expectancy under BASE and STRESS;
- target-hit rate >= `1/(target_R+1)+0.05`;
- largest winner share <=0.40.

No qualification = no trading. No fallback.

## Future execution

- next exact M1 open;
- structure stop frozen from completed pre-entry M1 history, with only the stated 5-tick floor;
- target 4R/5R/6R from raw initial risk;
- STOP_FIRST;
- target gaps filled at frozen target;
- max hold or 17:00 same day;
- GROSS 0, BASE 1, STRESS 2 adverse ticks per side;
- commission excluded.

If both LONG and SHORT independently qualify on the same decision bar, stay flat. Otherwise choose the qualified profile with highest predicted BASE R and trade only on directional state onset.

## Research survivor gate

Per instrument:
- BASE PF >=2.0;
- STRESS PF >=1.5;
- BASE mean R >=+0.35R;
- STRESS mean R >=+0.15R;
- date-block bootstrap P10 BASE mean R >0;
- >=20 trades and >=12 dates;
- >=2 positive BASE months and >=2 positive STRESS months;
- largest winner share <=0.30;
- >=2 target-R values and >=2 structural lookbacks executed.

Research-only. Any survivor still requires genuinely untouched future data.
