# Cycle 6 — Pooled Causal Ridge Forecast

Preregistered before Cycle 6 results.

## Data fence

- Read only 2026-01-05 through 2026-05-15.
- Retired 2026-05-16 onward data MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Cycle 6 is research-only until new untouched data exists.

## Model

- Signal timeframe M5, execution M1.
- Pool CNYRUBF and USDRUBF in one ATR-normalized linear Ridge model.
- Refit once per 7-calendar-day block.
- Evaluation begins 2026-03-02.
- Each refit uses only the trailing 56 calendar days ending strictly before the block.
- Target is same-day forward 30-minute close return divided by current ATR14.
- Rows whose target horizon is not fully known before the block start are excluded.

## Fixed causal features

ATR-normalized returns, candle body/range/wicks, rolling-range position and distance, volatility ratios, relative volume, distance to previous-day high/low/close, round-level distance/position, session position, and fixed time-of-day sine/cosine. Instrument identity is not used as a numeric price feature.

## Regularization choice

Ridge alpha is chosen causally from `[1, 10, 100]`: fit on the older part of the trailing window and choose the alpha with lowest MSE on the most recent 14 calendar days, then refit that alpha on the full trailing window.

## Trade threshold

The absolute forecast threshold is the greater of `0.10 ATR` and the 80th percentile of absolute predictions on the causal 14-day validation slice. This controls trade frequency without optimizing trading PnL.

## Execution

- Prediction known after M5 close.
- Enter exact next M1 open.
- Long when prediction first crosses above +threshold; short when it first crosses below -threshold.
- One position at a time per instrument.
- Protective stop = 1.5 ATR14 from entry.
- No profit target.
- Time exit = 30 minutes after entry, same Moscow day.
- STOP_FIRST for stop interaction.
- GROSS 0 adverse ticks/side; BASE 1; STRESS 2.
- Commission excluded.

## Research gates

Combined two-instrument result:
- BASE PF >= 1.30
- STRESS PF >= 1.10
- positive BASE/STRESS expectancy
- >= 30 trades
- >= 15 unique days
- >= 2 positive months in BASE and STRESS
- largest winner share <= 0.25

A pass is not confirmation and does not authorize opening 2025.
