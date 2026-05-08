# C3 Remove-And-Replace Experiment Plan

Status: plan only. C3 does not exist. No C3 graph has been generated, no C3 output directory has been created, and `docs/reconstruction/graph_candidates.tsv` has not been edited for C3.

## 1. Evidence From C2

C2 tested deletion-only targeted generic pruning from B0.

Evidence:

- C2 graph: `experiments/graph_candidates/C2_targeted_generic_pruning/outputs/pruned_graph.jsonl`
- Generation report: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json`
- Evaluator report: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`
- Decision: `experiments/graph_candidates/C2_targeted_generic_pruning/decision.md`
- Interpretation: `docs/reconstruction/12_C2_result_interpretation.md`

Verified C2 result:

| Metric | Value |
| --- | ---: |
| Accepted deletions | 27 |
| Weak components | 1 |
| Largest weak component ratio | 1.0 |
| Duplicate triples | 0 |
| Unique relations | 139 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total deficit | 2019 |
| Total surplus | 6675 |
| `P31` observed / surplus | 5952 / 5714 |
| `P279` observed / surplus | 744 / 517 |
| `P131` observed / surplus | 337 / 158 |

C2 rejection reasons:

| Reason | Count |
| --- | ---: |
| `would_disconnect_graph` | 75893 |
| `endpoint_degree_not_redundant` | 16212 |
| `no_connectivity_safe_candidate` | 1 |

Why deletion-only failed:

C2 preserved connectivity and relation coverage, but it reduced B0 total surplus by only 27, from 6702 to 6675. C2 did not beat C1's total surplus of 6582. The dominant blocker was `would_disconnect_graph`, which indicates that many deletion candidates in `P31`, `P279`, and `P131` act as weak-connectivity-supporting edges under the current invariant.

Why C3 should not repeat deletion-only pruning:

A second deletion-only run would test the same failure mode unless it relaxes connectivity or relation-coverage constraints. Those constraints are thesis-critical, so the next experiment should preserve them and change the operation type: add or identify replacement connectivity first, then remove generic surplus edges.

## 2. Existing Implementation Evidence

| Script or artifact | What it appears to do | Reuse safety | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| `src/Pruning graph/kg_balance_remove_replace.py` | Sequential remove-and-replace skeleton. It scores removal candidates, accepts plain prune if connectivity remains, otherwise searches one-hop/two-hop WDQS bridge replacements and accepts swaps if connectivity is restored and net score is positive. | Not safe to run directly as C3 without a controlled wrapper. It dynamically imports old pruner and repair modules, uses live WDQS helpers, and its docstring calls it a first skeleton, not a finished optimizer. Useful as design reference. | High for source behavior; low for executed reliability | Source docstring and code in `src/Pruning graph/kg_balance_remove_replace.py`; no execution log found by search for `kg_balance_remove_replace` or `remove_replace` outside source. |
| `src/kg_building/repair_kg_connectivity.py` | Audit-safe connectivity repair using WDQS one-hop/two-hop bridge paths into the largest weak component. It writes manifest/state/events/graph_output/report. | Useful source of design and historical bridge events. Direct reuse would require live WDQS unless adapted to local candidate pools. | High | Source docstring; Stage11/Stage12 manifests and reports. |
| `src/kg_building/repair_relation_allocated_absence.py` | Repairs missing allocated relations using directed two-hop motifs and WDQS anchored queries. It writes accepted/rejected candidate logs and candidate pools. | Useful for candidate-pool schema ideas. Not directly a C3 swap engine; it targets missing relations and old Trial9 artifacts. | High | Source docstring; `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial*/summary.json`. |
| `scripts/slurm/stage13_balance_prune_revised_density_aware.slurm` | Runs Stage13 pruning and post-processing. Protects `P31`/`P279`, applies hard relation floors, and analyzes pruned/largest-component graphs. | Do not reuse for C3; it is deletion-oriented, not remove-and-replace. | High | `scripts/slurm/stage13_balance_prune_revised_density_aware.slurm`; `logs/stage13_prune_revised_29012090.out`; C1 report. |
| `tools/graph_candidate_generation/targeted_generic_dominance_prune.py` | Controlled C2 deletion-only generator with hashes, config checks, reports, and evaluator compatibility. | Useful as operational/provenance template only. Do not extend it into C3 by adding replacement logic unless that remains isolated and named as C3. | High | C2 run reports and source. |

Execution evidence gap:

