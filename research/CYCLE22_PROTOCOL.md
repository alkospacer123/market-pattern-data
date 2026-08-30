# Cycle 22 — Stress-First High-R Cost-Margin Discovery

Preregistered while Cycle 21 was still running. Cycle 22 is independent of the eventual Cycle-21 result and follows the repeated Cycle-17–20 observation that BASE high-R expectancy can be positive while one additional adverse tick destroys the edge.

## Fences and status

- Research-only.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- March–May is research walk-forward only, not fresh confirmation.

## Question

Can the machine identify rare causal states whose payoff remains strongly positive under STRESS execution, rather than merely positive under BASE execution?

The machine may remain flat for any week/instrument. There is no least-bad fallback.

## Frozen high-R profiles

Use moderate stop widths so one tick is not an overwhelming fraction of initial risk:

- S1: 0.75 ATR stop, 3R target, max hold 90m
- S2: 0.75 ATR stop, 4R target, max hold 120m
- S3: 0.75 ATR stop, 5R target, max hold to 17:00
- S4: 1.00 ATR stop, 3R target, max hold 90m
- S5: 1.00 ATR stop, 4R target, max hold 120m
- S6: 1.00 ATR stop, 5R target, max hold to 17:00
- S7: 1.25 ATR stop, 3R target, max hold 120m
- S8: 1.25 ATR stop, 4R target, max hold to 17:00
- S9: 1.25 ATR stop, 5R target, max hold to 17:00

No target below 3R is eligible. There is no minimum-tick stop floor because these stops are intentionally moderate; actual stop ticks are reported.

Execution: completed M5 decision bar, exact next M1 open, same Moscow day, STOP_FIRST, conservative target-gap fill, force close 17:00, GROSS 0 / BASE 1 / STRESS 2 adverse ticks per side, commission excluded.

## Causal feature state

Use only already-preregistered causal information:

1. numeric M5 state fields from `autonomous_search_v3.build_features`, excluding `fwd_*`;
2. completed-M1 microstructure summaries over 5/15/30 minutes;
3. synchronized CNY/Si causal context from completed bars;
4. fixed time-of-day sine/cosine and instrument indicator.

Eligible M5 bars are 09:00 through 16:50 Moscow. Instrument labels are fit separately as in Cycle 19; cross-instrument market state may remain a causal predictor.

## Stress-first labels

For every instrument x direction x profile store:

- GROSS, BASE and STRESS bps;
- GROSS, BASE and STRESS realized R;
- target-before-stop flag;
- raw initial risk in ticks;
- exit timestamp.

The primary regression target is **STRESS realized R**, not BASE R.

A secondary classifier predicts whether the frozen target is reached before stop/time exit.

Additionally define executable cost margin:

`cost_margin_R = STRESS_realized_R - 0.10`.

The model is rewarded for states with actual positive margin after the required +0.10R stress hurdle, not for weak gross predictability.

## Weekly causal fit

Seven-day blocks begin 2026-03-02.

- causal training window: prior 56 calendar days;
- latest 14 days: validation only;
- outcomes are usable only when exit time is strictly before the relevant boundary;
- fit each instrument x direction x profile independently.

Frozen HGB grid:
- max_leaf_nodes: 7, 15, 31
- min_samples_leaf: 20, 40
- l2_regularization: 1, 10
- learning_rate: 0.05
- max_iter: 120
- early_stopping: false
- seed: 20260401

For every hyperparameter fit evaluate prediction tails P95 and P97.5. A future profile is enabled only if one validation tail satisfies ALL:

- >= 12 tail observations;
- >= 5 distinct dates;
- STRESS PF >= 1.60;
- STRESS mean realized R >= +0.20R/trade;
- BASE PF >= 2.00;
- BASE mean realized R >= +0.30R/trade;
- positive BASE/STRESS expectancy in bps;
- actual target-hit rate >= theoretical gross break-even `1/(target_R+1) + 0.05`;
- largest STRESS winner share <= 0.40;
- median raw stop >= 8 ticks, preventing a nominal high-R profile whose risk is too small relative to execution cost.

No qualifying tail = profile/direction/instrument disabled for the next block. No fallback.

Qualified configurations rank by:
1. STRESS mean R;
2. STRESS PF;
3. minimum(BASE PF, STRESS PF);
4. target-hit rate;
5. distinct validation dates.

The selected model is refit on the full causal 56-day window; its validation prediction quantile and classifier probability threshold are frozen for the next week.

## Future signal

A profile may vote only when:
- its predicted STRESS R exceeds its frozen tail threshold;
- target-hit probability exceeds its frozen classifier threshold;
- predicted STRESS R itself is >= +0.20R.

If only one direction has votes, execute the voting profile with highest predicted STRESS R. If LONG and SHORT both vote, stay flat. Trade only on directional consensus onset; one open position per instrument.

## Research survivor gate

Report each instrument independently. An instrument is a `STRESS_HIGH_R_RESEARCH_SURVIVOR` only if ALL hold on March–May research walk-forward:

- STRESS PF >= 1.50;
- STRESS mean realized R >= +0.15R/trade;
- BASE PF >= 2.00;
- BASE mean realized R >= +0.30R/trade;
- whole-trading-date bootstrap P10 STRESS mean R > 0, seed 20260401;
- >= 20 trades;
- >= 12 unique trading dates;
- >= 2 positive STRESS calendar months;
- >= 2 positive BASE calendar months;
- largest STRESS winner share <= 0.30;
- at least 2 distinct target-R levels executed;
- GROSS total bps >= BASE >= STRESS.

Combined portfolio is reported but does not force a weak instrument into a strong one.

Any pass remains research-only and requires genuinely new untouched future confirmation. Retired May16–Jul1 and 2025 remain sealed.
