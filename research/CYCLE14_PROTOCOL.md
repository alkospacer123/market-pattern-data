# Cycle 14 — Causal M1 Microstructure Executable-PnL Discovery

Preregistered before Cycle 13 results are used to alter this hypothesis class.

## Status and fences

- Research-only.
- Read only Moscow 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Any survivor requires genuinely new untouched data.

## Motivation

Prior autonomous cycles mainly consumed completed M5 aggregates. Cycle 14 tests information destroyed by M5 aggregation: the order and concentration of one-minute movements immediately before the decision.

## Decision clock

- Decisions occur on the same completed M5 timestamps used by Cycles 11-13.
- At each decision, only M1 bars whose close is known by that M5 close may be used.
- Entry is exact next M1 open.
- Eligible M5 starts: 10:00-12:55 and 14:00-16:50 Moscow.

## Frozen causal M1 microstructure features

Compute separately over trailing 5, 15, and 30 completed M1 bars, never crossing Moscow trading dates:

- cumulative return / ATR14(M5)
- sum absolute M1 returns / ATR14
- realized RMS M1 return / ATR14
- movement efficiency = abs(net move) / sum abs moves
- fraction positive M1 returns
- fraction negative M1 returns
- sign-change rate
- longest consecutive positive-return run
- longest consecutive negative-return run
- close position inside trailing high-low range
- trailing high-low range / ATR14
- maximum single-minute absolute move / ATR14
- last-minute return / ATR14
- first-half return minus second-half return / ATR14
- volume last minute / trailing median volume
- volume coefficient of variation
- largest one-minute volume share
- signed price-change x volume imbalance normalized by sum absolute price-change x volume

Additional current completed-bar context:

- M5 ATR-normalized return, body, range, close position
- distance to previous-day high/low
- distance to nearest round level
- M5 session position
- fixed time-of-day sine/cosine
- instrument indicator

No future or target-derived field is allowed.

## Executable labels

Use the same four frozen profiles as Cycles 11-13, LONG and SHORT independently:

- P1 stop 0.75 ATR14, target 1.5R, hold <=30m
- P2 stop 1.00 ATR14, target 2R, hold <=60m
- P3 stop 1.25 ATR14, target 2R, hold <=60m
- P4 stop 1.50 ATR14, target 3R, hold <=120m

Label = isolated BASE bps from exact next M1 open using STOP_FIRST and same-day force close. Training labels require exit timestamp strictly before the weekly block start.

## Causal machine

Seven-calendar-day blocks starting 2026-03-02; trailing 56-day training window, most recent 14 days as model-selection validation.

Train pooled CNYRUBF + USDRUBF `HistGradientBoostingRegressor`, separately for LONG/SHORT x P1-P4. Frozen hyperparameter grid:

- max_leaf_nodes 7, 15, 31
- min_samples_leaf 20, 50
- l2_regularization 1, 10
- learning_rate 0.05
- max_iter 120
- early_stopping false

Select hyperparameters by the validation prediction top-decile: if >=10 observations, maximize actual BASE PF then expectancy; otherwise validation MSE. Refit on full causal 56 days. Weekly trade threshold = max(0, selected validation prediction P90).

For each future decision timestamp choose the eligible side/profile with maximum predicted BASE bps. Trade state onset only; rearm after state disappears or changes.

## Execution/friction

- exact next M1 open
- one position per instrument
- same-day only, force close 17:00
- STOP_FIRST
- GROSS 0, BASE 1, STRESS 2 adverse ticks per side
- commission excluded

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

Any pass remains research-only awaiting new untouched data. 2025 stays sealed.
