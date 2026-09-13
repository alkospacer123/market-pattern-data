# Autonomous Search — Cycle1–31 Replay Audit

## Executive conclusion

The Intel replay is usable as a research audit. The fenced mirror exposed no 2025 TRUE OOS and no data on/after 2026-05-16 to the replay engines.

There are **30 implemented research cycles** plus **Cycle15, which is preregistered but not implemented**.

- **Strict research-forward survivors:** 1 historical survivor (Cycle3 / A3-USDRUBF-M5-049).
- **Current validated/live candidates:** 0. A3 subsequently failed its separate untouched confirmation and is therefore not validated.
- **Strongest current research-positive cluster:** Cycle29 CNYRUBF SHORT rejection around ROUND levels under high 60-minute directional efficiency, using passive entry and high-R targets. It failed the strict survivor gate primarily because of sample size, not because BASE/STRESS economics collapsed.
- **Hardest negative lesson:** broad ML/analog/lead-lag/microstructure families generally show either no gross edge or a small gross edge that disappears under one- and two-tick execution friction.
- **Dead execution branch:** Cycle30 probe→reclaim entry produced zero discovery passes on both instruments.
- **Cycle31:** second-touch logic restored many discovery passes but still produced zero strict survivors.

## Replay integrity

The replay ran from 2026-09-12 21:13:15+03:00 to 2026-09-13 20:57:42+03:00, about 23h44m.

The controller used a fenced copy of the eight 2026 CNY/Si M1/M5 files with an exclusive cutoff of 2026-05-16. Retired 2026-05-16..2026-07-01 rows were excluded, and 2025 was not exposed.

Cycle26 and Cycle31 had infrastructure failures, not research-semantic failures:
- Cycle26 completed its calculations, then failed serializing Python `date`; it was independently reconstructed from the archived fenced data and audit source.
- Cycle31 completed both instrument searches and wrote manifests/shortlists/survivors, then failed writing a Unicode arrow to `report.md` under Windows cp1251.

Both source defects have been fixed without changing research logic.

## Cycle-by-cycle audit

