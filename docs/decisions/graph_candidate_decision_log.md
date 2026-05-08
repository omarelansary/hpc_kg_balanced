# Graph Candidate Decision Log

This log records human-facing graph-candidate decisions from the controlled operational layer. It references existing artifacts as provenance and does not move or copy graph files.

Operational root:

`experiments/graph_candidates/`

Registry:

`docs/reconstruction/graph_candidates.tsv`

## Decision Rules

1. A candidate is not final until a human decision records that status.
2. A later experiment is not a new stage unless it has a reproducible process, input hashes, output hashes, reports, and a decision.
3. C2 and later candidates should live under `experiments/graph_candidates/`.
4. Historical artifacts under `data/connectedgraph/` and `src/Pruning graph/` should be referenced, not moved.
5. `docs/reconstruction/graph_candidates.tsv` should be updated only after a candidate output, evaluator report, and decision exist.

## Current Decisions

| Date | Candidate | Status | Decision | Evidence | Notes |
| --- | --- | --- | --- | --- | --- |
| 2026-05-07 | `B0` | `frozen_baseline` | Use as comparison baseline, not final | `experiments/graph_candidates/B0_stage12_largest_component/manifest.json`; `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json` | Pointer-only operational entry. |
| 2026-05-07 | `C1` | `active_candidate_not_final` | Treat as current active candidate, not final | `experiments/graph_candidates/C1_stage13_aggressive/manifest.json`; `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json` | Preserves connectivity and relation coverage, but worsens deficit relative to B0. |
| 2026-05-07 | `C2` | `planned_not_generated` | Design only; no generated graph exists | `experiments/graph_candidates/C2_targeted_generic_pruning/manifest.template.json`; `docs/reconstruction/11_C2_experiment_plan.md`; `docs/reconstruction/11_C2_experiment_plan_path_amendment.md` | Superseded by the generated C2 decision entry below; retained as historical planning record. |
| 2026-05-07 | `C2` | `generated_failed_minimum_thresholds` | Rejected as final, kept as exploratory evidence | `experiments/graph_candidates/C2_targeted_generic_pruning/decision.md`; `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json`; `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`; `docs/reconstruction/12_C2_result_interpretation.md` | Deletion-only targeted generic pruning preserved connectivity and relation coverage, but failed surplus threshold and hit 75893 `would_disconnect_graph` rejections. |
| 2026-05-08 | `C3_probe_v1` | `feasibility_probe_only` | `full_bridge_rescue_not_recommended_with_eligible_pool_v1` | `tools/graph_candidate_generation/probe_c3_remove_replace_feasibility.py`; `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_report.json`; `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_summary.md`; `docs/reconstruction/17_C3_feasibility_probe_result.md` | 0 of 473 connectivity-critical bridge-like target edges had feasible replacement. No graph candidate was generated; do not add a graph-candidate registry row. |

| 2026-05-08 | `B0` | `selected_final_graph` | `selected_final_graph` | `artifacts/final_graph/selected_final_graph/final_graph_manifest.json`; `artifacts/final_graph/selected_final_graph/final_graph_metrics.json`; `artifacts/final_graph/selected_final_graph/final_graph_decision.md`; `docs/reconstruction/19_final_graph_selection_decision.md` | Final human decision selected B0; no graph artifact was modified and the graph file was not copied. |

## Future Decision Entry Template

| Date | Candidate | Status | Decision | Evidence | Notes |
| --- | --- | --- | --- | --- | --- |
| `<YYYY-MM-DD>` | `<candidate_id>` | `<status>` | `<accept / reject / promote / keep active>` | `<manifest path>; <evaluator report path>; <generation report path>` | `<short rationale and unresolved concerns>` |
