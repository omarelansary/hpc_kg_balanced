# C2 Targeted Generic Pruning

Status: planned experiment. C2 does not exist as a generated graph.

This directory is the controlled operational root for the future C2 targeted generic-dominance pruning candidate.

## Purpose

C2 is intended to test whether targeted pruning of generic-dominance surplus can beat C1's surplus while preserving B0/C1 connectivity and relation coverage.

Primary target relations:

- `P31`
- `P279`
- `P131`

Design evidence:

- C2 plan: `docs/reconstruction/11_C2_experiment_plan.md`
- Path amendment: `docs/reconstruction/11_C2_experiment_plan_path_amendment.md`
- Current decision state: `docs/reconstruction/10_current_decision_state.md`

## Required Paths

- Parent graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Parent graph SHA256: `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`
- Allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Allocation SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`
- Config template: `configs/graph_candidates/C2_targeted_generic_pruning.template.json`
- Command template: `experiments/graph_candidates/C2_targeted_generic_pruning/command.template.sh`

## Future Outputs

These files are not present until C2 is explicitly executed:

- Candidate graph: `experiments/graph_candidates/C2_targeted_generic_pruning/outputs/pruned_graph.jsonl`
- Generation report: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json`
- Evaluator report: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`
- Evaluator summary: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.summary.md`

## Operating Rules

1. Do not call this candidate Stage14.
2. Do not append C2 to `docs/reconstruction/graph_candidates.tsv` until the graph, hashes, reports, and decision exist.
3. Do not claim C2 is final.
4. Use B0 as the parent unless a human decision records a different parent.
5. Preserve the canonical allocation hash unless a human decision records a different allocation.
6. Use the duplicate-safe evaluator before any accept/reject decision.

## Acceptance Summary

Minimum C2 must preserve:

- `weak_component_count = 1`
- `largest_weak_component_ratio = 1.0`
- `unique_relations = 139`
- `allocated_relations_observed = 139`
- `zero_allocated_relations = 0`
- `duplicate_triple_count = 0`
- `total_surplus < 6582`
- `total_deficit <= 2359`

Strong C2 should also preserve `total_deficit <= 2019` and reduce combined `P31 + P279 + P131` surplus below `6166`.
