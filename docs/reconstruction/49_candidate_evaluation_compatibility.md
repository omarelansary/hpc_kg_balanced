# Phase II-A.1 Candidate Evaluation Compatibility

This check compares the reusable candidate evaluation foundation in `src/kg_pipeline/evaluation/` against historical candidate reports. It is read-only: it evaluates existing graph files, reads existing reports, writes no files by default, and does not replace `tools/graph_candidate_evaluation/evaluate_graph_candidate.py`.

## Compatibility Script

Script:

`scripts/reconstruction/check_candidate_evaluation_compatibility.py`

The script imports:

`from src.kg_pipeline.evaluation.candidate_report import evaluate_candidate`

It compares reusable-evaluator output against historical reports for candidate artifacts that are present locally.

## Candidates Compared

| Candidate | Graph | Historical report | Result |
| --- | --- | --- | --- |
| `B0_reaudit` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` | `artifacts/final_graph/selected_final_graph/rebuild/B0_reaudit.report.json` | matched |
| `B0_registry_report` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` | `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json` | matched |
| `C1_stage13_aggressive` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl` | `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json` | matched |
| `C2_targeted_generic_pruning` | `experiments/graph_candidates/C2_targeted_generic_pruning/outputs/pruned_graph.jsonl` | `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json` | matched |
| `strict_balance_pruned_ablation` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_ablation_20260322_215639/pruned_graph.jsonl` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_ablation_20260322_215639/pruned_graph.report.json` | schema_only_difference |

No optional candidate was skipped in the current local workspace.

## Compared Metrics

For standard evaluator reports, the compatibility script compares:

- total / unique triples;
- unique entities;
- unique relations;
- weak component count;
- largest weak component ratio;
- duplicate triple count;
- allocated relations observed;
- zero allocated relations;
- total surplus;
- total deficit;
- evaluator-compatible pattern-level observed totals.

For the strict balance-pruned ablation, the historical report is a pruning report with `final_snapshot` fields, not a standard evaluator report. The script compares only same-definition fields:

- total triples;
- unique entities;
- unique relations;
- weak component count;
- largest component ratio.

The strict ablation is classified as `schema_only_difference` because its report contains raw `pattern_counts` and does not expose standard evaluator `total_surplus` / `total_deficit` fields. Those raw pattern counts are not directly comparable to the reusable evaluator's eta-apportioned pattern totals.

## Current Result

Latest observed output:

```text
candidate	status	comparable_metrics	notes
B0_reaudit	matched	15
B0_registry_report	matched	15
C1_stage13_aggressive	matched	15
C2_targeted_generic_pruning	matched	15
strict_balance_pruned_ablation	schema_only_difference	5	historical pruner report has raw pattern_counts, not evaluator eta-apportioned pattern totals; historical pruner report does not expose the standard evaluator total_surplus/total_deficit fields
```

The script exits nonzero only on `real_metric_mismatch`. Missing optional candidates are reported as `skipped_missing_artifact` and do not fail the check. `B0_reaudit` is required and must match exactly.

## Boundary

This compatibility check does not:

- generate graphs;
- modify graph/data artifacts;
- query WDQS;
- call LLMs;
- replace the historical standalone evaluator;
- prove that historical pruning reports use the same schema as standard evaluator reports.

The result supports using the reusable evaluator helpers for future candidate comparison while keeping the historical standalone evaluator unchanged until a later migration step.

