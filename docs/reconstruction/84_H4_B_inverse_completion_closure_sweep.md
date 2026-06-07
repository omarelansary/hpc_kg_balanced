# H4-B Inverse Completion Closure Sweep

## Purpose

This document records a bounded H4-B closure sweep for labelled inverse-pair rule-completion. It does not query WDQS, call LLMs, run KGE, implement H4-C, or update the candidate registry.

All generated H4-B edges are labelled `synthetic_rule_completion` and are not canonical observed triples. The sweep is not a global optimum proof; it is a predeclared bounded sweep over H4-B modes.

## Run

Run path: `/tmp/H4_labelled_rule_completion/runs/h4_B_inverse_closure_sweep_20260607T094357Z`

Run location status: `temporary_not_durable`

The repository experiment path was not writable in this execution context, so runtime graph outputs were written under `/tmp` and are `temporary_not_durable`. These graph outputs require deliberate rerun or preservation before supervisor handoff or artifact promotion.

## Modes Tested

- H4-B1 strict conservative: confidence threshold `0.8`, deficit-capped, underfilled targets only, frozen-observed candidates excluded, no safe-delete.
- H4-B2 add-all stress: all required inverse rule-completion edges after excluding B0 and frozen-observed candidates; low-confidence and overfilled targets included as stress-test behavior.
- H4-B3 add-all plus strict base-support safe-delete: starts from H4-B2, preserves original entities, WCC, relation coverage, and base support for retained synthetic edges.
- H4-B4 confidence-tiered deficit-capped modes: `>=0.9`, `>=0.8`, `>=0.7`, and all verified confidence.

Pair-level confidence is used because orientation-specific confidence is not preserved in the current evidence.

## Metrics Table

| Mode | Decision | Synthetic edges | Triples | Triples/entity | Surplus | Deficit | Inverse deficit | Composition surplus | WCC | Coverage | Duplicates | Deletions |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H4-B1_strict_conservative | synthetic_augmented_candidate_for_review | 158 | 24841 | 1.134655 | 6702 | 1861 | 58.339113 | 6266.933965 | 1 | 139/139 | 0 | 0 |
| H4-B2_add_all_stress | stress_test_only | 3774 | 28457 | 1.299822 | 10253 | 1796 | 0.000000 | 6290.417360 | 1 | 139/139 | 0 | 0 |
| H4-B4_confidence_gte_0_9_deficit_capped | synthetic_augmented_candidate_for_review | 112 | 24795 | 1.132554 | 6702 | 1907 | 100.733744 | 6266.933965 | 1 | 139/139 | 0 | 0 |
| H4-B4_confidence_gte_0_8_deficit_capped | synthetic_augmented_candidate_for_review | 158 | 24841 | 1.134655 | 6702 | 1861 | 58.339113 | 6266.933965 | 1 | 139/139 | 0 | 0 |
| H4-B4_confidence_gte_0_7_deficit_capped | synthetic_augmented_candidate_for_review | 210 | 24893 | 1.137030 | 6702 | 1809 | 15.470831 | 6266.933965 | 1 | 139/139 | 0 | 0 |
| H4-B4_all_verified_deficit_capped | synthetic_augmented_candidate_for_review | 223 | 24906 | 1.137624 | 6702 | 1796 | 5.327974 | 6266.933965 | 1 | 139/139 | 0 | 0 |
| H4-B3_add_all_strict_base_support_safe_delete | stress_test_only | 3774 | 27667 | 1.263737 | 9463 | 1796 | 0.000000 | 6267.670336 | 1 | 139/139 | 0 | 790 |

## B1 Reproduction

B1 reproduction status: `matched`.

The sweep reproduced the prior H4-B1 result exactly for generated edge count, surplus, deficit, and inverse deficit:

- generated synthetic edges: `158`
- total surplus: `6702.0`
- total deficit: `1861.0`
- inverse deficit: `58.33911295323014`

## Add-All Stress Result

H4-B2 generated `3774` synthetic inverse edges and eliminated inverse deficit, but it increased total surplus from `6702` to `10253.0` and raised the synthetic edge ratio to `0.132621`. It also included `158` generated edges targeting overfilled relations and `226` generated edges involving composition-heavy relations.

Therefore H4-B2 is `stress_test_only`, not a candidate by default.

## Safe-Delete Result

H4-B3 accepted `790` strict deletions after add-all completion. It deleted `0` synthetic edges and `0` base-support triples for retained synthetic edges. It rejected `3774` base-support deletion attempts.

Safe-delete reduced H4-B2 surplus by `790`, but the final H4-B3 surplus remained `9463.0`, above B0. It also remained an add-all stress configuration with `3774` synthetic edges, so it is `stress_test_only`.

## Best Observed Configuration

Best observed under the tested H4-B sweep: `H4-B4_all_verified_deficit_capped`.

This mode generated `223` synthetic inverse edges, preserved WCC `1`, preserved `139/139` coverage, kept duplicate count `0`, kept total surplus at `6702.0`, reduced total deficit to `1796.0`, and reduced inverse deficit to `5.327974`.

This is the best observed configuration by construction metrics in the tested sweep. It is not necessarily the most conservative evidence setting, because it includes all verified inverse rules, including rules below the 0.8 confidence threshold.

This is a labelled synthetic augmentation result for review, not a final KG and not canonical observed evidence.

## Candidate and Stress Labels

Candidate-for-review modes:

- `H4-B1_strict_conservative`
- `H4-B4_confidence_gte_0_9_deficit_capped`
- `H4-B4_confidence_gte_0_8_deficit_capped`
- `H4-B4_confidence_gte_0_7_deficit_capped`
- `H4-B4_all_verified_deficit_capped`

Stress-test-only modes:

- `H4-B2_add_all_stress`
- `H4-B3_add_all_strict_base_support_safe_delete`

## Global Optimum Limitation

This H4-B closure sweep is not a global optimum proof. It is a predeclared bounded sweep over inverse-completion modes; exact optimization over all additions and deletions was not performed on the real graph.

Exact optimization over all inverse additions and deletions was not performed on the real graph. If exact search is useful, it should be limited to small toy cases and must not be reported as a real-graph global maximum.

## Claim Boundary

Safe claims:

- H4-B generated labelled `synthetic_rule_completion` inverse-pair edges only.
- Frozen-observed candidates were excluded from generated synthetic edges.
- Deficit-capped modes preserved WCC `1`, `139/139` coverage, and duplicate-free status.
- Several conservative H4-B modes improved deficit and density without increasing surplus.
- H4-B2/B3 are stress tests and are not candidates by default.

Unsafe claims:

- H4-B edges are canonical observed triples.
- H4-B proves generated inverse triples are true Wikidata facts.
- H4-B proves KGE behavior.
- H4-B is globally optimal.
- Temporary `/tmp` graph outputs are durable promoted artifacts.

## Decision

H4-B is not closed as a failure. The best observed configuration under the tested H4-B sweep is `H4-B4_all_verified_deficit_capped`, with decision state `synthetic_augmented_candidate_for_review`.

No registry update is recommended now. Durable artifact preservation or rerun under a writable experiment path is required before supervisor handoff or artifact promotion.
