# Cycle32 Result — Semantic Rejection Sample Expansion

## Research status

**NO_SEMANTIC_SAMPLE_EXPANSION_RESEARCH_SURVIVOR**

Cycle32 was preregistered before execution. It used the same fenced research data policy as the Cycle1-31 replay: Jan-Feb selection, Mar-May15 research-forward, no May16-Jul1 retired confirmation data, and no 2025 TRUE OOS. Mar-May15 remains research-only because it has already been repeatedly inspected across prior cycles.

## CNYRUBF

- Generated candidate evaluations: 2,010
- Deduped discovery candidates: 1,632
- Discovery passes: 27
- Shortlisted: 10
- Strict survivors: 0

Best pooled sample-expansion candidate:

`CNYRUBF|SHORT|REJECTION|ROUND_OR_ROLL60|LEVEL|SL8|B1|TTL15|TP6R|eff_60m:HIGH25`

Research-forward:

- GROSS: N32, PF 2.187, expectancy 0.840R
- BASE: N31, PF 1.983, expectancy 0.774R, 20 days, +163.61 bps
- STRESS: N29, PF 1.609, expectancy 0.539R, 19 days, +107.38 bps
- bootstrap P10 BASE mean R: +0.175
- all Mar / Apr / May1-15 BASE blocks positive: yes
- all corresponding STRESS blocks positive: yes
- STRESS/BASE trade ratio: 0.935

Why it did not survive:

1. BASE PF 1.983 is below the preregistered >=2.0 threshold.
2. Cluster robustness failed: ROUND was independently positive under STRESS, but ROLL60 alone was essentially flat/negative in R terms.

Component decomposition with the same execution:

- ROUND: STRESS N15, PF 2.059, expectancy +0.967R.
- ROLL60: STRESS N15, PF 1.041, expectancy -0.008R.

Parameter-neighbor behavior was encouraging but not sufficient to override the preregistered gates: three adjacent one-axis neighbors retained positive STRESS expectancy.

Interpretation: pooling ROUND with ROLL60 successfully expanded the sample from the ~16-19 trade Cycle29 cluster to ~30 trades without destroying stress economics, but the extra ROLL60 events did not establish an independent robust edge. The pooled result is therefore a strong near-miss, not a survivor.

## USDRUBF control

- Generated candidate evaluations: 1,668
- Discovery passes: 5
- Shortlisted: 5
- Strict survivors: 0

The best shortlisted control remained negative on research-forward data (BASE PF < 0.7, negative expectancy; STRESS also negative). This does not support cross-instrument replication of the Cycle32 semantic pool.

## Decision

Cycle32 hypothesis is **not accepted as a research survivor**.

Knowledge carried forward:

- ROUND remains the dominant positive component.
- ROLL60 can raise sample size but does not independently carry the edge under STRESS.
- Do not lower the BASE PF gate to rescue the pooled candidate.
- The next cycle should rotate away from anchor pooling and test a genuinely different causal axis.
