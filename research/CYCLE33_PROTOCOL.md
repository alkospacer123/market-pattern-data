# Cycle33 — Completed-H1 Regime Context for M5 ROUND Rejection

## Objective

Explore a genuinely different causal axis after Cycle32: higher-timeframe regime context derived only from **completed H1 bars**, while preserving the M5 causal rejection/execution machinery.

Cycle33 is not another attempt to tune the Cycle29/Cycle32 anchor pool. The structural event is frozen to ROUND rejection; the new variable is the H1 regime.

## Rationale from prior cycles

- Cycle29 found a strong but sparse CNY SHORT ROUND-rejection cluster.
- Cycle32 showed that adding ROLL60 events can expand N to ~30, but the added ROLL60 component does not independently retain positive STRESS expectancy.
- Therefore Cycle33 must rotate away from anchor pooling.
- Multi-timeframe regime conditioning has not been tested as a dedicated finite family in Cycles1–32.

## Preregistered hypothesis

A completed-H1 bearish regime can identify a broader set of M5 ROUND rejections with positive executable expectancy, increasing sample without importing weak non-ROUND level events.

The LONG mirror is retained as a control branch. USDRUBF is a replication/control instrument and must not drive CNY parameter selection.

## Causal H1 construction

H1 bars are resampled from M5 data by trading date/hour.

At every M5 setup bar, Cycle33 may use only an H1 bar whose end time is <= the M5 setup timestamp. The still-forming H1 bar is forbidden.

H1 regime features are computed from completed H1 bars only:
- `h1_ret_2h`: return of the latest completed H1 close versus two completed H1 bars earlier.
- `h1_eff_3h`: directional efficiency across the last three completed H1 close-to-close moves.

Quantile cutpoints are fit using Jan-Feb research-selection data only.

Preregistered context states:

SHORT:
- `H1_RET2_LOW25`
- `H1_BEAR_EFF75` = negative H1 2h return and H1 efficiency >= Jan-Feb Q75

LONG control:
- `H1_RET2_HIGH75`
- `H1_BULL_EFF75` = positive H1 2h return and H1 efficiency >= Jan-Feb Q75

No additional H1 feature/state may be selected based on Mar-May performance.

## Frozen M5 event family

- structure: ROUND only
- event: REJECTION only
- anchor modes: LEVEL, EVENT_EXTREME
- M5 setup; next causal M1 execution inherited from Cycle29
- probe/reclaim and second-touch geometries are excluded

Execution grid:
- CNY stops: 8, 10 points
- USDRUBF stops: 9, 12 points
- buffers: 1, 2, 3 ticks
- TTL: 15, 30 minutes
- targets: 4R, 5R, 6R
- GROSS/BASE/STRESS execution uncertainty unchanged from Cycle29

## Selection and evaluation

Discovery/selection: 2026-01-05 through 2026-02-28.
Research-forward: 2026-03-01 through 2026-05-15.

Never expose:
- retired 2026-05-16 through 2026-07-01 internal confirmation data;
- TRUE OOS 2025.

Mar-May15 has already been repeatedly inspected by prior research cycles and remains research-only. A Cycle33 pass is not validation.

## Forward survivor gates

Preserve Cycle29 strict economics/sample gates:
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

Additional robustness gates:
- at least two adjacent one-axis execution neighbors must retain positive STRESS expectancy with >=5 trades;
- the alternate preregistered H1 context for the same direction/execution must also have positive STRESS expectancy with >=5 trades.

## Decision rule

PASS:
A candidate passes all strict Cycle29 gates plus both new robustness gates.

NEAR-MISS:
Economics/sample are positive but one preregistered robustness axis fails.

FAIL:
Higher-timeframe conditioning does not produce a robust executable family.

## Prohibitions

- no optimization on Mar-May15;
- no new H1 indicators after seeing forward results;
- no threshold relaxation after seeing results;
- no May16-Jul1 or 2025 access;
- no relabeling of research-forward evidence as confirmation or validation.
