# Cycle 12 — Historical Analog Pattern Mining

Preregistered before Cycle 11 results are used to alter this hypothesis class.

## Status and fences

- Research-only.
- Read only 2026-01-05 through 2026-05-15 Moscow.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Any survivor requires genuinely new untouched data.

## Idea

No named trading setup is supplied. Represent the recent market as a normalized M5 sequence, find the most similar historical sequences whose future trade outcomes are already completely known, and trade only when several neighbor depths independently show a profitable executable outcome in the same direction/profile.

## Causal sequence representation

For every eligible M5 bar, construct a 6-bar sequence ending at the current completed bar. For each of the six bars include:

- ret_5m_atr
- body_atr
- range_atr
- close_pos_candle
- relvol_60m
- pos_60m
- dist_high_60m_atr
- dist_low_60m_atr
- dist_pdh_atr
- dist_pdl_atr

Add current fixed time-of-day sine/cosine and instrument indicator. All inputs are causal fields from `autonomous_search_v3`; no `fwd_*` field is allowed.

Eligible M5 starts: 10:00-12:55 and 14:00-16:50 Moscow.

## Executable labels

Use the same four frozen profiles as Cycle 11:

- P1: stop 0.75 ATR14, target 1.5R, hold <=30 min
- P2: stop 1.00 ATR14, target 2.0R, hold <=60 min
- P3: stop 1.25 ATR14, target 2.0R, hold <=60 min
- P4: stop 1.50 ATR14, target 3.0R, hold <=120 min

For LONG and SHORT separately, calculate isolated BASE bps from exact next M1 open with STOP_FIRST, same-day force-close, and 1 adverse tick per side. Save label exit time. A historical analog may be used only if its complete label exit is strictly before the query block start.

## Weekly causal analog engine

Seven-calendar-day blocks begin 2026-03-02.

For each block:

1. Historical analog pool = trailing 56 calendar days ending strictly before block start, with labels completely known before block start.
2. Fit median imputation, StandardScaler, and PCA(12) only on that historical pool.
3. Pool CNYRUBF and USDRUBF after ATR normalization; instrument indicator remains in the vector.
4. For every future query bar, find the 100 nearest historical vectors by Euclidean distance in PCA space.
5. Evaluate neighbor depths K = 25, 50, 100 for each LONG/SHORT × P1-P4 outcome.
6. A candidate side/profile is eligible only when at least two K depths have BASE PF >=1.50, positive BASE expectancy, and win rate >0.50 among their historical labels.
7. Candidate score = minimum positive expectancy across its eligible K depths, multiplied by `sqrt(number_of_eligible_depths)`.
8. Choose the side/profile with the highest score. If none qualify, stay flat.
9. Trade only state onset: consecutive bars retaining the same chosen side/profile are one state; rearm when no candidate qualifies or selected side/profile changes.

There is no optimization on the future block.

## Real execution

- Exact next M1 open.
- One position per instrument.
- Same-day only; force close 17:00.
- STOP_FIRST.
- GROSS 0, BASE 1, STRESS 2 adverse ticks per side.
- Commission excluded.

## Strict research gate

Combined causal block portfolio:

- BASE PF >=2.00
- STRESS PF >=1.50
- positive BASE/STRESS expectancy
- >=30 BASE trades
- >=15 unique trading days
- >=3 positive BASE calendar months
- >=2 positive STRESS calendar months
- largest BASE winner share <=0.25
- GROSS total bps >= BASE >= STRESS

A pass is only a research survivor awaiting new data; 2025 remains sealed.
