# Autonomous Market Pattern Research Ledger

Persistent research state. Do not rewrite failed cycles into successes. New cycles append new evidence.

## Data fences

- Main reusable research/discovery data: Moscow 2026-01-05 through 2026-05-15.
- 2026-05-16 through 2026-07-01 was used once as Internal Confirmation for the frozen Cycle-3 survivor and is RETIRED for all later candidate selection/confirmation.
- 2025 TRUE OOS remains SEALED and must not be opened unless a future candidate passes a genuinely untouched confirmation stage under the research protocol.
- No fresh Q3/after-2026-07-01 dataset is currently available in this repository.

## Completed evidence through Cycle 18

| Cycle | Research class | Key result | Status |
|---|---|---|---|
| 1 | autonomous sparse state/rule search | best OOF BASE PF ~2.63, STRESS ~1.60, N=29; adaptive deployment BASE PF ~0.25 | failed robustness/min-trades |
| 2 | frozen January candidate -> later WF | best BASE PF ~2.42, STRESS ~1.83, N=17 | failed sample/stability |
| 3 | stable-state high-PF discovery | USDRUBF M5 survivor BASE PF 2.623, STRESS 1.797, N=32 | discovery pass |
| 3 IC | untouched May16-Jul1 confirmation | survivor BASE PF 0.487, STRESS 0.324 | failed confirmation; interval retired |
| 4 | causal event families | example train BASE PF ~3.02 -> frozen forward ~0.85 | failed transfer |
| 5 | weekly adaptive event selector | BASE PF ~0.196, STRESS ~0.158 | failed |
| 6 | pooled causal Ridge return forecast | BASE PF ~0.695, STRESS ~0.457, N~1080 | failed |
| 7 | Equal High/Low round-level reversal | CNY GROSS PF ~1.418 -> BASE ~0.999 | gross edge consumed by friction |
| 8 | passive retest of equal level | best CNY BASE ~0.996, STRESS ~0.643 | failed |
| 9 | equal-level liquidity breakout | CNY BASE ~0.735; Si ~0.620 | failed |
| 10 | CNY/Si relative value | representative GROSS PF ~2.64 -> BASE ~0.12 after two-leg friction | economically non-tradeable |
| 11 | nonlinear executable-PnL ML | GROSS 1.150 -> BASE 0.853 -> STRESS 0.639 | failed |
| 12 | historical analog mining | GROSS 0.910 -> BASE 0.682 -> STRESS 0.518 | failed |
| 13 | cross-instrument lead/lag ML | GROSS 1.137 -> BASE 0.838 -> STRESS 0.624 | weak predictability, insufficient magnitude |
| 14 | M1 microstructure ML | GROSS 0.926 -> BASE 0.688 -> STRESS 0.515 | failed |
| 17 | autonomous high-R 3R–5R discovery | GROSS 1.293, BASE 0.964, STRESS 0.738, N=80 | no survivor |
| 18 | ultra-short stop barrier 3R–6R | GROSS 1.510, BASE 0.996, STRESS 0.694, N=70 | no survivor |

### Cycle 17 detail

- Combined BASE mean realized R: -0.0033R/trade; STRESS -0.2577R.
- CNYRUBF: BASE PF 1.312, BASE mean +0.287R, N=41; STRESS PF 1.043, mean +0.066R.
- USDRUBF: BASE PF 0.693, BASE mean -0.308R, N=39; STRESS PF 0.509.
- By executed target bucket: 3R BASE PF ~0.61; 4R ~0.76; 5R ~1.62.
- Several causal validation tails showed PF 2–6 and +0.4R to +1.7R/trade, but week-ahead transfer was unstable.
- Example: Apr20-Apr27 CNY forward BASE PF 3.60 on 7 trades while Si in the same week was BASE PF 0.56.

### Cycle 18 detail

- Stop family 0.25–0.50 ATR with a hard minimum of 5 ticks; targets 3R–6R.
- Dual causal models: executable BASE-R regression plus target-before-stop classifier.
- Combined GROSS PF 1.510, +2.03 bps/trade, N=70.
- Combined BASE PF 0.996, -0.022 bps/trade, mean +0.0856R/trade.
- Combined STRESS PF 0.694, -2.07 bps/trade, mean -0.2827R/trade.
- Whole-day bootstrap P10 BASE mean R = -0.278R.
- Median raw stop = 5 ticks; 5-tick floor active on 64.3% of executed trades. Therefore further nominal stop compression would mostly create an execution-noise illusion rather than meaningful risk reduction.
- CNYRUBF: BASE PF 1.201, mean +0.195R, N=46; STRESS PF 0.854.
- USDRUBF: BASE PF 0.733, mean -0.125R, N=24; STRESS PF 0.486.
- CNY March was strong (BASE PF 3.17, STRESS 2.26) but April deteriorated below 1, so regime transfer remains the central failure mode.
- A representative pre-week validation tail qualified XS8/XS10 SHORT near BASE PF 2.05–2.13 and STRESS 1.53–1.67, yet the next week fell to ~0.60 PF on both instruments.
- Another week had XS10 SHORT validation BASE PF ~2.99/STRESS ~2.28; forward CNY BASE PF ~2.20 while Si was ~0.44. This reinforces the need for instrument-specific qualification rather than pooled label evidence.

## Current research conclusion

1. High apparent PF is possible, especially in rare states, but the only formal early discovery survivor failed untouched confirmation badly.
2. Frequent weak prediction is not enough; realistic one-tick-per-side execution often consumes the gross edge.
3. Search priority is now rare large-payoff states with target >=3R and substantial realized R after friction.
4. RR is payoff geometry, not expectancy: both high target multiple and positive BASE/STRESS mean R are required.
5. The machine must be allowed to remain flat rather than select the least-bad model.
6. Stops must remain execution-realistic. Cycle 18 shows that a 5-tick minimum is already active in most ultra-short-stop trades.
7. Instrument pooling is suspect: CNY and Si repeatedly show materially different high-R forward behavior.
8. Validation-tail PF alone is insufficient. Transfer into the immediately following causal block is the decisive screening problem.

## Active / preregistered work

- Cycle 19 — Instrument-Specific High-R Discovery: Cycle-18 3R–6R barrier class with CNY and Si labels/model qualification fully isolated; running.
- Cycle 20 — Structural Ultra-Short Stop / 4R–6R: stop beyond completed M1 local structure, minimum 5 ticks, maximum 0.60 ATR; instrument-specific dual-model discovery; running.

## Current objective

Find a causal executable pattern/system with:

- short, auditable and market-meaningful stop;
- target >=3R, with 4R–6R preferred when supported by evidence;
- BASE PF >=2.0;
- STRESS PF >=1.5;
- positive and substantial mean realized R after friction;
- enough independent trades/dates/months;
- low winner concentration;
- positive lower-tail day-block bootstrap;
- future untouched confirmation before deployment.

Until those gates are met, status remains research-only.
