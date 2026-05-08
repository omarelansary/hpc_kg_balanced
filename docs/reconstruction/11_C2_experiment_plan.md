# C2 Experiment Plan: Targeted Generic-Dominance Pruning

Status: design only. C2 does not exist yet. No pruning has been run for C2, no C2 graph has been generated, and `docs/reconstruction/graph_candidates.tsv` has not been updated for C2.

This plan uses the current candidate tracking system and duplicate-safe evaluator:

- Evaluator: `tools/graph_candidate_evaluation/evaluate_graph_candidate.py`
- Registry rules: `docs/reconstruction/09_graph_candidate_registry.md`
- Current decision state: `docs/reconstruction/10_current_decision_state.md`
- B0 evaluator report: `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`
- C1 evaluator report: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`
- C1 pruning report: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.report.json`

## 1. Recommended Parent Graph

Recommendation: use `B0` as the parent graph for C2.

Parent graph:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`

Parent graph SHA256:

`c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`

Allocation:

`src/Pruning graph/bidirectional_allocation_results5k.json`

Allocation SHA256:

`a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

Verified facts:

| Metric | B0 | C1 |
| --- | ---: | ---: |
| Raw rows | 24683 | 24223 |
| Unique triples | 24683 | 24223 |
| Duplicate triples | 0 | 0 |
| Unique relations | 139 | 139 |
| Weak components | 1 | 1 |
| Largest weak component ratio | 1.0 | 1.0 |
| Allocated relations observed | 139 | 139 |
| Zero allocated relations | 0 | 0 |
| Total deficit | 2019 | 2359 |
| Total surplus | 6702 | 6582 |

Evidence:

- B0 metrics: `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`
- C1 metrics: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`
- Current comparison summary: `docs/reconstruction/10_current_decision_state.md`

Reason:

C1 improves total surplus by 120 relative to B0, but worsens total deficit by 340. Because C2 is intended to reduce generic-dominance surplus without worsening the eta profile, B0 is the safer parent. Starting from B0 preserves the lower known deficit and gives the experiment a clean target: improve surplus beyond C1 while avoiding C1's deficit increase.

Evidence-based inference:

C1 appears to have spent 460 deletions without substantially reducing the dominant generic relations. Its own pruning report records only 4 removals from `P31` and 2 removals from `P279`, while C1 evaluator metrics still show `P31`, `P279`, and `P131` as the three most overfilled relations.

Evidence:

- C1 pruning report: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.report.json`
- C1 evaluator report: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`

## 2. C2 Objective

Objective:

Generate a controlled candidate that reduces generic-dominance surplus concentrated in `P31`, `P279`, and `P131`, while preserving connectivity, allocated relation coverage, duplicate-free graph content, and the canonical allocation hash.

Exact metric objective:

1. Preserve all hard constraints listed in Section 3.
2. Achieve `total_surplus < 6582`, beating C1 on surplus.
3. Achieve `total_deficit <= 2359`, avoiding a deficit worse than C1.
4. Prefer `total_deficit <= 2019`, preserving B0's lower deficit.
5. Reduce the combined `P31 + P279 + P131` surplus relative to B0.
6. For a strong C2, reduce combined `P31 + P279 + P131` surplus below `6166`.

Combined generic-dominance surplus baseline:

| Relation | B0 expected eta | B0 observed | B0 surplus | C1 observed | C1 surplus |
| --- | ---: | ---: | ---: | ---: | ---: |
| `P31` | 238 | 5957 | 5719 | 5953 | 5715 |
| `P279` | 227 | 750 | 523 | 748 | 521 |
| `P131` | 179 | 353 | 174 | 344 | 165 |
| Combined | 644 | 7060 | 6416 | 7045 | 6401 |

The strong C2 target `6166` is B0 combined generic surplus minus 250. This threshold is intentionally larger than C1's 15-triple reduction in the same three relations.

Evidence:

- B0 relation counts: `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`
- C1 relation counts: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`

