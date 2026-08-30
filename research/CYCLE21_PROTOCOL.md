# Cycle 21 — Direct High-R Barrier Rule Mining

Preregistered after Cycles 17–20 showed repeated validation-tail instability. This cycle removes supervised model-tail selection entirely and searches explicit causal state rules against high-R executable outcomes.

## Fences and status

- Research-only.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- March–May is research walk-forward only, not fresh confirmation, because it has been inspected in prior research cycles.

## Question

Do simple, explicit causal market states exist that repeatedly produce executable 4R–6R outcomes with a short stop, rather than only appearing as unstable high-confidence tails of a fitted ML model?

## Execution profiles

Raw stop distance = `max(stop_atr * ATR14, 5 ticks)`.

- R1: 0.50 ATR stop, 4R target, max 90m
- R2: 0.50 ATR stop, 5R target, max 120m
- R3: 0.50 ATR stop, 6R target, max 120m
- R4: 0.75 ATR stop, 4R target, max 90m
- R5: 0.75 ATR stop, 5R target, max 120m
- R6: 0.75 ATR stop, 6R target, max 120m

LONG and SHORT are searched independently. No target below 4R is allowed in Cycle 21.

Execution remains exact next M1 open, same-day only, force close at 17:00, STOP_FIRST, conservative target-gap fill, GROSS 0 / BASE 1 / STRESS 2 adverse ticks per side, commission excluded.

## Causal feature state

Use numeric causal M5 features produced by `autonomous_search_v3.build_features`, excluding all `fwd_*` fields and excluding outcome-derived values.

State cutpoints are fit once using JANUARY 2026 feature values only and then frozen for all later dates.

Each numeric feature may generate four explicit tail states:
- LOW10 = <= January P10
- LOW25 = <= January P25
- HIGH25 = >= January P75
- HIGH10 = >= January P90

Fixed one-hour Moscow clock buckets from 09:00 through 16:59 are also eligible explicit states. Time buckets are fixed by clock and are never fitted.

Only M5 decision bars starting from 09:00 through 16:50 are eligible, giving the machine access to the full practical intraday session rather than inheriting the old manual 10–13 / 14–17 restriction.

## Rule family

Rules have depth 1 or 2 only.

- all eligible univariate feature-state rules are evaluated;
- depth-2 interactions require two different features;
- candidate interaction generation is TARGET-FREE;
- after removing pairs with fewer than 20 Jan–Feb raw state observations, interaction strings are canonically sorted and ranked by SHA256;
- retain exactly the first 1,500 eligible interaction pairs (or all if fewer exist);
- no outcome/PF/expectancy value may influence which interaction pairs enter the search family;
- exact duplicate state masks are deduplicated before outcome evaluation.

This prevents adaptive beam-search from manufacturing rare high-PF rules.

## Signal semantics

A rule is active when its complete state mask is true. Only false-to-true state onset within the same Moscow date is a signal; a continuously true state does not fire repeatedly.

## Jan–Feb discovery gate

For each instrument x rule x LONG/SHORT x execution profile, evaluate isolated executable outcomes on state onsets.

The SAME frozen rule/profile/direction must satisfy January and February separately:

Per month:
- >= 6 executable signal observations;
- >= 4 distinct trading dates;
- BASE mean realized R >= +0.10R;
- STRESS mean realized R > 0;
- BASE PF >= 1.25;
- target-hit rate >= theoretical gross break-even `1/(target_R+1)`.

Combined January+February:
- >= 16 executable observations;
- >= 10 distinct dates;
- BASE PF >= 2.00;
- STRESS PF >= 1.35;
- BASE mean R >= +0.35R;
- STRESS mean R >= +0.10R;
- positive BASE/STRESS expectancy in bps;
- target-hit rate >= `1/(target_R+1) + 0.04`;
- largest BASE winner share <= 0.35.

No pass = no candidate. There is no least-bad fallback.

## Frozen shortlist

Rank passing Jan–Feb candidates only by:
1. minimum of January and February BASE mean R;
2. minimum of combined BASE PF and STRESS PF;
3. combined STRESS mean R;
4. number of distinct discovery dates;
5. canonical rule id.

Freeze at most 30 candidates per instrument. To reduce near-duplicate selection, at most 2 candidates may share the same exact rule mask and direction.

## March–May research walk-forward

The frozen January cutpoints, rule definition, direction, stop, target and hold are applied unchanged to 2026-03-01 through 2026-05-15.

A forward `HIGH_R_RULE_SURVIVOR` must satisfy:
- BASE PF >= 2.00;
- STRESS PF >= 1.50;
- BASE mean R >= +0.30R;
- STRESS mean R >= +0.10R;
- whole-day bootstrap P10 BASE mean R > 0, seed 20260401;
- >= 20 BASE trades;
- >= 12 unique dates;
- >= 2 positive BASE calendar months;
- >= 2 positive STRESS calendar months;
- largest BASE winner share <= 0.30;
- GROSS total bps >= BASE >= STRESS.

Each candidate is reported independently. No March–May result feeds back into rule creation, ranking, or parameter choice.

Any survivor remains research-only and requires genuinely new untouched future confirmation data.