# C1: Stage13 Aggressive But Guarded

Status: `active_candidate_not_final`

Decision: strongest current candidate in the decision docs, not thesis-final.

This directory is a controlled pointer layer. It does not contain a copied graph.

## Graph Pointer

- Path: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl`
- Format: JSONL with `h`, `r`, `t`
- SHA256: `e01d7137c1dbcd790082825a025cade7198a957b3c936f0d9b5b3f0b33780b73`

## Parent Pointer

- Parent candidate ID: `B0`
- Parent graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Parent graph SHA256: `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`

## Allocation Pointer

- Path: `src/Pruning graph/bidirectional_allocation_results5k.json`
- SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

## Generation Evidence

- Stage13 SLURM log: `logs/stage13_prune_revised_29012090.out`
- Stage13 runner: `scripts/slurm/stage13_balance_prune_revised_density_aware.slurm`
- Stage13 report: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.report.json`
- Stage13 summary CSV: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/summary.csv`
- Stage13 summary Markdown: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/summary.md`

## Evaluation Pointer

- Evaluator report: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`
- Evaluator summary: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.summary.md`
- Evaluator script: `tools/graph_candidate_evaluation/evaluate_graph_candidate.py`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Raw rows | 24223 |
| Unique triples | 24223 |
| Duplicate triples | 0 |
| Unique relations | 139 |
| Weak components | 1 |
| Largest weak component ratio | 1.0 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total deficit | 2359 |
| Total surplus | 6582 |

Evidence: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`

## Notes

- C1 is a candidate, not a final thesis graph.
- Existing paths are referenced as provenance and were not moved or copied.
- This pointer layer should remain small and operational.
