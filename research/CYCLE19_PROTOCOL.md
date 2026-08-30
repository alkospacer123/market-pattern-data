# Cycle 19 — Instrument-Specific High-R Discovery

Preregistered after Cycle 17 completed and while Cycle 18 was still running. Motivation is explicit: Cycle 17 pooled selection produced materially different realized forward behavior in CNYRUBF and USDRUBF. Cycle 19 tests whether label pooling masks instrument-specific high-R regimes.

## Fences

- Research-only.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Fresh untouched data is required for confirmation.

## Core design

Use the exact Cycle-18 ultra-short-stop profile family and execution semantics:

- stop ATR coefficients 0.25, 0.35, 0.50;
- raw stop floor 5 ticks;
- targets 3R through 6R;
- exact next M1 open;
- same-day only, force close 17:00;
- STOP_FIRST;
- BASE 1 adverse tick/side, STRESS 2;
- no target below 3R.

Use the exact same causal feature state as Cycle 18, including cross-instrument context features. The important change is label/model isolation, not the information set.

## Instrument isolation

For every weekly block, profile and direction:

- fit CNYRUBF models using only CNYRUBF labeled rows;
- fit USDRUBF models using only USDRUBF labeled rows;
- validation and qualification are also instrument-specific;
- no CNY realized trade outcome may help qualify a Si model and vice versa.

Cross-instrument price-state fields remain legal causal predictors because they are known at signal close; only realized labels are isolated.

## Dual-model qualification

As in Cycle 18, each profile/direction/instrument uses:

1. HistGradientBoostingRegressor predicting BASE realized R;
2. HistGradientBoostingClassifier predicting target-before-stop.

Frozen shared hyperparameter grid:
- max_leaf_nodes 7, 15
- min_samples_leaf 20, 40
- l2_regularization 1, 10
- learning_rate 0.05
- max_iter 120
- seed 20260401

Training window 56 days; latest 14 days validation only. Thresholds are fixed at regression P95 and classifier-probability P75.

Because validation is now one instrument rather than a two-instrument pool, qualification requires:

- >= 12 dual-tail observations;
- >= 5 distinct validation dates;
- BASE PF >= 2.00;
- STRESS PF >= 1.35;
- BASE mean R >= +0.35R;
- STRESS mean R >= +0.10R;
- positive BASE/STRESS bps expectancy;
- target-hit rate >= `1/(target_R+1) + 0.05`;
- largest BASE winner share <= 0.40.

No qualified model = that instrument/profile/direction remains flat for the next week. No fallback.

## Future signal

A model votes only if both its frozen regression-P95 and classifier-P75 thresholds are exceeded. If only one direction has votes, execute the voting profile with highest predicted BASE R. If LONG and SHORT both vote, remain flat. Trade only on directional state onset.

## Final reporting and gates

Report CNY and Si independently before the combined portfolio. An individual instrument is an `INSTRUMENT_RESEARCH_SURVIVOR` only if:

- BASE PF >= 2.00;
- STRESS PF >= 1.50;
- BASE mean R >= +0.30R;
- STRESS mean R >= +0.10R;
- day-block bootstrap P10 BASE mean R > 0;
- >= 20 trades;
- >= 12 unique days;
- >= 2 positive BASE months;
- >= 2 positive STRESS months;
- largest BASE winner share <= 0.30;
- >= 2 target-R levels executed.

The combined portfolio gate remains at least as strict as Cycle 18: BASE PF 2.0, STRESS PF 1.5, positive bootstrap lower tail, 30 trades, 15 days, and diversification across profiles/targets.

The machine may legally return `CNY only`, `Si only`, both, or neither. This is research-only; no result opens 2025 or reuses retired confirmation data.
