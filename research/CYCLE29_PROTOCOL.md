# Cycle 29 — Structure-Aligned Passive Entry with Fixed Short Stop

Preregistered after Cycles 27-28 showed that market entry after structural confirmation often consumes too much of a short fixed stop. Cycle 29 changes the entry geometry, not the fixed-stop requirement.

## Fences

- Research-only autonomous discovery.
- Read only Moscow 2026-01-05 through 2026-05-15.
- 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Jan-Feb discovery only; Mar-May15 retrospective research forward only.

## Core geometry

For every completed structural setup freeze a protective anchor `A` and choose a legal fixed stop size `S` in ticks and a stop-behind-anchor buffer `B` in ticks.

The passive entry price is derived BEFORE the order is placed:

- LONG: `limit = A + (S - B) * tick`
- SHORT: `limit = A - (S - B) * tick`

After fill:

- LONG stop = `limit - S*tick = A - B*tick`
- SHORT stop = `limit + S*tick = A + B*tick`

Thus the stop size from fill is fixed, while the stop is guaranteed to sit exactly `B` ticks beyond the frozen invalidation structure. The stop is never widened.

Legal buffers: **1, 2, 3 ticks**.

## Fixed stop grids

One point = one minimum exchange-price increment in repository data.

- CNYRUBF: **6, 8, 10 points only**, never >10.
- USDRUBF/Si: **6, 9, 12, 15 points only**.

## Structural setups

Reuse the causal Cycle-27 M5 structural-event definitions, frozen at the completed M5 setup bar:

Structures:
- PREV_DAY
- ROLL30
- ROLL60
- M5_FRACTAL
- EQUAL_CLUSTER
- ROUND
- OPEN30

Events:
- REJECTION
- SWEEP_RECLAIM
- BREAK_RETEST

Protective anchor modes:
- LEVEL
- EVENT_EXTREME

The event, structure and anchor are frozen before the passive order is placed.

## Passive-order requirement

The derived limit must be passive at setup completion:

- LONG: completed setup close must be above the buy-limit price;
- SHORT: completed setup close must be below the sell-limit price.

Order lifetime candidates are **15 or 30 minutes**, never beyond 17:00 Moscow. One live order/position at a time per candidate. If an order expires unfilled, the candidate may re-arm on a later independent setup.

## Conservative fill models

Fill price is always the frozen limit; no favorable price improvement is credited.

- GROSS: touch of limit qualifies.
- BASE: market must trade through the limit by >=1 tick.
- STRESS: market must trade through the limit by >=2 ticks.

If an M1 bar opens through the limit, the recorded fill remains the limit, not the better opening price.

On the fill bar, target credit is forbidden because intrabar ordering before/after the fill is unknown. If the stop is also touched on the fill bar, stop is assumed to occur after fill and is charged conservatively. A gap through the stop on the fill bar exits at the M1 open after the limit fill is deemed executable.

After the fill bar:

- STOP_FIRST if stop and target are both touched in one M1 bar;
- adverse stop gaps exit at M1 open;
- favorable target gaps exit conservatively at target.

Exit friction:

- GROSS: 0 adverse exit ticks;
- BASE: 1 adverse exit tick;
- STRESS: 2 adverse exit ticks.

Entry uncertainty is represented by the 0/1/2-tick fill-through requirement, so an additional market-entry slippage charge is not added. Commission is excluded and reported.

## Reward grid

Fixed target from actual limit fill:

- 3R
- 4R
- 5R
- 6R

No target <3R. Maximum holding time after fill:

- 3R: 120 minutes
- 4R: 180 minutes
- 5R: 240 minutes
- 6R: until 17:00

## Optional context

Candidate may use no context or exactly one frozen M5 causal state.

Numeric states searched in Cycle 29 are only the broader LOW25/HIGH25 states from the Cycle-27 whitelist; fixed clock buckets are also allowed. Quantile cutpoints are fit Jan-Feb only and frozen unchanged for forward use. LOW10/HIGH10 are intentionally excluded to reduce sparsity.

## Candidate identity

`instrument | direction | event | structure | anchor_mode | stop_points | anchor_buffer | order_ttl | target_R | optional_context`

No ML, adaptive beam search, March-May feedback, target-derived entry feature, post-hoc anchor substitution or stop widening.

## Jan-Feb discovery gate

Same complete candidate must satisfy January and February separately under BASE and STRESS fill models.

Per month using BASE fills:
- >=5 trades;
- >=4 dates;
- BASE PF >=1.20;
- BASE E[R] >0;
- STRESS E[R] >0 whenever STRESS has trades.

Combined Jan5-Feb28:
- BASE >=14 trades and >=9 dates;
- STRESS >=10 trades;
- STRESS/BASE trade-count ratio >=0.50;
- BASE PF >=2.00;
- STRESS PF >=1.40;
- BASE E[R] >=+0.30;
- STRESS E[R] >=+0.10;
- BASE/STRESS bps expectancy >0;
- largest BASE winner share <=0.35.

No pass means no candidate.

## Frozen shortlist

Rank discovery-passing candidates by:
1. minimum(January STRESS E[R], February STRESS E[R]);
2. combined STRESS PF;
3. combined BASE PF;
4. STRESS E[R];
5. BASE dates;
6. canonical candidate id.

Freeze at most 60 candidates/instrument, max 3 per identical `(direction,event,structure,anchor_mode,context)` semantic bucket.

## Mar-May strict research gate

Apply frozen candidate unchanged through 2026-05-15.

`PASSIVE_FIXED_STOP_SURVIVOR` requires ALL:

- BASE PF >=2.00;
- STRESS PF >=1.50;
- BASE E[R] >=+0.30;
- STRESS E[R] >=+0.10;
- day-bootstrap P10 BASE E[R] >0, seed 20260401;
- BASE >=30 trades and >=15 dates;
- STRESS >=20 trades;
- STRESS/BASE trade-count ratio >=0.50;
- March, April and May1-15 total bps all >0 in BASE;
- March, April and May1-15 total bps all >0 in STRESS;
- largest BASE winner share <=0.25.

Because fill uncertainty changes which orders execute, GROSS/BASE/STRESS total-bps monotonicity is reported but is not a valid gate in Cycle 29.

Any survivor remains research-only and requires genuinely new untouched confirmation data. Retired May16-Jul1 and 2025 remain sealed.
