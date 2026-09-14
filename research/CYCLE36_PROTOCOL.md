# Cycle36 — USDRUBF Morning ROLL30 Rejection Generalization

## Objective

Test whether the strongest independent non-ROUND research-positive cluster from Cycle27 generalizes into a sufficiently sampled and robust family without adding indicator contexts or relaxing gates.

Cycle36 is a **generalization test**, not a new broad structural search.

## Prior evidence

Cycle27 produced a research-positive USDRUBF near-miss around:

`SHORT REJECTION ROLL30 EVENT_EXTREME clock 09_12 SL12 TP4R`

Research-forward economics were approximately:

- BASE PF 2.130
- STRESS PF 1.771
- BASE N 21
- positive bootstrap lower tail

It failed strict survivor status because sample size was below the required threshold and temporal robustness was incomplete.

This cluster is independent of the repeatedly mined CNY ROUND family.

## Preregistered hypothesis

A short-side rejection of rolling 30-minute resistance during the first part of the session contains a real executable edge that should remain positive when the time window is widened and when adjacent stop/target settings are used.

If the edge exists only in the exact historical `09_12 / SL12 / TP4R` cell, it must be rejected as an isolated research artifact.

## Instruments

Primary hypothesis instrument:
- USDRUBF

Replication/control instrument:
- CNYRUBF

CNY results must not be used to change USDRUBF parameters or gates.

## Frozen structural family

- setup timeframe: M5
- structure: `ROLL30` only
- event: `REJECTION` only
- primary direction: SHORT
- LONG mirror retained as a control branch
- anchor modes: `EVENT_EXTREME`, `LEVEL`
- no ROUND, ROLL60, EQUAL_CLUSTER, OPEN30, fractal or previous-day structures
- no indicator-state contexts

## Preregistered session windows

Session time is based on the completed M5 setup timestamp.

- `MORNING_09_12`: 09:00 <= setup < 12:00
- `EXTENDED_09_15`: 09:00 <= setup < 15:00
- `FULL_09_1630`: 09:00 <= setup <= 16:30

These windows are fixed before execution. No alternative clock boundary may be introduced after seeing results.

## Execution family

Causal execution is inherited from Cycle27:

- signal is known only after the M5 setup bar completes;
- entry is the next causal M1 open;
- one active position per candidate;
- stop-first treatment on ambiguous intrabar stop/target touches;
- force/time exit is unchanged from Cycle27;
- GROSS / BASE / STRESS friction logic is unchanged.

Finite execution grid:

USDRUBF stops:
- 9
- 12
- 15 points

CNYRUBF control stops:
- 6
- 8
- 10 points

Targets:
- 3R -> max hold 120 min
- 4R -> max hold 180 min
- 5R -> max hold 240 min

No other stop, target, or hold values may be introduced after seeing results.

## Selection and evaluation windows

Discovery/selection:
- 2026-01-05 through 2026-02-28

Research-forward:
- 2026-03-01 through 2026-05-15

Never expose:
- retired 2026-05-16 through 2026-07-01 internal-confirmation data;
- TRUE OOS 2025.

Mar-May15 is already repeatedly inspected and remains research-only.

## Discovery gate

Use the unchanged Cycle27 discovery gate.

No threshold is lowered to preserve the historical Cycle27 near-miss.

## Deterministic ranking and shortlist

Discovery-pass candidates are ranked by:

1. descending minimum of January and February STRESS expectancy R;
2. descending full-discovery STRESS PF;
3. descending full-discovery BASE PF;
4. descending full-discovery STRESS expectancy R;
5. descending STRESS unique days;
6. candidate ID lexical tie-break.

Shortlist diversity:

- maximum 3 candidates per `(direction, session_window, anchor_mode)` bucket;
- maximum total shortlist = 30 per instrument.

This ranking/shortlist policy is frozen before forward evaluation.

## Forward survivor gates

A strict Cycle36 survivor must satisfy all:

- BASE PF >= 2.0
- STRESS PF >= 1.5
- BASE expectancy >= 0.30R
- STRESS expectancy >= 0.10R
- bootstrap P10 BASE mean R > 0
- BASE N >= 30
- BASE unique days >= 15
- STRESS N >= 20
- STRESS / BASE trade-count ratio >= 0.50
- all Mar / Apr / May1-15 BASE blocks positive
- all corresponding STRESS blocks positive
- largest BASE winner share <= 0.25
- GROSS total bps >= BASE total bps >= STRESS total bps

## Additional generalization gates

A strict survivor must also satisfy both:

1. **Session-window support**
   - at least one adjacent preregistered session window at the same direction/anchor/stop/target must have STRESS N >= 10 and positive STRESS expectancy R.

2. **Execution-neighbor support**
   - at least one one-axis adjacent stop or target setting at the same session window/direction/anchor must have STRESS N >= 10 and positive STRESS expectancy R.

These gates explicitly test whether the historical near-miss is a family rather than one isolated parameter cell.

## Decision rule

PASS:
- at least one candidate passes the strict forward gate and both generalization gates.

NEAR-MISS:
- forward economics remain positive and the family broadens sample, but one preregistered robustness gate fails.

FAIL:
- zero discovery passes, negative/fragile forward economics, or positive performance is isolated to one exact historical cell.

## Prohibitions

- no new indicator contexts;
- no new session boundaries;
- no new structures/events;
- no parameter or gate relaxation after seeing forward results;
- no optimization on Mar-May15;
- no May16-Jul1 access;
- no 2025 access;
- no relabeling of research-forward evidence as validation.