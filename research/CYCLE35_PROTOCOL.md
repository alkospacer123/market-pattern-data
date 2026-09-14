# Cycle35 — Opening-Range Structural Behavior

## Objective

Rotate away from the repeatedly mined ROUND-rejection motif and test an independent, session-defined structure: the first 30 minutes of the trading session.

Cycle35 asks whether the completed opening range creates executable support/resistance that supports either continuation after a break/retest or failure/rejection at the range boundary.

## Prior evidence

- Cycle29 produced a strong but sparse CNY SHORT ROUND-rejection high-R cluster.
- Cycle32 showed that pooling weaker rolling anchors raises sample but dilutes the edge.
- Cycle33 completed-H1 conditioning produced zero discovery passes.
- Cycle34 lower-R/shorter-hold exits over the frozen ROUND motif also produced zero discovery passes.
- Therefore Cycle35 must not add another ROUND filter or another ROUND exit variant.

## Preregistered hypothesis

A session opening range is a distinct causal structural anchor. The first 30 minutes may create boundaries at which later M5 behavior exhibits either:

1. continuation after a confirmed break and retest; or
2. rejection / sweep-and-reclaim failure at the boundary.

The experiment is intended to discover whether either semantic branch has robust executable edge. It is not allowed to select the semantic branch from Mar-May performance.

## Causal opening-range construction

Use M5 bars from 09:00 through 09:25 inclusive to construct:

- `OPEN30_HIGH` = maximum high of those completed bars;
- `OPEN30_LOW` = minimum low of those completed bars.

The opening range becomes available only from 09:30 onward. No setup before 09:30 may use it.

The opening range is frozen for the rest of the session and never uses future bars.

## Frozen structural family

Timeframe and execution:
- setup timeframe: M5;
- execution timeframe: next causal M1 open after the completed M5 setup;
- one active position per candidate;
- forced session exit no later than 17:00;
- GROSS / BASE / STRESS friction treatment inherited from Cycle27.

Structure:
- `OPEN30` only;
- no ROUND, ROLL30, ROLL60, EQUAL_CLUSTER, fractal or prior-day level pooling.

Preregistered event semantics:
- `REJECTION`;
- `SWEEP_RECLAIM`;
- `BREAK_RETEST`.

Directions:
- LONG and SHORT are both tested independently.

Anchor modes:
- `LEVEL`;
- `EVENT_EXTREME`.

No contextual feature filters are allowed in Cycle35. In particular there is no `eff_60m`, H1 state, clock-bucket optimization, volatility quantile, or post-hoc regime selection. The session-defined structure itself is the hypothesis.

## Finite execution grid

CNYRUBF fixed stops:
- 6 points;
- 8 points;
- 10 points.

USDRUBF fixed stops:
- 9 points;
- 12 points;
- 15 points.

Targets / maximum holds:
- 3R / 120 minutes;
- 4R / 180 minutes;
- 5R / 240 minutes.

No other target, stop or hold value may be introduced after results are seen.

## Selection and evaluation windows

Discovery/selection:
- 2026-01-05 through 2026-02-28.

Research-forward:
- 2026-03-01 through 2026-05-15.

Never expose:
- retired 2026-05-16 through 2026-07-01 internal-confirmation data;
- TRUE OOS 2025.

Mar-May15 is already repeatedly inspected and remains research-only. A Cycle35 pass is not validation.

## Discovery gate

Use the unchanged causal Cycle27/Cycle24 discovery gate. No threshold may be relaxed for opening-range candidates.

## Frozen ranking and shortlist

Discovery-pass candidates are ranked deterministically by:

1. larger minimum of January and February STRESS expectancy R;
2. higher combined discovery STRESS PF;
3. higher combined discovery BASE PF;
4. higher combined discovery STRESS expectancy R;
5. more discovery STRESS trading days;
6. lexicographic candidate ID.

Shortlist cap: 30 candidates per instrument.

Diversity cap: at most 3 shortlisted candidates per `(direction, event, anchor_mode)` bucket.

No Mar-May values may influence ranking or shortlist selection.

## Forward survivor gate

Use the unchanged Cycle27 strict research-forward gate:
- BASE PF >= 2.0;
- STRESS PF >= 1.5;
- BASE expectancy >= 0.30R;
- STRESS expectancy >= 0.10R;
- bootstrap P10 BASE mean R > 0;
- BASE N >= 30;
- BASE unique days >= 15;
- all Mar / Apr / May1-15 BASE blocks positive;
- all corresponding STRESS blocks positive;
- largest BASE winner share <= 0.25;
- GROSS total bps >= BASE total bps >= STRESS total bps.

## Additional Cycle35 robustness gate

A strict Cycle35 survivor must also have at least one adjacent one-axis execution neighbor with:
- STRESS N >= 10;
- positive STRESS expectancy R.

Adjacent means exactly one of:
- neighboring preregistered stop value at the same target;
- neighboring preregistered target/hold pair at the same stop.

The event semantic, direction and anchor mode remain fixed for the neighbor test.

## Decision rule

PASS:
A candidate passes the unchanged strict forward gate and the execution-neighbor robustness gate.

NEAR-MISS:
Opening-range economics are positive and repeat through time, but one preregistered gate is missed.

FAIL:
No discovery candidate survives, or forward economics / friction / temporal robustness fail.

## Prohibitions

- no opening-range duration other than 30 minutes;
- no context filters after seeing results;
- no new events after seeing results;
- no parameter threshold relaxation;
- no optimization on Mar-May15;
- no May16-Jul1 access;
- no 2025 access;
- no relabeling of research-forward evidence as validation.