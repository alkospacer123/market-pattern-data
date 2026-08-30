# Cycle 22 implementation note — frozen before execution

`CYCLE22_PROTOCOL.md` preregistered the regression prediction tails P95/P97.5 and a frozen classifier probability threshold, but did not state the classifier threshold quantile explicitly.

Before any Cycle-22 result is computed, this ambiguity is resolved as follows:

- target-hit classifier threshold = **P75 of validation predicted probabilities**;
- a validation/future row must exceed BOTH the selected STRESS-R regression tail threshold (P95 or P97.5) and classifier P75;
- this matches the already-preregistered dual-model convention used in Cycles 18 and 19;
- no alternative classifier quantile will be tested in Cycle 22.

All other Cycle-22 protocol fields remain unchanged.
