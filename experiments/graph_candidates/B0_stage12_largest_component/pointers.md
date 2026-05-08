# B0: Stage12 Largest Component

Status: `frozen_baseline`

Decision: baseline for comparison, not thesis-final by itself.

This directory is a controlled pointer layer. It does not contain a copied graph.

## Graph Pointer

- Path: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Format: CSV with `h,r,t`
- SHA256: `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`

## Allocation Pointer

- Path: `src/Pruning graph/bidirectional_allocation_results5k.json`
- SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

## Evaluation Pointer

- Evaluator report: `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`
- Evaluator summary: `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.summary.md`
- Evaluator script: `tools/graph_candidate_evaluation/evaluate_graph_candidate.py`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Raw rows | 24683 |
| Unique triples | 24683 |
| Duplicate triples | 0 |
| Unique relations | 139 |
| Weak components | 1 |
| Largest weak component ratio | 1.0 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total deficit | 2019 |
| Total surplus | 6702 |

Evidence: `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`

## Notes

- Parent candidate: none. `B0` is the frozen baseline in the candidate registry.
- Existing paths are referenced as provenance and were not moved or copied.
- This pointer layer should remain small and operational.
