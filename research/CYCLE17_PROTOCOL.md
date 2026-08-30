# Cycle 17 — Autonomous High-R Expectancy Discovery

Preregistered after Cycles 1–14 showed that frequent weak predictive edges are generally too small to survive realistic friction, while rare high-PF states can appear but must be protected against sparse-selection overfit.

## Status and fences

- Research-only autonomous discovery.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- A survivor is not a deployable strategy and requires genuinely new untouched confirmation data.

## Research question

Can the machine identify causal market states whose executable payoff geometry is at least 1:3 risk/reward and whose realized conditional expectancy remains strongly positive after BASE and STRESS friction?

The machine is not asked to predict every bar. It may remain flat for an entire block. There is no fallback to a merely least-bad model.

## Frozen high-R execution profile family

Every tested target is >= 3R. Stop distance is fixed from ATR14 known at signal close; target is a fixed multiple of that initial risk.

- HR1: stop 0.50 ATR, target 3R, max hold 60m
- HR2: stop 0.50 ATR, target 4R, max hold 90m
- HR3: stop 0.50 ATR, target 5R, max hold 120m
- HR4: stop 0.75 ATR, target 3R, max hold 60m
- HR5: stop 0.75 ATR, target 4R, max hold 90m
- HR6: stop 0.75 ATR, target 5R, max hold 120m
- HR7: stop 1.00 ATR, target 3R, max hold 90m
- HR8: stop 1.00 ATR, target 4R, max hold 120m
- HR9: stop 1.00 ATR, target 5R, max hold 120m
- HR10: stop 1.25 ATR, target 3R, max hold 120m

No 1.5R or 2R profile is eligible in this cycle.

## Causal feature space

Reuse the already-preregistered pooled causal feature state from Cycle 16 only:

1. numeric causal M5 state fields from autonomous_search_v3, excluding all fwd_* fields;
2. trailing completed-M1 microstructure summaries over 5/15/30 minutes;
3. exact-synchronized CNY/Si cross-instrument fields based only on completed bars;
4. time-of-day sine/cosine and instrument indicator.

All fields are known when the M5 decision candle closes.

## Labels

For every eligible M5 state, instrument, LONG/SHORT direction and frozen high-R profile:

- decision is made on the completed M5 candle;
- entry is the exact next M1 open;
- same Moscow calendar date only;
- STOP_FIRST if stop and target occur in the same M1 bar;
- target gaps are filled conservatively at the frozen target;
- force close no later than 17:00 and profile max hold;
- GROSS = 0 adverse ticks/side;
- BASE = 1 adverse tick/side;
- STRESS = 2 adverse ticks/side;
- commission excluded.

Training target is realized BASE R-multiple, where 1R is the frozen initial stop distance. BASE/STRESS bps, realized R, target-hit flag and exit timestamp are stored separately.

## Weekly causal discovery

Evaluation blocks are seven calendar days beginning 2026-03-02. For each block:

- training/selection window = previous 56 calendar days;
- most recent 14 days are validation only;
- older portion is model fitting;
- labels are usable only if their exit timestamp is strictly before the relevant fit/validation boundary.

For each profile x LONG/SHORT direction, fit HistGradientBoostingRegressor using the frozen grid:

- max_leaf_nodes: 7, 15, 31
- min_samples_leaf: 20, 50
- l2_regularization: 1, 10
- learning_rate: 0.05
- max_iter: 120
- early_stopping: false
- deterministic seed: 20260401

For each hyperparameter fit, evaluate two predeclared rarity thresholds: prediction P95 and P97.5.

A profile/direction configuration is qualified only if its actual validation tail satisfies ALL:

- >= 25 observations;
- >= 8 distinct trading dates;
- BASE PF >= 1.80;
- STRESS PF >= 1.25;
- BASE expectancy >= +0.25R/trade;
- STRESS expectancy >= +0.05R/trade;
- BASE expectancy in bps > 0;
- STRESS expectancy in bps > 0;
- largest BASE winner share <= 0.35.

No qualified configuration = that profile/direction is disabled for the next block.

Qualified configurations rank by:

1. min(BASE PF, STRESS PF);
2. min(BASE expectancy R, STRESS expectancy R);
3. number of validation dates;
4. target-hit rate.

The chosen model is refit on the full causal 56-day window and its selected validation prediction quantile is frozen for the next block.

## Sparse high-R consensus signal

On each future eligible M5 bar in the unchanged research windows 10:00–12:55 and 14:00–16:50:

- only qualified profile/direction models may vote;
- a vote exists only when prediction exceeds its frozen threshold;
- a direction requires at least 2 simultaneous profile votes;
- the agreeing votes must contain at least 2 distinct target multiples (for example 3R and 4R), preventing consensus from being only tiny stop-width variants of one payoff target;
- if both LONG and SHORT qualify simultaneously, stay flat;
- on consensus onset, execute the agreeing profile with the highest predicted BASE R;
- do not retrigger while the same directional consensus remains continuously active;
- one open position per instrument.

## Final research-survivor gate

Combined portfolio must satisfy ALL:

- BASE PF >= 2.00;
- STRESS PF >= 1.50;
- BASE mean realized R >= +0.30R/trade;
- STRESS mean realized R >= +0.10R/trade;
- 10th percentile of date-block bootstrap BASE mean R > 0;
- >= 30 BASE trades;
- >= 15 unique trading dates;
- >= 3 positive BASE calendar months;
- >= 2 positive STRESS calendar months;
- largest BASE winner share <= 0.25;
- at least 2 executed profiles and at least 2 distinct executed target-R values;
- GROSS total bps >= BASE total bps >= STRESS total bps.

Bootstrap uses whole trading dates as resampling blocks and fixed seed 20260401.

A pass remains research-only and awaits fresh untouched confirmation. The retired May16–Jul1 interval and 2025 TRUE OOS remain sealed.