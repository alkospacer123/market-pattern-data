# Autonomous Search Tuning v2 — post-Cycle31

Status: preregistered search-policy change for NEW research families only. It does not alter Cycle 31 or retroactively change any prior gate/result.

## Why this change exists

A historical CMD audit of round-level touch optimizers showed that the autonomous pipeline has a structural blind spot. The CMD archive contains broad profitable parameter neighborhoods on both M1 and M5, whereas recent autonomous cycles increasingly focused on complex M5 structure/event/context combinations. The CMD results are historical and post-hoc relative to the current research protocol, so their exact winning parameters MUST NOT be seeded into formal discovery. They may be used only as architecture-calibration evidence: the machine must be capable of searching simple repeated-touch geometry, wide payoff ranges, both M1 and M5, and family-level parameter plateaus.

The CMD engine is also materially more optimistic than the autonomous executable contract: it enters at the signal-bar close and does not model BASE/STRESS adverse friction. Therefore CMD PF is not directly comparable with autonomous BASE/STRESS PF. Formal autonomous research keeps the causal/executable contract below.

## Absolute data fences

- Formal research/discovery may read only Moscow 2026-01-05 through 2026-05-15.
- Jan-Feb is selection/tuning only.
- Mar-May15 is research-forward only.
- 2026-05-16 through 2026-07-01 is RETIRED and must not be read for selection, tuning, ranking, feature engineering, re-checking or confirmation.
- TRUE OOS 2025 remains SEALED.
- No post-2026-07-01 data may be treated as research data; genuinely new untouched data requires a separate confirmation decision.

## Core change: two-layer search architecture

### Layer A — simple market geometry FIRST

Every new broad discovery cycle must include simple causal primitives before adding complex context filters:

1. ROUND_TOUCH — repeated tests/touches of the nearest frozen round level.
2. EQUAL_CLUSTER — repeated equal/near-equal highs or lows.
3. PREV_DAY / PREV_SESSION high-low interactions.
4. OPEN_RANGE / OPEN30 interactions.
5. ROLLING_EXTREME / causal fractal interactions.
6. COMPRESSION / balance geometry where implemented causally.

A simple primitive is allowed to stand alone. REJECTION, SWEEP_RECLAIM, BREAK_RETEST, trend/context and volatility state are OPTIONAL refinements, not mandatory prerequisites.

### Layer B — conditional/refined geometry SECOND

Only after Layer-A candidates are generated may the search add one causal refinement at a time, such as event type, broad volatility/efficiency state, trend state or clock bucket. Do not require a compound structure+event+context stack by default.

## Mandatory signal timeframes

Each new search family must run independently on:

- CNYRUBF M1
- CNYRUBF M5
- USDRUBF/Si M1
- USDRUBF/Si M5

M1 is a genuine signal timeframe, not merely an execution layer for M5. Candidate identity and registry records must include `timeframe`.

Do not pool M1 and M5 statistics for selection or survivor gates.

## Repeated-touch templates

Generic repeated-test search must support both template classes without using historical CMD winners as seeds:

### CONSECUTIVE

- n-of-n completed bars
- n in {2,3,4,5}

### WINDOW

- required_touches k in {2,3,4,5}
- window_bars w in {3,5,7,9}
- require k <= w

Touch state must be defined causally from completed signal bars only. Reset/session rules must be explicit and preregistered.

## Round-level semantics

- CNYRUBF round step: 0.05
- USDRUBF/Si round step: 0.10
- tolerance search must include exact touch and small finite neighborhoods: {0,1,2} ticks where instrument geometry permits.
- nearest-grid assignment must be deterministic.
- level identity and touch count are frozen/known only from completed bars.

## Direction search

Every simple family must consider independently:

- LONG
- SHORT
- BOTH

Do not assume symmetry and do not require pooled LONG+SHORT performance.

## Stop search

Use a broad preregistered executable grid rather than only the Cycle29/31 stop subset.

CNY fixed stop ticks: {3,4,5,6,8,10}; never widen beyond 10 ticks inside a completed candidate.

Si fixed stop ticks: {3,4,5,6,8,9,12,15,20}.

Where structural stops are used, the anchor and buffer must be frozen at signal time and the final stop must respect the family cap. No post-fill widening.

Buffer ticks for simple level families: {1,2,3,4} where the resulting stop is legal.

## Target search

The search must not truncate high-payoff families at 6R. Generic fixed-R target grid:

{2R,3R,4R,5R,6R,7R,8R,9R,10R}

High target R is not sufficient by itself; executable expectancy and robustness remain mandatory.

## Time / holding search

Simple families may search a small preregistered set of last-entry cutoffs / clock buckets, but time must not be used to carve around observed losses post hoc. Candidate neighborhoods that survive nearby cutoffs are preferred.

## Causal entry contract — mandatory

Historical CMD same-close entry is NOT allowed in formal autonomous research.

### M1 signal

