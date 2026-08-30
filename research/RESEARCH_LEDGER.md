# Autonomous Market Pattern Research Ledger

Persistent research state. Do not rewrite failed cycles into successes. New cycles append new evidence.

## Data fences

- Main reusable research/discovery data: Moscow 2026-01-05 through 2026-05-15.
- 2026-05-16 through 2026-07-01 was used once as Internal Confirmation for the frozen Cycle-3 survivor and is RETIRED for all later candidate selection/confirmation.
- 2025 TRUE OOS remains SEALED and must not be opened unless a future candidate passes a genuinely untouched confirmation stage under the research protocol.
- No fresh Q3/after-2026-07-01 dataset is currently available in this repository.

## Completed evidence through Cycle 17

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
| 10 | CNY/Si relative value | GROSS PF up to high values; representative ~2.64 -> BASE ~0.12 after two-leg friction | economically non-tradeable |
| 11 | nonlinear executable-PnL ML | GROSS 1.150 -> BASE 0.853 -> STRESS 0.639 | failed |
| 12 | historical analog mining | GROSS 0.910 -> BASE 0.682 -> STRESS 0.518 | failed |
| 13 | cross-instrument lead/lag ML | GROSS 1.137 -> BASE 0.838 -> STRESS 0.624 | weak predictability, insufficient magnitude |
| 14 | M1 microstructure ML | GROSS 0.926 -> BASE 0.688 -> STRESS 0.515 | failed |
| 17 | autonomous high-R 3R–5R discovery | combined GROSS PF 1.293, BASE 0.964, STRESS 0.738, N=80 | no survivor |

### Cycle 17 detail

- Combined BASE mean realized R: -0.0033R/trade; STRESS -0.2577R.
- CNYRUBF: BASE PF 1.312, BASE mean +0.287R, N=41; STRESS PF 1.043, mean +0.066R.
- USDRUBF: BASE PF 0.693, BASE mean -0.308R, N=39; STRESS PF 0.509.
- By executed target bucket: 3R BASE PF ~0.61; 4R ~0.76; 5R ~1.62.
- Several *causal validation* tails genuinely showed high values (PF 2–6 and +0.4R to +1.7R/trade), but week-ahead transfer was unstable.
- Example: Apr20-Apr27 CNY forward BASE PF 3.60 on 7 trades while Si in the same week was BASE PF 0.56.

## Current research conclusion

1. High apparent PF is possible, especially in rare states, but the only formal early discovery survivor failed untouched confirmation badly.
2. Frequent weak prediction is not enough: typical gross edges of roughly 0.5–1.8 bps/trade are consumed by realistic one-tick-per-side execution.
3. The search should therefore prioritize **rare, large-payoff states**, not dense next-bar prediction.
4. RR itself is not mathematical expectancy. New candidates must combine payoff geometry >=3R with positive realized BASE/STRESS expectancy in R and bps.
5. The machine must be allowed to stay flat rather than select the least-bad model.
6. Short stops must remain execution-realistic; no sub-tick/sub-noise stop illusion.
7. Instrument pooling is now suspect because Cycle 17 produced materially different forward behavior in CNY and Si.

## Active / preregistered next work

- Cycle 18 — Ultra-Short Stop Barrier Mining: stop 0.25–0.50 ATR with 5-tick floor, targets 3R–6R, dual regression + target-before-stop classifier; currently running.
- Cycle 19 — Instrument-Specific High-R Discovery: same high-R class but CNY and Si label/model qualification isolated; preregistered and implementation prepared.
- Cycle 20 — Structural Ultra-Short Stop / 4R–6R: stop beyond completed M1 local swing, minimum 5 ticks, maximum 0.60 ATR; preregistered.

## Current objective

Find a causal executable pattern/system with:

- short, auditable stop;
- target >=3R (prefer farther targets if evidence supports them);
- BASE PF >=2.0;
- STRESS PF >=1.5;
- positive and substantial mean realized R after friction;
- enough independent trades/dates/months;
- low winner concentration;
- robustness under day-block bootstrap and future untouched confirmation.

Until those gates are met, status remains research-only.
