# Cycle 11 — Nonlinear Causal Executable-PnL Discovery

Preregistered before Cycle 10 and Cycle 11 results are used to modify this hypothesis class.

## Data status and fences

- Research-only: all observations through 2026-05-15 belong to the research pool.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 Internal Confirmation MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Any survivor requires genuinely new untouched data.

## Goal

Find nonlinear causal combinations of ordinary market-state features that identify a sparse subset of M5 bars with high expected **real executable BASE PnL**. Unlike Cycle 6 Ridge, the target is not future close return: it is the actual isolated trade result under a frozen stop/target/time contract.

## Signal and execution universe

- Signal timeframe M5, execution M1.
- Eligible M5 starts: 10:00-12:55 and 14:00-16:50 Moscow.
- Prediction is available only after the M5 candle closes.
- Entry is exact next M1 open.
- One position at a time per instrument in portfolio simulation.
- Same Moscow day only; force close at 17:00.
- STOP_FIRST for stop/target ties.
- GROSS 0, BASE 1, STRESS 2 adverse ticks per side.
- Commission excluded.

Four frozen execution profiles:

- P1: stop 0.75 ATR14, target 1.5R, max hold 30 min.
- P2: stop 1.00 ATR14, target 2.0R, max hold 60 min.
- P3: stop 1.25 ATR14, target 2.0R, max hold 60 min.
- P4: stop 1.50 ATR14, target 3.0R, max hold 120 min.

Stop is measured from the actual raw M1 entry. Target is an R-multiple of the raw entry-to-stop risk.

## Training labels

For every eligible M5 bar, instrument, direction, and profile, compute a hypothetical isolated BASE trade using the future M1 path only after the signal is known. Save BASE bps and actual label exit timestamp.

A row is eligible to train a weekly model only if the complete label exit timestamp is strictly before that prediction block starts.

## Frozen causal features

Use numeric causal M5 fields from `autonomous_search_v3.build_features` only, excluding all `fwd_*` fields and target fields. Add:

- fixed time-of-day sine/cosine;
- instrument indicator;
- signed distance to nearest round level in ATR units already available in the causal feature set.

No future-derived feature is permitted.

## Model class

Pooled CNYRUBF + USDRUBF `HistGradientBoostingRegressor`, trained separately for LONG and SHORT for each execution profile.

Prediction blocks are seven calendar days beginning 2026-03-02. For every block:

1. Training window = trailing 56 calendar days ending strictly before block start.
2. Model-selection validation slice = most recent 14 calendar days within that window.
3. Candidate model fit slice = older portion of the 56-day window.
4. Hyperparameter grid, frozen now:
   - max_leaf_nodes: 7, 15, 31
   - min_samples_leaf: 20, 50
   - l2_regularization: 1, 10
   - learning_rate: 0.05
   - max_iter: 120
   - early_stopping: false
5. For each side/profile, candidate hyperparameters predict the causal 14-day validation slice. Define the selected tail as predictions >= their 90th percentile. If >=10 tail observations exist, rank hyperparameters by actual BASE PF of that tail, then actual BASE expectancy. If fewer than 10 exist, rank by validation MSE.
6. Refit the winning hyperparameters on the complete eligible trailing 56-day window.
7. Freeze the weekly prediction threshold as `max(0, validation prediction P90)` from the selected validation model.

## Weekly decision

For each future M5 bar in the block:

- Predict BASE bps for LONG and SHORT for all four profiles.
- A side/profile is eligible only when prediction >= its frozen weekly threshold.
- Choose the eligible side/profile with maximum predicted BASE bps.
- Consecutive M5 bars retaining the exact same chosen side/profile form one state; trade only its onset. The state rearms after no profile qualifies or the chosen side/profile changes.
- Portfolio execution then enforces one open position per instrument.

No outcome from a block can alter that block's model, threshold, profile, direction, or features.

## Reporting and diagnostics

Report weekly model hyperparameters, validation tail PF/expectancy, thresholds, prediction calibration, selected profile counts, signal count, executed trade count, monthly GROSS/BASE/STRESS PF and expectancy, concentration, CNY/Si split, and combined portfolio result.

## Strict research-survivor gate

Combined portfolio over the causal weekly prediction blocks:

- BASE PF >= 2.00
- STRESS PF >= 1.50
- positive BASE and STRESS expectancy
- >=30 BASE trades
- >=15 unique trading days
- >=3 positive BASE calendar months
- >=2 positive STRESS calendar months
- largest BASE winner share <=0.25
- total GROSS bps >= total BASE bps >= total STRESS bps

A pass is not validation and never authorizes opening 2025.
