# Discovery Objective v3 — high-return autonomous search

Purpose: define the objective of the future local autonomous research machine. This document governs DISCOVERY, not the separate deep stress-testing workflow.

## Scope of this chat / engine

The engine continuously searches for causal trading regularities with high profitability, high return, adequate sample size and temporal stability on CNYRUBF and USDRUBF/Si, independently on M1 and M5.

Deep post-discovery stress testing of specific retained candidates may be performed in a separate workflow. Discovery itself must still reject obviously fragile one-point artifacts through causal execution, temporal splits and parameter-neighborhood checks.

## CMD source-code role

Historical CMD Python sources in the user's Library (including round-level M5 and M1 optimizers) are reference implementations and idea generators. They are NOT the ceiling of the search space. The new engine should reuse good engineering patterns such as deterministic enumeration, reusable trade-master construction, TOP_PF/TOP_EXPECTANCY/TOP_PROFIT/TOP_ROBUST outputs and parameter-neighborhood analysis, while extending the searched semantic families far beyond round-level touches.

Historical CMD winning parameter rows must not be used as formal discovery seeds. Their semantic families may motivate generic broad grids.

## Primary objective

Find multiple independent candidate families that combine:

1. high total return (Total R and return per month / per active day),
2. high expectancy per trade,
3. high PF,
4. adequate N and independent trading dates,
5. low/moderate drawdown in R,
6. temporal stability,
7. genuine local parameter robustness,
8. executable causal entries,
9. diversity across instruments, timeframes and mechanisms.

No single scalar metric defines a winner.

## Mandatory ranking views

For every instrument × timeframe × family, persist at least:

- TOP_TOTAL_R
- TOP_RETURN_RATE
- TOP_EXPECTANCY
- TOP_PF
- TOP_ROBUST
- TOP_SAMPLE
- PARETO_FRONT

The Pareto front must retain candidates that are non-dominated across return, expectancy, PF, N/dates, drawdown and robustness rather than collapsing everything into one score.

## Search families — broad catalogue

The machine must systematically rotate through and combine causal families. At minimum support / eventually implement:

### Level / price geometry
- ROUND_TOUCH
- ROUND_APPROACH_REJECTION
- ROUND_BREAKOUT
- ROUND_FALSE_BREAKOUT
- ROUND_ACCEPTANCE_RETEST
- EQUAL_HIGH_LOW
- REPEATED_TEST_CLUSTER
- PREV_DAY_HIGH_LOW
- PREV_SESSION_HIGH_LOW
- CURRENT_SESSION_HIGH_LOW
- OPEN_RANGE
- ROLLING_HIGH_LOW
- CAUSAL_FRACTAL_LEVEL
- PIVOT_CLUSTER
- MIRROR_LEVEL / role reversal

### Compression / expansion
- BALANCE_RANGE
- BBW_COMPRESSION
- ATR_COMPRESSION
- INSIDE_BAR_CLUSTER
- NARROW_RANGE
- COMPRESSION_BREAKOUT
- COMPRESSION_FALSE_BREAK
- EXPANSION_AFTER_COMPRESSION

### Trend / pullback / continuation
- EMA_TREND_PULLBACK
- STRUCTURE_TREND_PULLBACK
- BREAKOUT_PULLBACK
- MOMENTUM_CONTINUATION
- HIGHER_HIGH_LOWER_LOW continuation
- TREND_EXHAUSTION reversal

### Sweep / reclaim / liquidity-style geometry
- SWEEP_RECLAIM
- STOP_RUN_REJECTION
- FAILED_BREAK
- DOUBLE_SWEEP
- PROBE_RECLAIM
- SECOND_TOUCH

### Candle / microstructure geometry
- WICK_REJECTION
- BODY_EXPANSION
- CLOSE_LOCATION
- ENGULF / outside-bar geometry
- multi-bar impulse/retrace
- M1 micro-pattern sequences

### Volatility / regime-conditioned patterns
- ATR_STATE
- RANGE_STATE
- EFFICIENCY_STATE
- VOLATILITY_EXPANSION
- VOLATILITY_CONTRACTION
- time-of-day regime

### Cross-instrument relations
- CNY↔Si lead/lag
- spread / ratio deviation
- relative-strength divergence
- conditional response of one instrument to the other's level/event

New families may be added when previous-cycle diagnostics suggest a causal hypothesis. Do not repeatedly mutate one family forever if it stops yielding improvements.

## Generic parameter exploration

The engine should use broad finite grids and staged refinement rather than narrow hand-picked grids.

Stage A: coarse broad enumeration.
Stage B: refine around promising semantic clusters.
Stage C: test one-axis neighbors and nearby semantic variants.
Stage D: freeze candidates for research-forward evaluation.

Refinement is driven by cluster-level evidence, never by selecting one lucky row and tuning around its individual losses.

## Return-focused metrics

For every candidate record:

- trades
- trading_dates
- wins / losses
- PF
- Total_R
- Avg_R / expectancy_R
- return_R_per_month
- return_R_per_20_trading_days
- max_DD_R
- return_to_DD = Total_R / max_DD_R when defined
- largest_winner_share
- median_R
- losing_streak
- month/block breakdown
- parameter-neighbor statistics

Where price/bps accounting is available, also persist expectancy_bps and total_bps.

## Candidate retention tiers

The registry should not save only formal survivors.

- HIGH_RETURN_RESEARCH_POSITIVE: strong return and positive robust family, but not full survivor.
- ROBUST_RESEARCH_POSITIVE: particularly stable/plateau-like family, even if raw return is lower.
- HIGH_SAMPLE_POSITIVE: broad high-N positive family useful for future refinement.
- DISCOVERY_SURVIVOR: passes all preregistered survivor gates.
- CONFIRMATION_FAILED / VALIDATED as already defined.

A candidate can carry multiple tags while having one lifecycle status.

## Diversity policy

The machine must deliberately preserve search diversity. Allocate search budget across:

- M1 and M5,
- CNY and Si,
- LONG, SHORT and BOTH,
- reversal, breakout, continuation and mean-reversion mechanisms,
- simple and conditional families.

Do not spend all cycles refining the current top family. Use an exploration/exploitation schedule, e.g. roughly 60% exploration of under-tested families and 40% refinement of promising clusters until enough survivor-quality families exist.

## Causal integrity

Formal discovery must use completed-bar information only and next-causal execution as defined in the current search policy. Historical same-close CMD execution can be reproduced only as calibration, not formal evidence.

## Data fences

Formal research remains restricted to Moscow 2026-01-05 through 2026-05-15. Jan-Feb is selection/tuning; Mar-May15 is research-forward. 2026-05-16 through 2026-07-01 remains RETIRED. TRUE OOS 2025 remains SEALED.

## Continuous local machine behavior

When the local daemon is running:

1. select the next family according to exploration/exploitation policy;
2. preregister the finite search space;
3. run CNY M1, CNY M5, Si M1, Si M5 as applicable;
4. compute all ranking views and Pareto front;
5. identify robust semantic clusters / plateaus;
6. save every meaningful positive family in the registry;
7. research-forward test frozen candidates;
8. update lifecycle status;
9. immediately start the next search family if fewer than the target number of independent survivors exists.

The machine does not wait one hour between cycles. Hourly automation is only a watchdog / reporting layer.