- signal is known only after the M1 bar closes;
- earliest executable entry is the next causal M1 open / next eligible M1 bar;
- never credit the signal-bar close as an executable fill.

### M5 signal

- signal is known only after the completed M5 close;
- execution begins only on subsequent M1 data;
- never use any M1 observation belonging to the completed signal M5 bar after the decision timestamp.

## Execution scenarios

Every formal candidate must be evaluated under the same causal trade identity with:

- GROSS — diagnostic only;
- BASE — realistic adverse execution assumption;
- STRESS — harsher adverse execution assumption.

Keep STOP_FIRST when stop and target are touched in the same executable M1 bar. Fill-bar target credit is forbidden. Adverse stop gaps exit conservatively; favorable target gaps receive no favorable improvement beyond the frozen target. Commission remains separately reported unless a future preregistered contract explicitly includes it.

## Search/ranking change: rank FAMILIES and PLATEAUS, not only rows

For each primitive × instrument × timeframe, retain multiple views:

- TOP_PF
- TOP_EXPECTANCY / mean R
- TOP_TOTAL_R / profit
- TOP_ROBUST
- TOP_SAMPLE / high-N positive

Do not select a single global winner and discard the rest.

Build a semantic-neighborhood graph over candidate parameters. A candidate family receives higher robustness only when multiple genuine neighboring configurations remain executable-positive. Non-binding axes must be detected and must NOT be counted as independent neighbor evidence.

Required cluster diagnostics include:

- number of positive one-axis neighbors;
- PF / E[R] dispersion inside the neighborhood;
- direction concentration;
- temporal block consistency;
- winner concentration;
- trade/date count;
- sensitivity to target, stop/buffer, tolerance, touch count/window and entry cutoff.

## Discovery flow

### Stage 0 — architecture calibration (NON-FORMAL)

Use the historical CMD family definitions only to verify that the new engine can represent those semantic classes. Exact historical winners may be replayed only as labeled `historical_calibration`, never as formal discovery candidates or survivors.

Run two replays when raw data permits:

A. LEGACY replay: reproduce CMD semantics, including same-close entry, solely to check implementation correspondence.
B. CAUSAL replay: same semantic rule but next-open entry plus GROSS/BASE/STRESS on the allowed research fence only.

The difference A→B quantifies execution optimism. Neither replay may promote a survivor because the rule was selected post hoc from historical results.

### Stage 1 — formal Jan-Feb broad discovery

Generate the full preregistered generic grid without historical winner seeding. Search M1 and M5 separately, by instrument. Retain multiple top tables and cluster summaries.

### Stage 2 — freeze family shortlist

Freeze clusters, not isolated best rows. Ranking priority:

1. lower-tail executable robustness across Jan and Feb;
2. genuine positive-neighbor density;
3. STRESS PF / E[R];
4. BASE PF / E[R];
5. independent dates/trades;
6. low winner concentration;
7. canonical semantic ID.

Cap near-duplicate rows per semantic cluster so one plateau does not crowd out other families.

### Stage 3 — Mar-May15 research-forward

Evaluate the frozen complete candidates and family neighborhoods with no retuning.

## Gates

Cycle31 frozen gates remain unchanged for Cycle31.

For new standard families, retain the existing strict survivor philosophy unless a future protocol preregisters a different family-specific gate BEFORE results. At minimum a survivor must demonstrate:

- BASE PF >= 2.00;
- STRESS PF >= 1.50;
- BASE E[R] >= +0.30;
- STRESS E[R] >= +0.10;
- positive lower-tail day bootstrap;
- meaningful independent N and trading dates;
- positive temporal blocks, including March, April and May1-15 under BASE and STRESS;
- low winner concentration;
- genuine local parameter robustness.

Do not relax gates after seeing a result. Sparse profitable candidates remain `research_positive` until a separately preregistered sparse-family protocol exists.

## Persistent registry

Store every executable-positive research-forward candidate/family, not only formal survivors. Required fields:

- cycle
- family
- semantic_cluster_id
- candidate_id
- instrument
- timeframe
- direction
- parameters
- GROSS/BASE/STRESS metrics
- trade/date counts
- temporal blocks
- bootstrap
- winner concentration
- neighbor/plateau diagnostics
- exact pass/fail reasons
- status

Historical CMD registry remains separate. Formal autonomous registry may reference a historical family only through `calibration_lineage`, never by treating historical CMD metrics as current evidence.

## Continuous-search behavior

After a completed formal cycle:

- register all new executable-positive candidates;
- classify failure mode;
- immediately preregister and start the next unique causal family if fewer than 3 independent discovery survivors exist;
- do not wait for an hourly boundary to begin the next cycle when running on the local research daemon;
- hourly orchestration is a watchdog/heartbeat, not the research cadence.

Target state: at least 3 genuinely independent discovery survivors (different timeframe/instrument/family/entry mechanism, not three neighboring parameter rows). TRUE OOS remains sealed until a separate confirmation decision.