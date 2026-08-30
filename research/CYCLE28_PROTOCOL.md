# Cycle 28 — M1 Fixed-Stop Microstructure Events

Preregistered before Cycle 27 results are known. Cycle 28 is an independent fixed-stop hypothesis class: the protective structure and trigger are formed on completed M1 bars, while M5 information may only act as frozen context.

## Fences

- Research-only.
- Read only Moscow 2026-01-05 through 2026-05-15.
- 2026-05-16 through 2026-07-01 MUST NOT be read.
- 2025 TRUE OOS remains SEALED.
- Jan-Feb discovery; Mar-May15 research forward only.

## Fixed stops

One point = one exchange-price increment in repository data.

- CNYRUBF: 6, 8, 10 points; no stop >10.
- USDRUBF/Si: 6, 9, 12, 15 points.

Stop is exact fixed distance from the next-M1-open entry and may never widen.

## M1 protective structures

All structures must be known before entry:

- latest confirmed five-bar M1 fractal;
- prior 15-minute high/low;
- prior 30-minute high/low;
- prior-day high/low;
- equal-high/equal-low cluster from the prior 30 minutes within 2 ticks;
- relevant round level;
- opening-range high/low after 09:30.

## M1 event families

Signals require a completed two-stage micro event rather than a single arbitrary bar.

1. `SWEEP_CONFIRM`: M1 bar sweeps the structure by 1-5 ticks and closes back across it; the next completed M1 bar does not re-break the sweep extreme and closes in trade direction.
2. `REJECT_FOLLOW`: M1 bar touches/penetrates the structure by <=4 ticks and closes back; next completed M1 bar closes farther away from the level.
3. `BREAK_RETEST_CONFIRM`: structure is broken on a completed M1 bar, retested within the next 1-5 completed M1 bars, and the completed retest bar closes on the continuation side.

Entry is the exact open of the M1 bar immediately after the event confirmation.

## Stop hiding

Protective anchor is frozen at signal time and is one of:

- the structural level itself;
- sweep/retest extreme;
- latest confirmed micro-fractal behind the entry when it belongs to the event sequence.

A trade exists only when the fixed stop lies beyond the protective anchor by 1-3 ticks. No fitting anchor = no trade.

## Reward

Fixed target from entry:

- 3R;
- 4R;
- 5R;
- 6R.

No target below 3R. Same-day only, force close 17:00. Hold ceilings may be 60, 120, 240 minutes or to 17:00 and are frozen as part of candidate identity before outcome ranking.

## Optional M5 context

At most ONE completed-M5 causal state may qualify an M1 event. Allowed state family is the Cycle-27 target-free whitelist. Quantile thresholds are fitted Jan-Feb only and frozen for forward application. Depth >1 is forbidden.

## Execution

- eligible entries 09:00-16:30 Moscow;
- exact next M1 open after confirmation;
- one position at a time per instrument;
- STOP_FIRST same-bar ambiguity;
- adverse stop gap at M1 open;
- favorable target gap conservatively at target;
- GROSS/BASE/STRESS = 0/1/2 adverse ticks per side;
- commission excluded.

## Discovery and forward gates

Use the same Jan-Feb discovery gate and strict Mar-May gate as Cycle 27:

- discovery must work separately in January and February;
- combined discovery BASE PF >=2.0, STRESS PF >=1.4, BASE E[R] >=+0.30, STRESS E[R] >=+0.10;
- forward BASE PF >=2.0, STRESS PF >=1.5;
- forward BASE E[R] >=+0.30, STRESS E[R] >=+0.10;
- day-bootstrap P10 BASE E[R] >0, seed 20260401;
- >=30 forward trades and >=15 dates;
- March, April and May1-15 all positive in BASE and STRESS;
- largest BASE winner share <=0.25;
- GROSS total bps >= BASE >= STRESS.

Any survivor remains research-only and needs genuinely new untouched confirmation data. Retired May16-Jul1 and 2025 remain sealed.