## 3. Hard Constraints

C2 must satisfy all of these constraints to be considered valid for comparison:

| Constraint | Required value |
| --- | --- |
| Parent candidate | `B0` unless explicitly overridden by a documented human decision |
| Parent graph SHA256 | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` |
| Allocation path | `src/Pruning graph/bidirectional_allocation_results5k.json` |
| Allocation SHA256 | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` |
| Weak component count | `1` |
| Largest weak component ratio | `1.0` |
| Unique relations | `139` |
| Allocated relations observed | `139` |
| Zero allocated relations | `0` |
| Duplicate triple count | `0` preferred; if nonzero, duplicates must be reported and eta metrics must use unique triples |
| Allocation metric basis | unique triples, not raw graph rows |
| Lost relation IDs | none |
| Output provenance | generation command, input hashes, output hash, evaluator report, and registry row |

Evidence for duplicate-safe allocation evaluation:

- Evaluator implementation: `tools/graph_candidate_evaluation/evaluate_graph_candidate.py`
- Registry policy: `docs/reconstruction/09_graph_candidate_registry.md`
- Current duplicate-safe reports: `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json` and `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`

## 4. Target Relations

Primary target relations:

| Relation | Why targeted | Evidence |
| --- | --- | --- |
| `P31` | Largest overfilled relation by a wide margin in B0 and C1 | `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`; `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json` |
| `P279` | Second-largest generic surplus in B0 and C1 | same reports |
| `P131` | Third-largest generic surplus in B0 and C1 | same reports |

Secondary review-only relations:

| Relation | Reason to consider only after primary targets | Evidence |
| --- | --- | --- |
| `P361` | Top-five overfilled relation in B0 and C1, but surplus is much smaller than the primary targets | B0 and C1 evaluator reports |
| `P1001` | Top-five overfilled relation in C1 | C1 evaluator report |
| `P1889` | Overfilled in B0 and still overfilled in C1 | B0 and C1 evaluator reports |

Recommendation:

C2 should only target `P31`, `P279`, and `P131` in its minimum experiment. Secondary relations should be left unchanged unless the primary-target experiment preserves all hard constraints and still leaves a documented surplus problem that justifies a second pass.

## 5. Proposed Pruning Strategy

Recommendation:

Do not modify existing Stage13 scripts. If C2 is executed later, create a new isolated generator script under:

`tools/graph_candidate_generation/targeted_generic_dominance_prune.py`

This script does not exist yet and must not be treated as part of this task.

Reason:

Stage13 is useful evidence, but its existing revised density-aware runner is not a clean targeted generic-dominance experiment. The runner defaults to `INPUT_GRAPH="${BASE_DIR}/largest_component.csv"`, protects `P31` and `P279`, and sets hard relation minimum counts for `P31=5000` and `P279=650`. The C1 pruning report then shows only 4 removals from `P31` and 2 removals from `P279`, while generic surplus remains dominant.

Evidence:

