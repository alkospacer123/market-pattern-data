# Autonomous Research Orchestrator Policy — M1 + M5

Effective after the Cycle 31 infrastructure stall on 2026-08-30. This file governs orchestration only; it does not alter any preregistered research hypothesis or gate.

## Cycle identity

- A Cycle is one unique preregistered causal research hypothesis.
- GitHub Actions `run_attempt`, rerun, recovery leg, timeout recovery, or infrastructure retry is **not** a new Cycle.
- A failed/cancelled run with no executable research artifact is **not** a completed research result.

## Failure handling

1. Inspect workflow run, jobs, steps and artifacts before deciding research state.
2. If a job is queued/in-progress normally, do not start a duplicate.
3. If a run fails after research steps start, classify as an implementation failure, repair the same preregistered Cycle without changing its hypothesis/gates, then rerun it.
4. If jobs fail with `runner_id=0`, `steps=[]`, and no artifacts, classify as infrastructure failure. Do not advance the Cycle number and do not fabricate a research result.
5. Retry an infrastructure-failed run at most once per hourly orchestration invocation. Repeated no-runner failures are an infrastructure block, not research evidence.

## Mandatory signal timeframes for new Cycles

Every new research Cycle after Cycle 31 must search **both M1 and M5 as genuine signal timeframes**, independently, for both CNYRUBF and USDRUBF/Si.

- Candidate identity must include `timeframe=M1` or `timeframe=M5`.
- M1 and M5 candidates are ranked/gated separately; their statistics must never be pooled to pass a gate.
- M1 signal: decision only after the M1 bar closes; execution cannot begin before the next M1 bar/open.
- M5 signal: decision only after the M5 bar closes; executable path is evaluated only on subsequent M1 data.
- No look-ahead.
- Cross-timeframe agreement may be reported only as additional robustness information, never as a post-hoc rescue gate.

## Frozen research gates

Do not weaken preregistered gates after seeing results. Current Cycle 29/31 discovery and strict survivor thresholds remain the baseline unless a future cycle preregisters a different family before execution.

No seed shopping, manual winner seeding, post-result threshold relaxation, post-hoc anchor substitution, or stop widening.

## Data fences

- Reusable research/discovery data: Moscow `2026-01-05` through `2026-05-15` only.
- Jan-Feb: selection/tuning only.
- Mar-May15: research-forward only.
- `2026-05-16` through `2026-07-01`: **RETIRED**; never read for selection, tuning, ranking, re-checking, or confirmation.
- TRUE OOS 2025: **SEALED**.
- A future survivor must wait for genuinely new untouched confirmation data.

## Registry

For every completed instrument × timeframe leg, inspect executable GROSS/BASE/STRESS. Add every new executable research-positive candidate to `research/profitable_systems_registry.json`, including its timeframe and one of:

- `research_positive`
- `discovery_survivor`
- `confirmation_failed`
- `validated`

A strong candidate that misses survivor only on sample size, temporal consistency, bootstrap, or another strict gate remains in the registry as `research_positive` if executable BASE and STRESS research-forward results are positive.

## Next-cycle rule

Only after a completed research Cycle produces valid artifacts and no sufficient survivor, and no next Cycle is active:

1. classify the causal failure mode from GROSS→BASE→STRESS, sample size, temporal blocks, bootstrap, winner concentration and execution;
2. preregister one new unique causal hypothesis before seeing its result;
3. implement independent CNYRUBF/USDRUBF × M1/M5 legs;
4. launch it once in GitHub Actions.

Cycle 31 remains the current preregistered research Cycle until it either produces executable artifacts or is explicitly superseded for a documented non-research reason. Its repeated no-runner attempts on 2026-08-30 are infrastructure retries, not additional Cycles.
