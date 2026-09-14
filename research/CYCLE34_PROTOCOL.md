# Cycle34 — Exit/Occupancy Compression over Frozen M5 ROUND Rejection

## Objective

Test a genuinely different causal axis after Cycle33: keep the structural entry semantics fixed and change only the exit/occupancy geometry.

Cycle34 asks whether the strongest late-stage ROUND-rejection motif can increase executable sample by exiting sooner, without importing weaker anchors/events or relaxing survivor gates.

## Prior evidence

- Cycle29 found a strong but sparse CNY SHORT ROUND-rejection cluster, with the best member around BASE PF 3.317 / STRESS PF 2.977 but only N16.
- Cycle32 showed that semantic pooling can raise N to roughly 30, but the added ROLL60 component did not independently carry the edge.
- Cycle33 showed that completed-H1 regime conditioning produces zero Jan-Feb discovery passes on both instruments.
- Therefore Cycle34 must not add another context filter or another level family.

## Preregistered hypothesis

The ROUND-rejection entry contains real local edge, but the 4R–6R high-return exits keep positions occupied too long and suppress executable sample. Lower targets with shorter fixed maximum holding times may preserve stress-adjusted expectancy while allowing more independent trades.

## Frozen entry family

Primary instrument: CNYRUBF.
USDRUBF remains a replication/control instrument and must not drive CNY selection.

Direction:
- SHORT is the primary hypothesis.
- LONG mirror is a control branch and is ranked separately.

Frozen event/structure:
- timeframe: M5 setup;
- structure: ROUND only;
- event: REJECTION only;
- anchor modes: LEVEL and EVENT_EXTREME;
- context: `eff_60m:HIGH25` only;
- passive entry;
- next-causal-M1 execution inherited from Cycle29;
- probe/reclaim, second-touch, ROLL30/ROLL60 and equal-level pooling are excluded.

## Exit/occupancy family

The only new research axis is target/maximum-hold compression:

- 1.5R -> max hold 60 minutes
- 2.0R -> max hold 90 minutes
- 3.0R -> max hold 120 minutes

Stops remain finite and centered on the prior robust neighborhood:
- CNYRUBF: 8, 10 points
- USDRUBF: 9, 12 points

Other execution dimensions remain frozen finite sets:
- buffer: 1, 2, 3 ticks
- order TTL: 15, 30 minutes
- GROSS / BASE / STRESS fill-through and exit friction unchanged from Cycle29
- one active position per candidate; occupancy ends only at the causal exit

## Selection and evaluation windows

Discovery/selection:
- 2026-01-05 through 2026-02-28

Research-forward:
- 2026-03-01 through 2026-05-15

Never expose:
- retired 2026-05-16 through 2026-07-01 internal-confirmation data;
- TRUE OOS 2025.

Mar-May15 is already repeatedly inspected and remains research-only. A Cycle34 pass is not validation.

## Discovery gate

Use the unchanged Cycle29 discovery gate. No threshold is lowered for the lower-R family.

## Candidate freezing

All discovery-pass candidates are ranked using discovery data only, with the same deterministic priority used by the late structural search:
1. maximize the weaker of January-STRESS and February-STRESS expectancy;
2. maximize discovery STRESS PF;
3. maximize discovery BASE PF;
4. maximize discovery STRESS expectancy;
5. maximize discovery BASE unique days;
6. deterministic candidate ID tie-break.

Freeze at most 60 candidates.

Diversity cap before forward evaluation:
- at most 3 candidates per `(direction, anchor_mode, target_r)` bucket.

No Mar-May15 quantity may affect ranking, deduplication, or shortlist membership.

## Forward survivor gates

Use the unchanged Cycle29 strict gates:
- BASE PF >= 2.0
- STRESS PF >= 1.5
- BASE expectancy >= 0.30R
- STRESS expectancy >= 0.10R
- bootstrap P10 BASE mean R > 0
- BASE N >= 30
- BASE unique days >= 15
- STRESS N >= 20
- STRESS/BASE trade ratio >= 0.50
- all Mar / Apr / May1-15 BASE blocks positive
- all corresponding STRESS blocks positive
- largest BASE winner share <= 0.25

## Additional robustness gates

A strict Cycle34 survivor must also satisfy both:

1. Exit-axis neighbor support:
   at least one adjacent preregistered target/hold pair must have STRESS N >= 10 and positive STRESS expectancy.

2. Execution neighbor support:
   at least one one-axis stop/buffer/TTL neighbor at the same target/hold must have STRESS N >= 10 and positive STRESS expectancy.

These gates prevent an isolated lucky exit setting from being called a survivor.

## Decision rule

PASS:
A candidate passes the unchanged Cycle29 forward gate plus both Cycle34 robustness gates.

NEAR-MISS:
The compressed-exit family clearly raises N and retains positive BASE/STRESS economics but misses one preregistered gate.

FAIL:
Lower target/shorter occupancy destroys PF/expectancy, does not increase usable sample, or robustness depends on one isolated exit/execution setting.

## Prohibitions

- no new context filters after seeing Cycle34 forward results;
- no target values other than 1.5R, 2R, 3R;
- no hold times other than 60, 90, 120 minutes mapped above;
- no threshold relaxation after seeing results;
- no optimization on Mar-May15;
- no May16-Jul1 access;
- no 2025 access;
- no relabeling of research evidence as confirmation or validation.