- Stage13 runner: `scripts/slurm/stage13_balance_prune_revised_density_aware.slurm`
- Stage13 runner settings include `PROTECTED_RELATIONS`, `HARD_RELATION_MIN_COUNTS`, `INPUT_GRAPH`, `PRUNE_DIR`, and post-round connectivity guard arguments.
- Stage13 pruning implementation: `src/Pruning graph/kg_balance_pruner_revised_pruning_only.py`
- C1 pruning report: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.report.json`

Proposed isolated C2 algorithm:

1. Read B0 and the canonical allocation as read-only inputs.
2. Compute unique triples and relation counts using the same duplicate-safe convention as the evaluator.
3. Build deletion candidates only from `P31`, `P279`, and `P131`.
4. Exclude any deletion that would reduce a relation below eta.
5. Exclude any deletion that would remove the final occurrence of an allocated relation.
6. Prefer triples whose endpoints have higher alternate degree or redundant paths.
7. Check weak connectivity after every single deletion or after every accepted mini-batch of size 1.
8. Stop immediately if any hard constraint would be violated.
9. Write a generation report containing input hashes, accepted removals, rejected removals, relation counts before and after, and final evaluator command.
10. Evaluate the output with `tools/graph_candidate_evaluation/evaluate_graph_candidate.py` before adding it to the registry.

Use from Stage13:

- Reuse the idea of hard connectivity guards.
- Reuse the idea of relation floors.
- Reuse the requirement that output reports record objective metrics.

Do not reuse from Stage13 without revision:

- Broad density-aware objective as the primary target.
- Protected `P31` and `P279` defaults.
- Any behavior that allows a candidate to be accepted without the standard graph-candidate evaluator report.

## 6. Guardrails

C2 generation, if later implemented, must enforce these guardrails:

1. Check weak connectivity after every accepted deletion or batch.
2. Use batch size `1` for the first reproducible C2 run unless a larger batch has a rollback proof in the generation report.
3. Never delete a relation below its eta target.
4. Never delete the last observed triple for any allocated relation.
5. Never delete from relations that are currently underfilled.
6. Protect all non-target relations from deletion in the minimum C2 experiment.
7. Avoid increasing total deficit; if any deletion increases total deficit, reject it.
8. Preserve all 139 allocated relation IDs.
9. Preserve `weak_component_count = 1`.
10. Preserve `largest_weak_component_ratio = 1.0`.
11. Require `duplicate_triple_count = 0` in the output, or reject the candidate before registry entry.
12. Record parent graph hash, allocation hash, output graph hash, command, and evaluator report.

## 7. Acceptance Criteria

Minimum C2:

| Metric | Required result |
| --- | --- |
| Weak components | `1` |
| Largest weak component ratio | `1.0` |
| Unique relations | `139` |
| Allocated relations observed | `139` |
| Zero allocated relations | `0` |
| Duplicate triple count | `0` |
| Allocation SHA256 | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` |
| Parent graph SHA256 | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` |
| Total surplus | `< 6582` |
| Total deficit | `<= 2359` |

Strong C2:

| Metric | Required result |
| --- | --- |
| Weak components | `1` |
| Largest weak component ratio | `1.0` |
| Unique relations | `139` |
| Allocated relations observed | `139` |
| Zero allocated relations | `0` |
| Duplicate triple count | `0` |
| Total surplus | `< 6582` |
| Total deficit | `<= 2019` |
| Combined `P31 + P279 + P131` surplus | `< 6166` |
| `P31` observed count | `< 5953` |
| `P279` observed count | `< 748` |
| `P131` observed count | `< 344` |

The strong relation thresholds use C1 counts as the comparator. A strong C2 must improve each primary generic relation relative to C1, not only improve aggregate surplus through unrelated relations.

## 8. Rejection Criteria

Reject C2 if any of the following occurs:

1. The graph becomes disconnected: `weak_component_count != 1`.
2. `largest_weak_component_ratio` falls below `1.0`.
3. Any allocated relation disappears.
4. `zero_allocated_relations > 0`.
5. Unique relation count falls below `139`.
6. `duplicate_triple_count > 0` and the duplicate source is not explained.
7. Total deficit is worse than C1: `total_deficit > 2359`.
8. Total surplus does not beat C1: `total_surplus >= 6582`.
9. Surplus improvement is trivial: combined `P31 + P279 + P131` surplus decreases by fewer than 100 triples relative to B0.
10. The allocation hash differs from B0/C1 without an explicit human decision.
11. Parent graph hash is missing or does not match B0 without an explicit human decision.
12. The generation command, script path, report, or evaluator report is missing.

## 9. Proposed Output Paths If Later Executed

These paths are proposed only. They must not be created until C2 is explicitly authorized for execution.

Future candidate output directory:

`data/connectedgraph/candidates/C2_targeted_generic_dominance/`

Future candidate graph:

`data/connectedgraph/candidates/C2_targeted_generic_dominance/pruned_graph.jsonl`

Future generation report:

`data/connectedgraph/candidates/C2_targeted_generic_dominance/prune_report.json`

Future evaluator report:

`docs/reconstruction/graph_candidate_reports/C2_targeted_generic_dominance.report.json`

Future evaluator summary:

`docs/reconstruction/graph_candidate_reports/C2_targeted_generic_dominance.summary.md`

Future registry row:

Append a `C2` row to `docs/reconstruction/graph_candidates.tsv` only after the graph exists, the evaluator report exists, and SHA256 values are known.

Proposed future row values:

| Column | Planned value |
| --- | --- |
| `candidate_id` | `C2` |
| `label` | `targeted_generic_dominance_from_B0` |
| `graph_path` | `data/connectedgraph/candidates/C2_targeted_generic_dominance/pruned_graph.jsonl` |
| `graph_sha256` | value from future evaluator report |
| `allocation_path` | `src/Pruning graph/bidirectional_allocation_results5k.json` |
| `allocation_sha256` | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` |
| `parent_candidate_id` | `B0` |
| `parent_graph_sha256` | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` |
| `script_or_process` | `tools/graph_candidate_generation/targeted_generic_dominance_prune.py` |
| `objective` | reduce `P31`/`P279`/`P131` surplus while preserving connectivity and eta coverage |
| `created_from_log_or_command` | future command or run manifest |
| `report_path` | `docs/reconstruction/graph_candidate_reports/C2_targeted_generic_dominance.report.json` |
| `status` | `candidate` or `rejected`, based on evaluator output |
| `decision` | human decision after review |
| `notes` | include duplicate count, parent hash, allocation hash, and any rejected guard events |

## 10. Exact Later Execution Command Plan

Do not run these commands as part of this planning task.

Planned generation command, after the isolated generator script is created:

```bash
python tools/graph_candidate_generation/targeted_generic_dominance_prune.py \
  --input-graph 'src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv' \
  --allocation 'src/Pruning graph/bidirectional_allocation_results5k.json' \
  --output-graph 'data/connectedgraph/candidates/C2_targeted_generic_dominance/pruned_graph.jsonl' \
  --output-report 'data/connectedgraph/candidates/C2_targeted_generic_dominance/prune_report.json' \
  --parent-candidate-id B0 \
  --parent-graph-sha256 c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9 \
  --allocation-sha256 a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb \
  --target-relation P31 \
  --target-relation P279 \
  --target-relation P131 \
  --max-removals 600 \
  --batch-size 1 \
  --require-weak-components 1 \
  --require-largest-ratio 1.0 \
  --min-allocated-relations-observed 139 \
  --max-zero-allocated-relations 0 \
  --max-total-deficit 2359 \
  --max-final-surplus 6581 \
  --require-duplicate-count 0
