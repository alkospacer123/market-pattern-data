# Cycle 8 — Equal-Level Passive Retest Execution

Preregistered before Cycle 8 results.

## Status and data fence

Cycle 8 is retrospective research only. It may read only 2026-01-05 through 2026-05-15. The retired 2026-05-16 through 2026-07-01 confirmation window MUST NOT be read. 2025 TRUE OOS remains SEALED.

Cycle 7 showed that the best CNY equal-level reversal had positive GROSS expectancy but lost its edge under one adverse tick per side. Cycle 8 changes execution, not the core signal family.

## Signal family

Use the exact twelve preregistered Cycle 7 M5 signal variants:

- tolerance_ticks: 0 or 1
- touch_lookback_bars: 1, 3, or 6
- rejection_ticks: 0 or 1
- same round steps, sessions, second-touch semantics, and contiguous-cluster suppression as Cycle 7.

## Passive retest entry

After the M5 signal candle closes:

- Place a passive order at the signaled round level.
- Order lifetime: 15 minutes, never beyond the current session or 16:59.
- LONG: buy limit at the round level.
- SHORT: sell limit at the round level.
- If price never qualifies for a conservative fill before expiry, no trade.

Fill assumptions:

- GROSS: a touch of the level is sufficient.
- BASE: price must trade through the limit by at least 1 tick.
- STRESS: price must trade through the limit by at least 2 ticks.
- When filled, execution price is still recorded at the limit level; no favorable price improvement is credited.
- If the first eligible M1 open is already through the limit, fill is still recorded at the level, not at the better opening price.

This models queue/fill uncertainty instead of adverse market-entry slippage. Exit slippage remains adverse:

- GROSS: 0 adverse ticks on exit.
- BASE: 1 adverse tick on exit.
- STRESS: 2 adverse ticks on exit.
- Commission excluded.

## Stop/target grid

Stop is outside the round level by a fixed buffer:

- stop_buffer_ticks: 3, 5, 8, 13
- target_rr: 2, 3, 4

LONG stop = level - stop_buffer_ticks * tick.
SHORT stop = level + stop_buffer_ticks * tick.
Target is target_rr times the raw level-to-stop risk.

No execution parameter is optimized on March-May outcomes.

## Causal selection / retrospective walk-forward

For each instrument and each of the 12 signal variants:

1. Choose stop_buffer_ticks and target_rr using only 2026-01-05 through 2026-02-28.
2. Training eligibility requires at least 12 BASE trades, positive BASE and STRESS expectancy, and BASE/STRESS PF > 1.
3. Rank eligible executions by the lower of BASE PF and STRESS PF, then by STRESS expectancy.
4. Freeze the best execution for that signal variant.
5. Evaluate the frozen variant on three retrospective forward folds: March, April, and 2026-05-01 through 2026-05-15.

The forward folds are NOT untouched OOS because earlier research has already inspected this period. They are used only as internal robustness checks.

## Forward research gates

A Cycle 8 research survivor must satisfy over the combined Mar-May forward folds:

- BASE PF >= 1.50
- STRESS PF >= 1.20
- positive BASE and STRESS expectancy
- >= 20 BASE trades
- >= 12 unique days
- all 3 forward folds positive in BASE
- at least 2 of 3 forward folds positive in STRESS
- largest winner share <= 0.25
- at least one adjacent stop-buffer or RR setting also has BASE PF >= 1.25 and STRESS PF >= 1.0 with positive expectancy.

A survivor remains `RESEARCH_ONLY_AWAITING_NEW_CONFIRMIRMATION_DATA`; Cycle 8 never authorizes opening 2025.
