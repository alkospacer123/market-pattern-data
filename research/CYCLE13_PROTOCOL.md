# Cycle 13 — Cross-Instrument Lead/Lag Executable-PnL Discovery

Preregistered before Cycle 12 results are used to modify this hypothesis class.

## Status and fences

- Research-only.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Any survivor requires genuinely new untouched data.

## Motivation

Cycle 11 modeled CNYRUBF and USDRUBF from their own normalized state. Cycle 13 explicitly tests whether completed movements in one currency future contain incremental causal information about the executable future PnL of the other.

## Synchronization

- Exact synchronized M5 timestamps only.
- Signal decision occurs after both M5 bars at timestamp `t` are complete.
- Individual target-instrument execution is exact next M1 open.
- No as-of or forward timestamp matching.

## Causal joint features

For each synchronized completed M5 bar, include for both CNYRUBF and USDRUBF:

- ret_5m_atr, ret_15m_atr, ret_30m_atr, ret_60m_atr, ret_120m_atr
- body_atr, range_atr, close_pos_candle
- pos_30m, pos_60m, pos_120m
- dist_high_60m_atr, dist_low_60m_atr
- eff_30m, eff_60m
- vol_15m_60m, vol_30m_120m
- relvol_60m
- round_dist_atr
- dist_pdh_atr, dist_pdl_atr
- session_pos

Add fixed joint features computed only from completed bars:

- CNY minus USD normalized returns for 5/15/30/60 minutes;
- sign agreement for those four horizons;
- rolling Pearson correlation of 5-minute normalized returns over the previous 12 and 36 completed M5 bars, with the current pair excluded by shift(1);
- rolling beta CNY-ret_5m on USD-ret_5m over the previous 36 completed bars, current bar excluded;
- current completed-bar residual `CNY_ret_5m - beta_prior * USD_ret_5m`;
- fixed time-of-day sine/cosine.

No `fwd_*` feature is allowed.

## Executable target labels

For each target instrument separately and for LONG/SHORT under the same four frozen execution profiles as Cycles 11-12:

- P1: stop 0.75 ATR14, target 1.5R, hold <=30 min
- P2: stop 1.00 ATR14, target 2.0R, hold <=60 min
- P3: stop 1.25 ATR14, target 2.0R, hold <=60 min
- P4: stop 1.50 ATR14, target 3.0R, hold <=120 min

Label = isolated BASE bps from exact next M1 open, STOP_FIRST, same-day force close. Save label exit timestamp. A training label may be used only when its exit timestamp is strictly earlier than the weekly prediction block start.

## Causal weekly machine

Seven-day prediction blocks begin 2026-03-02. For each block:

1. Training window = trailing 56 calendar days ending before block start.
2. Model-selection validation = most recent 14 days inside that window.
3. Train separate `HistGradientBoostingRegressor` for each target instrument x LONG/SHORT x P1-P4.
4. Frozen hyperparameter grid:
   - max_leaf_nodes: 7, 15, 31
   - min_samples_leaf: 20, 50
   - l2_regularization: 1, 10
   - learning_rate: 0.05
   - max_iter: 120
   - early_stopping: false
5. Hyperparameter selection uses the 90th-percentile predicted-PnL tail on the causal 14-day validation slice: maximize actual BASE PF, then expectancy, requiring >=10 tail rows; otherwise minimum MSE.
6. Refit on the full causal 56-day training window.
7. Weekly eligibility threshold = `max(0, validation prediction P90)`.

## Trading decision

For each target instrument and future synchronized M5 bar:

- Predict BASE bps for all eight side/profile alternatives belonging to that target instrument.
- Select the largest prediction above its frozen threshold.
- Trade state onset only; repeated consecutive bars with same side/profile do not re-enter until the state switches or turns off.
- Enforce one open position per target instrument.

No future block result affects its own model or threshold.

## Execution and friction

- exact next M1 open;
- same-day only, force close 17:00;
- STOP_FIRST;
- GROSS 0, BASE 1, STRESS 2 adverse ticks per side;
- commission excluded.

## Strict research gate

Combined two-instrument portfolio:

- BASE PF >=2.00
- STRESS PF >=1.50
- positive BASE/STRESS expectancy
- >=30 BASE trades
- >=15 unique trading days
- >=3 positive BASE months
- >=2 positive STRESS months
- largest BASE winner share <=0.25
- GROSS total bps >= BASE >= STRESS

Any pass remains research-only awaiting fresh data. 2025 stays sealed.