No log or report was found proving that `src/Pruning graph/kg_balance_remove_replace.py` was executed for B0, C1, C2, or any final-candidate graph. Therefore C3 must not claim prior remove-and-replace success.

## 3. Candidate-Pool Availability

Local historical candidate artifacts exist, but they are not yet a clean C3 replacement pool.

| Candidate source | Local/frozen? | Contents | Reproducibility risk | C3 suitability |
| --- | --- | --- | --- | --- |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/collected_candidates_all.jsonl` | Local file | WDQS-derived candidate repair triples with query text/hash and graph context. | Frozen as a file, but provenance is tied to Trial9 and allocation `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json`, not the canonical 5k allocation. | Possible exploratory replacement source after compatibility audit; not directly canonical. |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/collected_candidates_all.jsonl` | Local file | Larger repair-candidate collection; summary reports 178 accepted repairs and 5186 rejected candidates. | Same Trial9/allocation mismatch; may include triples irrelevant to B0 bridge-like generic edges. | Possible exploratory source only. |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial*/pair_candidates.jsonl` | Local file | Relation-pair priority candidates with `missing_relation`, `realized_relation`, support, anchor counts, and scores. | Derived from older repair objective, not C3 objective. | Useful for ranking ideas; not sufficient alone as replacement triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/events.jsonl` and `state.json` | Local files | Stage11 bridge discoveries and applied repair events. | Generated from live WDQS in original run; paths in manifest reference `/home/kg_benchmark/...`. Large state file is historical artifact, not a curated candidate pool. | Potential source of frozen bridge triples after extraction and hash audit. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/events.jsonl` and `state.json` | Local files | Stage12 bounded path repair discoveries and applied paths. | Generated from live WDQS. May contain connectivity paths useful for replacement, but not organized as C3 candidate pool. | Potential source after extraction. |
| Live WDQS through `repair_kg_connectivity.py` or `kg_balance_remove_replace.py` | Not frozen | One-hop/two-hop bridge triples queried live. | High endpoint drift risk; results may not reproduce. | Should be disabled for thesis-track C3 unless explicitly marked exploratory. |

Candidate-pool conclusion:

There is no confirmed canonical local replacement pool specifically for B0/C2 bridge-like `P31`/`P279`/`P131` removals. C3 can proceed only after a candidate-pool preparation step that either:

1. extracts and hashes a frozen local replacement pool from Stage11/Stage12 events/state and Trial9 repair candidate files, or
2. explicitly marks live WDQS replacement search as exploratory and non-final.

Recommended thesis-safe route:

Use local frozen files first. Do not use live WDQS for a candidate intended to replace C1 unless the run is clearly labeled exploratory and later frozen with full query/result manifests.

## 4. Recommended C3 Parent

Recommendation: use B0 as the C3 parent.

Parent:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`

Parent SHA256:

`c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`

Reason:

B0 has lower deficit than C1 and C2 (`total_deficit = 2019`) while preserving all relation coverage and weak connectivity. C2 is negative evidence, not a better parent: it removed only 27 target triples and still failed surplus. Starting C3 from C2 would inherit a rejected deletion-only state without a demonstrated benefit over B0.

Human-decision alternative:

If the goal is to test whether replacements can repair exactly the edges C2 could not delete, C2's rejected graph and rejection logs can be used as diagnostic input. That should not make C2 the parent unless a human decision records the reason.

## 5. C3 Objective

Primary objective:

Reduce generic-dominance surplus in `P31`, `P279`, and `P131` more meaningfully than C2 by replacing connectivity-supporting generic edges with less overfilled or deficit-helping edges, while preserving weak connectivity and allocated relation coverage.

Minimum objective:

- `weak_component_count = 1`
- `unique_relations = 139`
- `zero_allocated_relations = 0`
- `total_surplus < 6582`
- `total_deficit <= 2359`

Preferred objective:

- `total_deficit <= 2019`
- combined `P31 + P279 + P131` surplus `< 6166`
- no duplicate triples
- same canonical allocation hash unless explicitly justified

## 6. Proposed Remove-And-Replace Strategy

The C3 generator should be new and isolated:

`tools/graph_candidate_generation/remove_replace_generic_connectivity.py`

It should not modify old scripts.

Proposed algorithm:

