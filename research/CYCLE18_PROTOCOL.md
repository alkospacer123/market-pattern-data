# Cycle 18 — Ultra-Short Stop Barrier Mining

Preregistered while Cycle 17 was still running. Cycle 18 is an independent high-R research class, not a post-hoc repair of Cycle 17.

## Status and data fences

- Research-only autonomous discovery.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Any survivor requires genuinely new untouched confirmation data.

## Research question

Can the machine identify rare causal states in which a very short protective stop is compensated by a 3R–6R target and positive executable expectancy after friction?

The machine is allowed to stay flat for any week. There is no fallback to the least-bad model.

## Frozen ultra-short-stop profiles

Raw stop distance is `max(stop_atr * ATR14, 5 ticks)` so that the stop cannot become a sub-execution-noise artifact. Target is a fixed multiple of the resulting raw initial risk.

- XS1: stop 0.25 ATR, target 3R, max hold 45m
- XS2: stop 0.25 ATR, target 4R, max hold 60m
- XS3: stop 0.25 ATR, target 5R, max hold 90m
- XS4: stop 0.35 ATR, target 3R, max hold 45m
- XS5: stop 0.35 ATR, target 4R, max hold 60m
- XS6: stop 0.35 ATR, target 5R, max hold 90m
- XS7: stop 0.50 ATR, target 3R, max hold 60m
- XS8: stop 0.50 ATR, target 4R, max hold 90m
- XS9: stop 0.50 ATR, target 5R, max hold 120m
- XS10: stop 0.50 ATR, target 6R, max hold 120m

No target below 3R is permitted.

## Causal feature space

Reuse the already-preregistered Cycle-16 pooled causal state only:

1. numeric causal M5 state fields, excluding all `fwd_*` fields;
2. trailing completed-M1 microstructure summaries over 5/15/30 minutes;
3. exact-synchronized CNY/Si cross-instrument fields based only on completed bars;
4. time-of-day sine/cosine and instrument indicator.

All fields are known when the M5 decision candle closes.

## Executable barrier labels

For each eligible M5 bar, instrument, direction and profile:

- decision after completed M5 bar;
- exact next M1 open entry;
- initial raw risk = `max(stop_atr * ATR14, 5 ticks)`;
- target = entry +/- target_R * raw risk;
- same Moscow date only;
- STOP_FIRST if stop and target are both touched in one M1 bar;
- favorable target gaps filled conservatively at target;
- time exit at profile max hold or 17:00, whichever comes first;
- GROSS 0 adverse ticks/side, BASE 1, STRESS 2;
- commission excluded.

Store separately: BASE/STRESS bps, BASE/STRESS realized R, target-before-stop flag, raw stop ticks, whether the 5-tick floor was active, and exit timestamp.

## Dual-model causal discovery

Weekly evaluation blocks begin 2026-03-02. Training window = previous 56 calendar days; latest 14 days are validation only. Labels are usable only if exit time is strictly before the relevant fit/validation boundary.

For every profile x LONG/SHORT direction fit two models on the older part of the window:

1. `HistGradientBoostingRegressor` predicting realized BASE R;
2. `HistGradientBoostingClassifier` predicting whether the target is reached before stop/time exit.

Both use the same frozen hyperparameter grid:
- max_leaf_nodes: 7, 15
- min_samples_leaf: 30, 60
- l2_regularization: 1, 10
- learning_rate: 0.05
- max_iter: 120
- early_stopping: false
- seed: 20260401

For each shared hyperparameter configuration on the 14-day validation slice:

- regression threshold = prediction P95;
- target-hit probability threshold = probability P75;
- validation tail = rows satisfying BOTH thresholds.

A profile/direction is qualified only if the actual dual-model validation tail satisfies ALL:

- >= 20 observations;
- >= 7 distinct trading dates;
- BASE PF >= 2.00;
- STRESS PF >= 1.35;
- BASE mean realized R >= +0.35R/trade;
- STRESS mean realized R >= +0.10R/trade;
- BASE/STRESS expectancy in bps > 0;
- target-hit rate >= theoretical gross break-even hit rate `1/(target_R+1)` + 5 percentage points;
- largest BASE winner share <= 0.35.

No qualified configuration means the profile/direction is disabled for the next week. There is no MSE fallback and no performance-chasing fallback.

Among qualified configurations rank by:
1. min(BASE PF, STRESS PF);
2. min(BASE mean R, STRESS mean R);
3. target-hit rate;
4. number of distinct validation dates.

Refit both selected models on the full causal 56-day window. Freeze the validation P95 regression threshold and P75 classifier threshold for the next week.

## Future signal

For each future eligible M5 bar in the unchanged research windows 10:00–12:55 and 14:00–16:50:

- a profile may vote only if it was qualified before the week;
- regression prediction must exceed its frozen P95 threshold;
- target-hit probability must exceed its frozen P75 threshold;
- if profiles vote only LONG, choose the profile with highest predicted BASE R;
- if profiles vote only SHORT, choose the profile with highest predicted BASE R;
- if LONG and SHORT both vote, stay flat;
- trade only on directional state onset; rearm after the direction turns off or changes;
- one open position per instrument.

This cycle deliberately does NOT require two execution-profile votes: the independent regression + barrier-classifier agreement is the consensus mechanism.

## Final research-survivor gate

Combined CNY + Si portfolio must satisfy ALL:

- BASE PF >= 2.00;
- STRESS PF >= 1.50;
- BASE mean realized R >= +0.30R/trade;
- STRESS mean realized R >= +0.10R/trade;
- 10th percentile of whole-trading-date bootstrap BASE mean R > 0, seed 20260401;
- >= 30 BASE trades;
- >= 15 unique trading dates;
- >= 3 positive BASE calendar months;
- >= 2 positive STRESS calendar months;
- largest BASE winner share <= 0.25;
- >= 2 executed profiles and >= 2 distinct target-R levels;
- GROSS total bps >= BASE >= STRESS;
- median raw stop <= 0.60 ATR-equivalent OR the five-tick floor activation is explicitly reported; no hidden stop widening.

A pass is research-only and awaits fresh untouched confirmation. Retired May16-Jul1 and 2025 remain sealed.