```

Planned evaluation command, after the graph is generated:

```bash
python tools/graph_candidate_evaluation/evaluate_graph_candidate.py \
  --candidate-id C2 \
  --label 'targeted_generic_dominance_from_B0' \
  --graph 'data/connectedgraph/candidates/C2_targeted_generic_dominance/pruned_graph.jsonl' \
  --allocation 'src/Pruning graph/bidirectional_allocation_results5k.json' \
  --output-report docs/reconstruction/graph_candidate_reports/C2_targeted_generic_dominance.report.json
```

Planned registry append command, after hashes and metrics are known:

```bash
printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
  'C2' \
  'targeted_generic_dominance_from_B0' \
  'data/connectedgraph/candidates/C2_targeted_generic_dominance/pruned_graph.jsonl' \
  '<C2_GRAPH_SHA256_FROM_EVALUATOR_REPORT>' \
  'src/Pruning graph/bidirectional_allocation_results5k.json' \
  'a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb' \
  'B0' \
  'c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9' \
  'tools/graph_candidate_generation/targeted_generic_dominance_prune.py' \
  'Reduce P31/P279/P131 surplus while preserving connectivity and eta coverage' \
  '<C2_GENERATION_COMMAND_OR_MANIFEST_PATH>' \
  'docs/reconstruction/graph_candidate_reports/C2_targeted_generic_dominance.report.json' \
  '<candidate_or_rejected>' \
  '<human_decision_after_review>' \
  '<notes_include_duplicate_count_parent_hash_allocation_hash_guard_events>' \
  >> docs/reconstruction/graph_candidates.tsv
