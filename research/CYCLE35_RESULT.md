# Cycle35 Result — Opening-Range Structural Behavior

## Research status

**NO_OPENING_RANGE_RESEARCH_SURVIVOR**

Cycle35 was preregistered before execution and tested the session-defined `OPEN30` structure without context filters. The event family was limited to `REJECTION`, `SWEEP_RECLAIM`, and `BREAK_RETEST`, with `LEVEL` and `EVENT_EXTREME` anchors and the existing causal next-M1 execution model.

## Result

For both instruments:

- frozen shortlist: **0**
- strict survivors: **0**

The archived `shortlist.json` and `survivors.json` files are empty arrays for both CNYRUBF and USDRUBF.

Because the Cycle35 engine appends a candidate only after `c27.discovery_pass(...)` returns true, and the shortlist is then built directly from that candidate list, an empty shortlist implies **zero Jan-Feb discovery passes**. No Mar-May15 forward candidate existed to evaluate.

Exact generated/deduped evaluation counts were not recovered from the uploaded RAR5 manifest in this audit environment; they are not required for the research decision because the discovery-pass set is provably empty from the archived shortlist plus the frozen engine logic.

## Decision

The dedicated opening-range hypothesis is **rejected as implemented**.

Carry forward:

- Do not tune the OPEN30 window or add context filters after seeing this failure.
- Do not search nearby opening-range lengths to rescue the family on the same inspected data.
- `OPEN30 + REJECTION/SWEEP_RECLAIM/BREAK_RETEST` with no context has no Jan-Feb discovery survivor on either instrument under the frozen Cycle35 gates.
- Rotate away from OPEN30.

## Next research direction

Cycle36 should return to a **different, previously observed independent research-positive cluster**, not to CNY ROUND and not to opening range: the USDRUBF morning `ROLL30 REJECTION` family from Cycle27.

That family previously produced a research-positive near-miss around `SHORT REJECTION ROLL30 EVENT_EXTREME`, morning session, fixed stop and ~4R target, with positive BASE/STRESS economics but insufficient sample/temporal robustness. Cycle36 will test whether that motif generalizes across preregistered wider session windows and adjacent execution settings without adding indicator contexts or relaxing gates.

Research-only. Retired 2026-05-16..2026-07-01 and TRUE OOS 2025 remain closed.