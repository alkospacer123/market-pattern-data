# Cycle 23 — High-R Rule-Family Generalization

Preregistered while Cycle 22 was still running. This is a development-cycle response to the Cycle-21 observation that extremely strong 4R–6R explicit states can be too sparse to satisfy trade-count and concentration gates. March–May has already been inspected and remains research-only.

## Fences

- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Any survivor requires genuinely new untouched confirmation data.

## Question

Can a deterministic family of nearby causal states preserve high-R expectancy while increasing signal frequency, without using March–May outcomes to decide which states are grouped?

## High-R execution

- F1: 0.75 ATR stop, 4R target, 90m
- F2: 0.75 ATR stop, 5R target, 120m
- F3: 1.00 ATR stop, 4R target, 120m
- F4: 1.00 ATR stop, 5R target, force close 17:00

Exact next M1 open, same day, STOP_FIRST, conservative target-gap fill, force close 17:00, GROSS/BASE/STRESS = 0/1/2 adverse ticks per side, commission excluded.

## Causal states

Use numeric M5 features from `autonomous_search_v3.build_features`, excluding `fwd_*`, plus fixed one-hour clock states 09:00–16:59. January cutpoints are frozen.

For numeric features define nested tails:
- LOW10 <= P10
- LOW25 <= P25
- HIGH25 >= P75
- HIGH10 >= P90

## Deterministic semantic feature families

Feature grouping is based only on feature meaning/name and is fixed before outcome evaluation:

- `range_position`: `pos_*`, `dist_high_*`, `dist_low_*`, `session_pos`
- `return_momentum`: `ret_*`, `body_atr`, `body_frac`
- `efficiency`: `eff_*`
- `volatility`: `range_atr`, `vol_*`
- `volume`: `relvol_*`, `vol_z_*`
- `previous_day`: `dist_pdh_atr`, `dist_pdl_atr`, `gap_prevclose_atr`
- `round_level`: `round_dist_atr`, `round_pos`
- `candle_shape`: `close_pos_candle`, `upper_wick_frac`, `lower_wick_frac`
- `clock`: fixed hour state

No feature is moved between families based on PnL.

## Family-rule generation

Base atomic rules are all depth-1 states and target-free SHA256-capped depth-2 rules exactly as in Cycle 21.

For every depth-2 base rule with features from two different semantic families, generate only the following deterministic generalizations:

1. exact rule unchanged;
2. relax first numeric state `HIGH10→HIGH25` or `LOW10→LOW25`, if applicable;
3. relax second numeric state likewise;
4. relax both numeric states likewise;
5. same-state substitution of the first feature by each other feature in its semantic family with the same tail direction/width;
6. same-state substitution of the second feature by each other feature in its semantic family;
7. OR-union of the exact rule and each one-feature substitution from steps 5–6.

A generalization is defined from feature names/families only. No March–May outcome may influence generation.

Exact duplicate masks are deduplicated. Candidate family masks require at least 20 Jan–Feb state observations before outcome evaluation. If more than 5,000 unique family masks exist per instrument, retain the first 5,000 by canonical SHA256 rank, target-free.

Signal = false→true family-mask onset within the same Moscow date. Eligible bars 09:00–16:50.

## Jan–Feb development gate

The same family mask/direction/profile must satisfy January and February separately:
- >= 8 executable observations/month;
- >= 5 dates/month;
- BASE mean R >= +0.10R/month;
- STRESS mean R > 0/month;
- BASE PF >= 1.25/month.

Combined Jan–Feb:
- >= 22 observations;
- >= 12 dates;
- BASE PF >= 2.0;
- STRESS PF >= 1.5;
- BASE mean R >= +0.35R;
- STRESS mean R >= +0.15R;
- target-hit rate >= theoretical gross break-even + 0.04;
- largest BASE winner share <= 0.30.

No pass = no candidate. Freeze at most 40 candidates/instrument, max 2 per identical family mask+direction.

## Research stability evaluation on March–May

A `FAMILY_HIGH_R_RESEARCH_SURVIVOR` requires:
- BASE PF >= 2.0;
- STRESS PF >= 1.5;
- BASE mean R >= +0.30R;
- STRESS mean R >= +0.10R;
- >= 20 trades;
- >= 12 dates;
- >= 2 positive BASE months;
- >= 2 positive STRESS months;
- whole-date bootstrap P10 BASE mean R > 0;
- largest BASE winner share <= 0.25;
- GROSS total bps >= BASE >= STRESS.

March–May results do not feed back into family generation or Jan–Feb ranking. Because March–May has already been viewed in earlier cycles, a pass is research evidence only.