```

## 11. Risks

Risk: targeted pruning may fail to remove many triples.

Why it matters:

`P31`, `P279`, and `P131` may provide bridge-like edges for entities that otherwise have low degree. Deleting them under a strict weak-connectivity guard can cause most candidate deletions to be rejected.

Evidence:

- C1 kept weak connectivity but removed only 4 `P31` triples and 2 `P279` triples: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.report.json`
- C1 still has `P31`, `P279`, and `P131` as the top overfilled relations: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`

Risk: relation balance can trade off against connectivity.

Why it matters:

The graph can remain eta-overfilled because deletions that improve relation balance may break weak connectivity. A candidate that aggressively reduces surplus but disconnects the graph is not thesis-safe under the current acceptance criteria.

Evidence:

- Stage13 runner includes post-round weak-component and largest-component guard settings: `scripts/slurm/stage13_balance_prune_revised_density_aware.slurm`
- Stage13 pruning implementation includes hard preserve largest-component behavior and post-round guard checks: `src/Pruning graph/kg_balance_pruner_revised_pruning_only.py`

Risk: P31 removal can isolate entities.

Why it matters:

`P31` is extremely frequent in B0 and C1. Many entities may be connected to the graph through instance-of structure. Removing `P31` without local degree or alternate-path checks could create isolated or weakly connected fragments.

Evidence:

- B0 `P31`: expected 238, observed 5957, surplus 5719: `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`
- C1 `P31`: expected 238, observed 5953, surplus 5715: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`

Risk: a plain deletion-only strategy can preserve connectivity but fail the objective.

Why it matters:

If connectivity-safe deletions are rare, C2 may preserve all hard constraints but fail to beat C1's surplus. That result should be recorded as a rejected or exploratory candidate, not renamed as a new stage.

Evidence:

- Candidate naming and promotion rules: `docs/reconstruction/09_graph_candidate_registry.md`

Risk: provenance gaps would make C2 unusable even if the metrics improve.

Why it matters:

The thesis needs a defensible chain from parent graph and allocation to output graph and evaluator report. Without a command, script path, hashes, and report, a later output would repeat the ambiguity that the reconstruction is trying to eliminate.

Evidence:

- Registry required columns: `docs/reconstruction/graph_candidates.tsv`
- Promotion rules: `docs/reconstruction/09_graph_candidate_registry.md`

## 12. Final Recommendation

Recommendation: proceed with C2 design, but do not generate C2 until an isolated generator script and run command are reviewed.

Best parent graph: `B0`.

Reason:

B0 has the same relation coverage, connectivity, zero allocated relation count, duplicate count, and allocation hash as C1, but a lower total deficit. C1 reduces total surplus only slightly and leaves the dominant generic relation surplus almost unchanged.

Safest implementation route:

1. Create a new isolated script later under `tools/graph_candidate_generation/targeted_generic_dominance_prune.py`.
2. Start from B0.
3. Restrict the minimum C2 experiment to `P31`, `P279`, and `P131`.
4. Use single-deletion acceptance with immediate weak-connectivity and eta checks.
5. Evaluate with `tools/graph_candidate_evaluation/evaluate_graph_candidate.py`.
6. Register C2 only after the graph, hashes, generation report, evaluator report, and human decision exist.

Human decision before execution:

The thesis author must decide whether a deletion-only C2 is sufficient, or whether a future candidate should use remove-and-replace logic. The existing `src/Pruning graph/kg_balance_remove_replace.py` shows a separate remove-and-replace direction, but this plan does not claim that it has been executed for B0 or C1.

