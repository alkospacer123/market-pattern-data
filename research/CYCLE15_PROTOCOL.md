# Cycle 15 — Full-Session Causal Executable-PnL Discovery

Preregistered before Cycle 13/14 results are used to alter this hypothesis class.

## Why

Previous autonomous ML cycles inherited the manual research hours 10:00-13:00 and 14:00-17:00. A genuinely autonomous search should test whether stable edge lives elsewhere in the actual intraday session rather than assuming our original hours are correct.

## Status and fences

- Research-only.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Any survivor requires genuinely new untouched data.

## Eligible decision bars

- M5 signal timeframe, M1 execution.
- Use every completed M5 bar in the data whose exact next M1 open exists on the same Moscow trading date and whose selected profile can be force-closed on the same date.
- No fixed 10-17 filter.
- Time of day is supplied to the model as cyclic and fixed bucket features.
- The model is allowed to learn that some hours are never worth trading.

## Causal information

Use the complete numeric causal M5 feature set from `autonomous_search_v3.build_features`, excluding all `fwd_*` fields, plus:

- time-of-day sine/cosine;
- fixed 60-minute clock bucket one-hot features;
- minutes since first observed M5 bar of current trading date;
- minutes until last observed M5 bar of current trading date, where the daily final timestamp is a fixed exchange/data-calendar property learned only from timestamp availability and not price/volume/outcome;
- instrument indicator.

No future price, future volume, or target-derived feature is allowed.

## Executable labels

Same frozen four profiles as Cycles 11-14:

- P1: stop 0.75 ATR14, target 1.5R, hold <=30 min
- P2: stop 1.00 ATR14, target 2.0R, hold <=60 min
- P3: stop 1.25 ATR14, target 2.0R, hold <=60 min
- P4: stop 1.50 ATR14, target 3.0R, hold <=120 min

For LONG and SHORT separately, label = isolated BASE bps from exact next M1 open with STOP_FIRST and same-day force close. Label exit must be strictly before a weekly prediction block start before it may enter training.

## Causal weekly learner

Prediction blocks = seven calendar days beginning 2026-03-02. Training = trailing 56 calendar days, model-selection validation = most recent 14 days.

Pooled CNYRUBF + USDRUBF HistGradientBoostingRegressor, separately for LONG/SHORT x P1-P4.

Frozen hyperparameter grid:
- max_leaf_nodes 7, 15, 31
- min_samples_leaf 20, 50
- l2_regularization 1, 10
- learning_rate 0.05
- max_iter 120
- early_stopping false

Select hyperparameters by actual BASE PF then expectancy in the top 10% prediction tail on the causal validation slice, requiring >=10 tail examples; otherwise minimum MSE. Refit on the full causal 56-day window. Threshold = max(0, selected validation prediction P90).

At each future M5 bar choose the side/profile with maximum prediction above its frozen threshold; trade state onset only and enforce one open position per instrument.

## Execution/friction

- exact next M1 open;
- same Moscow trading date;
- profile time exit, additionally capped at final available M1 of that date;
- STOP_FIRST;
- GROSS 0, BASE 1, STRESS 2 adverse ticks per side;
- commission excluded.

## Strict research gate

Combined portfolio:
- BASE PF >=2.00
- STRESS PF >=1.50
- positive BASE/STRESS expectancy
- >=30 trades
- >=15 unique trading days
- >=3 positive BASE months
- >=2 positive STRESS months
- largest BASE winner share <=0.25
- GROSS total bps >= BASE >= STRESS

Any pass remains research-only awaiting fresh untouched data. 2025 stays sealed.