| Cycle | Research outcome | Key evidence | Decision |
|---:|---|---|---|
| 1 | NO_SURVIVOR_YET | 80 OOF candidates; top research-positive but N≈29 | KEEP AS PRECURSOR |
| 2 | NO_SURVIVOR_YET | 140 frozen candidates; strong sparse M5 shorts, insufficient sample/folds/concentration | KEEP AS PRECURSOR |
| 3 | SURVIVOR_FOUND | A3-USDRUBF-M5-049: forward BASE PF 2.623, STRESS PF 1.797, N32; later untouched confirmation failed | CONFIRMATION_FAILED |
| 4 | NO_DISCOVERY_SURVIVOR_YET | CNY M1/M5 and USD M1/M5 correctly replayed; no survivor | REJECT FAMILY AS IMPLEMENTED |
| 5 | RESEARCH_GATE_FAIL | BASE PF 0.196; STRESS PF 0.158; N25 | STRONG REJECT |
| 6 | RESEARCH_GATE_FAIL | BASE PF 0.695; STRESS PF 0.457; N1080 | STRONG REJECT |
| 7 | NO_RESEARCH_SURVIVOR | Standalone equal-level family failed | REJECT AS STANDALONE |
| 8 | NO_RESEARCH_SURVIVOR | Best CNY near breakeven BASE, negative after stress | REJECT SIMPLE RETEST |
| 9 | NO_RESEARCH_SURVIVOR | Best PF below 1 after costs/stress | REJECT SIMPLE BREAKOUT |
| 10 | NO_TRAIN_ELIGIBLE_MODEL | No train-eligible relative-value model | REJECT CURRENT FORM |
| 11 | NO_RESEARCH_SURVIVOR | Gross PF 1.150; BASE 0.853; STRESS 0.639; N687 | GROSS EDGE KILLED BY FRICTION |
| 12 | NO_RESEARCH_SURVIVOR | Gross PF 0.910; BASE 0.682; STRESS 0.518; N464 | STRONG REJECT |
| 13 | NO_RESEARCH_SURVIVOR | Gross PF 1.137; BASE 0.838; STRESS 0.624; N701 | GROSS EDGE KILLED BY FRICTION |
| 14 | NO_RESEARCH_SURVIVOR | Gross PF 0.926; BASE 0.688; STRESS 0.515; N646 | STRONG REJECT |
| 15 | PREREGISTERED_NOT_IMPLEMENTED | Protocol exists; executable engine absent | DO NOT FABRICATE RESULT |
| 16 | NO_RESEARCH_SURVIVOR | BASE PF 0.332; STRESS PF 0.260; N30 | STRONG REJECT |
| 17 | NO_RESEARCH_SURVIVOR | Combined negative after costs; CNY component BASE PF 1.312, STRESS 1.043, N41 | WEAK CNY SIGNAL |
| 18 | NO_RESEARCH_SURVIVOR | Gross PF 1.510; BASE 0.996; STRESS 0.694; N70 | FRICTION KILLS EDGE |
| 19 | NO_INSTRUMENT_RESEARCH_SURVIVOR | CNY BASE PF 1.256, STRESS 0.920, N93; USD worse | CNY > USD, NOT ROBUST |
| 20 | NO_INSTRUMENT_RESEARCH_SURVIVOR | CNY BASE PF 0.945, STRESS 0.693, N99; USD 0 trades | REJECT |
| 21 | NO_HIGH_R_RULE_SURVIVOR | CNY sparse SHORT R4 near-miss: BASE PF 3.701, STRESS 2.901, N6 | HIGH-R SPARSE CLUE |
| 22 | NO_STRESS_HIGH_R_RESEARCH_SURVIVOR | BASE PF 0.751; STRESS 0.600; N191 | STRONG REJECT |
| 23 | NO_FAMILY_HIGH_R_RESEARCH_SURVIVOR | CNY short family BASE PF 1.743, STRESS 1.400, N31; bootstrap P10 negative | NEAR-MISS / CNY SHORT CLUSTER |
| 24 | 0 survivors | CNY 1 discovery pass; USD 4; forward negative | REJECT |
| 25 | 0 survivors | CNY 2 discovery passes; USD 0; forward weak/negative | REJECT |
| 26 | NO_SPARSE_HIGH_R_ENSEMBLE_RESEARCH_SURVIVOR | Recovered: CNY forward BASE PF 0.691/STRESS 0.532 N157; USD 0.679/0.503 N149 | STRONG REJECT; SERIALIZATION FIXED |
| 27 | 0 survivors | USD SHORT rejection near-miss: BASE PF 2.130, STRESS 1.771, N21, bootstrap >0; one stress block failed | PROMISING SPARSE CLUSTER |
| 28 | 0 survivors | CNY SHORT reject-follow M1 fractal: BASE PF 1.523, STRESS 1.166, N44; bootstrap slightly <0 | WEAK BUT TEMPORALLY STABLE CLUSTER |
| 29 | 0 survivors | Strongest near-miss: CNY SHORT ROUND rejection eff60 HIGH25, BASE PF 3.317, STRESS 2.977, N16, bootstrap P10 +0.450, all blocks positive | TOP RESEARCH-POSITIVE; FAILS SAMPLE GATE |
| 30 | 0 survivors | 0 discovery passes on both instruments | HARD REJECT ENTRY GEOMETRY |
| 31 | 0 survivors | CNY 195 discovery passes/60 shortlist; USD 182/60; 0 survivors. Reporting-only UTF-8 failure fixed | NO SURVIVOR; SOME SPARSE SIGNAL |

## The one historical strict research survivor: A3

**A3-USDRUBF-M5-049**

State:
- `dist_high_120m_atr = HIGH25`
- `dist_low_15m_atr = HIGH10`
- SHORT
- stop 1.25 ATR
- target 1.5R
- max hold 120 min

