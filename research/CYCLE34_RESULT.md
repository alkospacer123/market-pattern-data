# Cycle34 Result — Exit/Occupancy Compression over Frozen M5 ROUND Rejection

## Research status

**NO_EXIT_OCCUPANCY_RESEARCH_SURVIVOR**

Cycle34 was preregistered before execution and ran on the same fenced research dataset used for the Intel replay: Jan-Feb selection, Mar-May15 research-forward, no access to retired 2026-05-16 through 2026-07-01 confirmation data, and no access to TRUE OOS 2025.

## CNYRUBF

- Generated candidate evaluations: 144
- Deduped discovery candidates: 144
- Discovery passes: 0
- Shortlisted: 0
- Strict survivors: 0

## USDRUBF control

- Generated candidate evaluations: 120
- Deduped discovery candidates: 120
- Discovery passes: 0
- Shortlisted: 0
- Strict survivors: 0

## Interpretation

The frozen M5 ROUND-rejection entry with `eff_60m:HIGH25` did not produce a single Jan-Feb discovery pass when the only new axis was compressed target/occupancy geometry:

- 1.5R / maximum hold 60 minutes
- 2R / maximum hold 90 minutes
- 3R / maximum hold 120 minutes

Because the failure occurs before the Mar-May15 research-forward stage, this is stronger evidence than a single weak forward period: the lower-R/shorter-hold family is rejected as implemented.

The result suggests that the strong Cycle29 ROUND-rejection cluster is not a generic local entry edge that can simply be harvested with smaller targets and greater turnover. Its positive economics appear linked to the sparse high-R payoff geometry.

## Decision

- Close the moderate-R exit/occupancy compression branch as implemented.
- Do not tune intermediate targets/hold times after seeing this result.
- Preserve the original Cycle29 high-R ROUND cluster as a research-positive, sample-limited motif; do not relabel it as a survivor.
- Rotate Cycle35 away from ROUND and toward a genuinely different structural family.

Research-only. No validation claim is made.