1. Load B0 and canonical allocation read-only.
2. Compute relation counts, eta deficits/surpluses, duplicate status, and weak connectivity using the same conventions as the evaluator.
3. Identify candidate generic triples in `P31`, `P279`, and `P131`, prioritizing triples that are bridge-like or were rejected by C2 as `would_disconnect_graph`.
4. For each generic edge, search a frozen local replacement pool for one-hop or two-hop replacement paths that connect the same weak structure if the generic edge is removed.
5. Add the replacement edge or path first in a temporary graph.
6. Verify weak connectivity remains `1`.
7. Remove the generic edge.
8. Recompute eta impact.
9. Reject the swap if it creates a duplicate, loses a relation, creates a zero allocated relation, increases total deficit beyond the allowed limit, or worsens surplus/deficit balance.
10. Record every accepted and rejected swap with reason codes.
11. Write output graph and generation report only under `experiments/graph_candidates/C3_remove_replace_generic_connectivity/`.
12. Run the standard evaluator before any decision.

Replacement ranking:

Prefer replacements that:

- restore or preserve connectivity after removing the generic edge
- use allocated relations that are underfilled or not overfilled
- avoid adding more `P31`, `P279`, or `P131`
- avoid creating new entities unless needed for a two-hop bridge
- are present in frozen local candidate pools with query/result provenance

Reject replacements that:

- require live WDQS in a non-exploratory run
- add duplicate triples
- increase total surplus more than the removed generic edge decreases it
- add triples for already severely overfilled relations
- lose any allocated relation or disconnect the graph

## 7. Guardrails

C3 must enforce:

1. No live WDQS unless the run is explicitly labeled exploratory.
2. No relation loss.
3. `zero_allocated_relations = 0`.
4. `weak_component_count = 1`.
5. No duplicate triples.
6. No output overwrite.
7. Parent graph path/hash recorded.
8. Allocation path/hash recorded.
9. Replacement-pool path/hash recorded.
10. Exact command recorded.
11. Generation report required.
12. Standard evaluator report required.
13. Human accept/reject decision required before registry promotion.

## 8. Acceptance Criteria

Minimum C3:

| Metric | Required value |
| --- | ---: |
| Weak components | 1 |
| Unique relations | 139 |
| Zero allocated relations | 0 |
| Total surplus | `< 6582` |
| Total deficit | `<= 2359` |

Strong C3:

| Metric | Required value |
| --- | ---: |
| Total surplus | `< 6582` |
| Total deficit | `<= 2019` |
| Combined `P31 + P279 + P131` surplus | `< 6166` |

Additional non-negotiable checks:

- duplicate triple count must be 0
- allocated relations observed must be 139
- largest weak component ratio must be 1.0
- graph and allocation hashes must be recorded

## 9. Proposed Operational Paths

Candidate root:

`experiments/graph_candidates/C3_remove_replace_generic_connectivity/`

Future config:

`configs/graph_candidates/C3_remove_replace_generic_connectivity.template.json`

Future generator:

`tools/graph_candidate_generation/remove_replace_generic_connectivity.py`

Future output graph:

`experiments/graph_candidates/C3_remove_replace_generic_connectivity/outputs/graph.jsonl`

Future generation report:

`experiments/graph_candidates/C3_remove_replace_generic_connectivity/reports/generation_report.json`

Future evaluator report:

`experiments/graph_candidates/C3_remove_replace_generic_connectivity/reports/evaluator.report.json`

Future evaluator summary:

`experiments/graph_candidates/C3_remove_replace_generic_connectivity/reports/evaluator.summary.md`

Future decision:

`experiments/graph_candidates/C3_remove_replace_generic_connectivity/decision.md`

## 10. Decision

Recommendation: proceed with C3 planning, but do not execute C3 until blockers are resolved.

Best parent: B0.

Best implementation route:

Create a new isolated C3 generator under `tools/graph_candidate_generation/`. Use C2's operational discipline for hashing, no-overwrite behavior, standard evaluator compatibility, and decision reporting. Use `kg_balance_remove_replace.py` only as design evidence, not as the direct C3 command.

Blockers before implementation:

1. Freeze or define the replacement candidate pool.
2. Decide whether Stage11/Stage12 events/state are acceptable as local replacement sources.
3. Decide whether Trial9 repair candidate files may be used despite allocation and graph mismatch.
4. Define replacement scoring so added triples do not worsen allocation imbalance.
5. Define whether C3 may add new entities.
6. Define whether C3 may add two-hop replacement paths or only one-edge replacements.
7. Record replacement-pool hashes before any C3 generation.
8. Decide whether any live WDQS use is allowed. If yes, label the run exploratory, not final.

Do not call C3 final, accepted, or generated until the output exists, has an evaluator report, and has a human decision.
