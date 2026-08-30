# Cycle 31 — Probe → Reclaim → Second-Touch Passive Entry

Preregistered after the complete Cycle 29 result showed a split failure mode: several CNY passive structural candidates retained large executable BASE/STRESS edge but were too sparse for the unchanged survivor gate, while several Si candidates had adequate counts but lost temporal consistency or STRESS margin. Cycle 31 tests a new execution hypothesis rather than selecting any winning Cycle-29 seed.

## Research status and fences

- Research-only autonomous discovery.
- Read only Moscow 2026-01-05 through 2026-05-15.
- 2026-05-16 through 2026-07-01 is retired and MUST NOT be read for selection, tuning, re-checking, ranking, or confirmation.
- TRUE OOS 2025 remains SEALED.
- Jan-Feb is the only selection/tuning period.
- Mar-May15 is retrospective research-forward only and cannot validate a system.
- Any survivor must wait for genuinely new untouched data.

## Hypothesis

Cycle 29 entered on the first passive structural pullback. A first touch may contain adverse selection. Cycle 31 therefore requires a fully causal three-stage sequence before entry:

1. **Probe:** after a completed M5 structural setup, price touches the frozen structure-aligned passive limit.
2. **Reclaim:** on a later completed M1 bar, price closes at least one tick back on the setup-safe side of that same frozen limit.
3. **Second touch:** only on a later M1 bar after the reclaim may the order fill at the original frozen limit.

The limit, protective anchor, fixed stop, target, TTL, context and setup identity are frozen before the initial probe. Nothing is moved after observing the probe or reclaim.

This is not seed shopping: every legal Cycle-29 structural/event/context/stop/target combination is searched under the same deterministic Jan-Feb process.

## Candidate space

Exactly the Cycle-29 systematic space is retained:

- instruments: CNYRUBF, USDRUBF;
- directions: LONG, SHORT;
- structures: PREV_DAY, ROLL30, ROLL60, M5_FRACTAL, EQUAL_CLUSTER, ROUND, OPEN30;
- events: REJECTION, SWEEP_RECLAIM, BREAK_RETEST;
- anchor modes: LEVEL, EVENT_EXTREME;
- CNY fixed stops: 6, 8, 10 points only;
- Si fixed stops: 6, 9, 12, 15 points only;
- anchor buffers: 1, 2, 3 ticks;
- TTL: 15 or 30 minutes;
- targets: 3R, 4R, 5R, 6R;
- optional context: NONE or exactly one broad LOW25/HIGH25 causal state or fixed clock bucket.

Quantile cutpoints are fitted Jan-Feb only and frozen.

## Structure-aligned limit and stop

Same immutable Cycle-29 geometry:

- LONG limit = anchor + (stop_points - buffer_ticks) * tick;
- SHORT limit = anchor - (stop_points - buffer_ticks) * tick.

After fill, stop is exactly `stop_points` from entry and therefore remains `buffer_ticks` beyond the frozen invalidation anchor. Stops are never widened.

## Probe / reclaim / second-touch execution

Order observation begins at the first M1 minute after the completed M5 setup and ends at the original TTL or 17:00 Moscow, whichever comes first.

### Probe

A probe is the first M1 bar that touches the frozen limit. Probe detection itself is identical across GROSS/BASE/STRESS and gives no fill credit.

### Reclaim

On a strictly later completed M1 bar:

- LONG requires close >= limit + 1 tick;
- SHORT requires close <= limit - 1 tick.

The reclaim bar cannot itself be the fill bar.

### Second-touch executable fill

On a strictly later M1 bar after reclaim:

- GROSS: touch of original limit qualifies;
- BASE: trade through original limit by >=1 tick;
- STRESS: trade through original limit by >=2 ticks.

Fill price is always the frozen limit; no favorable improvement is credited. If no legal second touch occurs before TTL, there is no trade.

Fill-bar target credit remains forbidden. Fill-bar stop is charged conservatively. After the fill bar, STOP_FIRST, adverse stop gaps, conservative target gaps, same-day force close and Cycle-29 exit friction rules are unchanged.

## Selection and gates

**No gates are changed after viewing Cycle 29.** Cycle 31 reuses the complete Cycle-29 Jan-Feb discovery gate, ranking rule, shortlist cap, and strict Mar-May15 survivor gate unchanged.

Jan-Feb discovery must still satisfy, among other frozen requirements:

- January and February each profitable under BASE with STRESS expectancy positive when trades exist;
- combined BASE >=14 trades / >=9 dates;
- combined STRESS >=10 trades and STRESS/BASE fill ratio >=0.50;
- BASE PF >=2.00;
- STRESS PF >=1.40;
- BASE E[R] >= +0.30;
- STRESS E[R] >= +0.10;
- largest BASE winner share <=0.35.

Strict Mar-May15 research survivor still requires ALL:

- BASE PF >=2.00;
- STRESS PF >=1.50;
- BASE E[R] >=+0.30;
- STRESS E[R] >=+0.10;
- day-bootstrap P10 BASE E[R] >0;
- BASE >=30 trades and >=15 dates;
- STRESS >=20 trades;
- STRESS/BASE trade ratio >=0.50;
- March, April, May1-15 all positive in BASE;
- March, April, May1-15 all positive in STRESS;
- largest BASE winner share <=0.25.

No fallback, no post-result gate relaxation, no manually chosen Cycle-29 seed and no use of the retired confirmation window.