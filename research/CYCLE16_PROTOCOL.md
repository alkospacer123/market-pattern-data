# Cycle 16 — Sparse Consensus High-PF Discovery

Preregistered after observing that prior ML cycles could select the least-bad validation model even when its validation tail PF was below 1. This is a new research hypothesis, not a reinterpretation of earlier results.

## Status and fences

- Research-only.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Any survivor requires genuinely new untouched data.

## Principle

The machine is explicitly allowed to stay flat for an entire week. A side/profile model is trade-eligible only if its own causal validation high-confidence tail already demonstrates a large executable edge. There is no fallback to a merely 'least bad' model.

## Feature space

Use a pooled feature set combining only causal information already preregistered in earlier independent cycles:

1. numeric M5 state features from `autonomous_search_v3.build_features`, excluding `fwd_*`;
2. Cycle 14 trailing M1 microstructure summaries over 5/15/30 completed minutes;
3. exact-synchronized Cycle 13 cross-instrument fields: normalized return differences, sign agreement, prior rolling correlation/beta, current completed-bar residual;
4. fixed time-of-day sine/cosine and instrument indicator.

All fields must be known when the M5 signal candle closes.

## Executable labels and profiles

Same four frozen profiles:
- P1 stop 0.75 ATR14, target 1.5R, hold <=30m
- P2 stop 1.00 ATR14, target 2R, hold <=60m
- P3 stop 1.25 ATR14, target 2R, hold <=60m
- P4 stop 1.50 ATR14, target 3R, hold <=120m

For each target instrument, LONG/SHORT, and profile, calculate isolated BASE and STRESS bps from exact next M1 open with STOP_FIRST and same-day force close. Training labels require exit timestamp strictly before a weekly block start.

## Weekly causal fit

Seven-day blocks begin 2026-03-02. Training window 56 calendar days, with the most recent 14 days as model-selection validation.

HistGradientBoostingRegressor grid is the same frozen grid as Cycles 11/13/14:
- max_leaf_nodes 7, 15, 31
- min_samples_leaf 20, 50
- l2_regularization 1, 10
- learning_rate 0.05
- max_iter 120
- early_stopping false

For each target instrument x LONG/SHORT x profile and each hyperparameter configuration:

1. Fit on the older causal portion of the 56-day window.
2. Predict the 14-day validation slice.
3. Define high-confidence tail at prediction >= P95 (not P90).
4. Require at least 12 validation-tail observations.
5. Calculate the actual isolated BASE and STRESS trade outcomes for exactly those tail observations.
6. A configuration is `qualified` only if ALL hold:
   - validation BASE PF >= 2.00;
   - validation STRESS PF >= 1.30;
   - BASE expectancy > 0;
   - STRESS expectancy > 0;
   - at least 4 distinct validation trading dates;
   - largest BASE winner share <= 0.35.
7. If no configuration qualifies for a side/profile, that side/profile is DISABLED for the next week.
8. Among qualified configurations rank by minimum(BASE PF, STRESS PF), then STRESS expectancy, then number of dates.
9. Refit the selected configuration on the full causal 56-day window.
10. Freeze its weekly prediction threshold at the selected configuration's validation P95.

There is deliberately no MSE fallback.

## Consensus trading decision

For every future eligible M5 bar in the original research windows 10:00-12:55 and 14:00-16:50:

- Each qualified side/profile produces a prediction.
- It becomes prediction-eligible only above its frozen P95 threshold.
- To trade a direction, require at least two distinct execution profiles on that SAME direction to be prediction-eligible simultaneously.
- Choose from the agreeing profiles the one with the highest predicted BASE bps.
- If LONG and SHORT both satisfy consensus on the same bar, stay flat as ambiguous.
- Trade state onset only; rearm after consensus turns off or changes.
- One position per instrument.

No future block outcome changes that block's models or eligibility.

## Execution/friction

- exact next M1 open;
- same Moscow date, force close 17:00;
- STOP_FIRST;
- GROSS 0, BASE 1, STRESS 2 adverse ticks per side;
- commission excluded.

## Strict research-survivor gate

Combined portfolio:
- BASE PF >= 2.00
- STRESS PF >= 1.50
- positive BASE/STRESS expectancy
- >=30 BASE trades
- >=15 unique trading days
- >=3 positive BASE calendar months
- >=2 positive STRESS calendar months
- largest BASE winner share <=0.25
- GROSS total bps >= BASE >= STRESS

A pass is research-only and awaits fresh untouched data. 2025 remains sealed.