Jan-Feb discovery:
- BASE: 23 trades, PF 2.560, +5.88 bps/trade, +135.25 bps total.
- STRESS: 23 trades, PF 1.727, +3.31 bps/trade.

Mar-May15 research-forward:
- BASE: 32 trades, PF 2.623, +6.45 bps/trade, +206.44 bps total, 25 days, 3 positive months/folds.
- STRESS: 32 trades, PF 1.797, +3.88 bps/trade, +124.03 bps total, 25 days, 3 positive months/folds.
- Four one-axis parameter neighbors were stable.
- CNY replication was directionally consistent but not a strict replica.

This is strong research evidence, but **not a live candidate now**: the separate untouched confirmation later failed, so the current lifecycle state is `confirmation_failed`.

## Strongest late-stage research cluster: Cycle29 CNY

Semantic cluster:
- CNYRUBF
- SHORT
- `REJECTION`
- ROUND level
- high `eff_60m`
- passive entry
- 5R–6R target

Best observed member:
`CNYRUBF|SHORT|REJECTION|ROUND|EVENT_EXTREME|SL10|B2|TTL15|TP6R|eff_60m:HIGH25`

Research-forward:
- BASE PF **3.317**
- BASE expectancy **1.488R**
- BASE N **16**
- STRESS PF **2.977**
- STRESS expectancy **1.388R**
- STRESS N **16**
- bootstrap P10 BASE mean R **+0.450**
- all Mar / Apr / May1-15 BASE blocks positive
- all STRESS blocks positive

It did **not** pass Cycle29's survivor gate because the sample is too small. This must be treated as a high-return research-positive / near-miss, not validation.

Two neighboring members of the same semantic cluster also remained positive under stress:
- ROUND LEVEL, SL10/B3/TTL30/6R: BASE PF 2.129, STRESS PF 2.074, N≈19/18, bootstrap P10 +0.123.
- Same geometry with 5R: BASE PF 2.077, STRESS PF 2.022, bootstrap P10 +0.084.

The fact that several semantic neighbors survive stress is more informative than one isolated high-PF row.

## Cross-cycle knowledge

1. **CNY became the stronger instrument in the late high-R structural families.** Cycles17, 19, 21, 23, 28 and especially 29 repeatedly favor CNY short-side structural/rejection states.
2. **SHORT structural rejection/continuation is more persistent than raw breakout/retest.** Equal-level standalone breakout/retest failed, while contextual rejection families repeatedly produced research-positive near-misses.
3. **Round/rolling structural anchors appear more useful than equal levels alone.**
4. **Execution costs are decisive.** Cycle11 and Cycle13 had weak positive gross PF (~1.15 and ~1.14) but turned negative at BASE and worse at STRESS.
5. **Broad prediction is not the answer here.** Pooled ridge had 1080 trades and was robustly negative; historical analog and M1 microstructure were also negative.
6. **High-R works only in sparse, strongly conditioned states.** The best 4R–6R candidates are impressive economically but repeatedly fail sample/temporal robustness gates.
7. **Probe→reclaim is a dead branch as implemented.** Cycle30 had zero discovery passes. Second-touch reclaim in Cycle31 is better but still not robust.
8. **Do not lower the sample gate to “save” Cycle29.** The correct next experiment is to expand the semantic event population while keeping strict gates.

## Recommended next research move

Cycle32 should test **semantic sample expansion**, not another narrow parameter optimization.

The target hypothesis is:

> A bearish structural rejection/pullback state can preserve Cycle29-like stress-adjusted expectancy while increasing sample size by pooling semantically adjacent level anchors and contexts under frozen execution families.

Key constraint: March-May15 is already research-inspected and remains research-only. Any Cycle32 pass is still a research survivor awaiting genuinely new untouched confirmation data. Retired May16-Jul1 and TRUE OOS 2025 remain closed.
