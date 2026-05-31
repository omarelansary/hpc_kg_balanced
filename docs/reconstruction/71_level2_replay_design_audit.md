# Level 2 Replay Design Audit

This audit evaluates whether the reusable pipeline runner can replay historical B0/C1 graph generation from frozen/local inputs. It does not implement replay, run graph construction, submit SLURM jobs, query WDQS, or call LLMs.

## Result

B0/C1 regeneration is not safe through the runner today. Level 1 frozen packaging is safe: existing registered candidate artifacts can be verified, copied into `outputs/pipeline_runs/<run_id>/candidates/<candidate_id>/`, and evaluated without modifying the historical graph artifacts.

The first safe Level 2 boundary is a Phase I read-only/run-scoped replay wrapper: materialize allocation and genericity matrix exports under `outputs/pipeline_runs/<run_id>/phase1_replay/`, then compare them to the frozen canonical artifacts. Do not overwrite `src/Pruning graph/bidirectional_allocation_results5k.json` or `archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json`.

## Classification Summary

| Stage | Classification | Main Risk | Required Wrapper |
| --- | --- | --- | --- |
| `phase1_symmetry_inverse_evidence` | `safe_replay_now` | none | none for validation; use a future run-scoped export wrapper only if materialized evidence tables are needed |
| `phase1_allocation_export` | `needs_read_only_wrapper` | high_if_enabled_as_export_to_manifest_output | write regenerated allocation to outputs/pipeline_runs/<run_id>/phase1_replay/ and compare to canonical hash a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb; never overwrite src/Pruning graph/bidirectional_allocation_results5k.json |
| `phase1_support_genericity_matrix_export` | `needs_read_only_wrapper` | high_if_enabled_as_export_to_manifest_output | write regenerated genericity matrix to outputs/pipeline_runs/<run_id>/phase1_replay/ and compare relation set/content against the frozen canonical matrix; never overwrite archive input matrix |
| `phase2_stage1_genericity_scoring` | `needs_run_directory_wrapper` | medium_to_high_if_historical_run_dir_is_reused | correct the command to the historical subcommand score-genericity with --config and a fresh --run-dir under outputs/pipeline_runs/<run_id>/level2_replay/; verify inputs and compare output summaries to frozen historical evidence |
| `phase2_stage3_candidate_audit` | `needs_run_directory_wrapper` | high_if_historical_run_dir_is_reused | copy or reference frozen Stage2 candidate shards into a fresh run directory, call audit-candidates with --config/--run-dir, and write only run-scoped Stage3 outputs |
| `phase2_stage4_core_graph_construction` | `needs_run_directory_wrapper` | high | fresh run directory wrapper with frozen Stage2/Stage3 inputs, explicit no-live policy, and output hash/report comparison; never target prod_refine_20260315_180520 |
| `phase2_stage5_repair` | `needs_run_directory_wrapper` | high | fresh run directory wrapper that consumes run-scoped Stage4 output and frozen candidate shards; compare repair summary to historical evidence |
| `phase2_stage6_refinement` | `needs_run_directory_wrapper` | high | fresh run directory wrapper and manifest correction: historical code writes stage06_refine_graph, while the current manifest names stage06_refinement |
| `phase2_stage7_eta_aware_replacement` | `needs_run_directory_wrapper` | high_if_out_dir_targets_historical_run | call eta_aware_component_filter.py with explicit --run_dir pointing at a fresh replay run and explicit --out_dir under outputs/pipeline_runs/<run_id>/level2_replay/; do not use --force except inside disposable run dirs |
| `phase2_stage11_connectivity_repair` | `driftable_not_replayable` | very_high | run-specific output_dir wrapper plus an audited frozen-local candidate source mode that prevents WDQS queries; record manifest/state/events and compare output hash to 73bc624bf9147b0bba4962ab286648bcfeeb931a94a1d1a727839f160b35ada5 |
| `phase2_stage12_path_repair` | `driftable_not_replayable` | very_high | same as Stage11: fresh output_dir, no-live frozen-local candidate policy, strict input hash check on Stage11 output, and output comparison to 89ec9bf9c8932962fd3d966073b51f76345666eda5ed5d9beb18659d02e294b0 |
| `phase2_B0_largest_component_extraction` | `needs_read_only_wrapper` | high_for_actual_extraction; low_to_medium_for_current_audit_without_force | separate validation from extraction: keep 01_audit_B0_final_graph.sh as frozen audit, and if extraction is needed create a run-scoped largest-component extractor that writes under outputs/pipeline_runs/<run_id>/ and compares hash c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9 |
| `phase2_C1_stage13_pruning_candidate` | `needs_slurm_wrapper` | medium_for_timestamped_sweep_dirs; high_without_explicit_output_root_policy | SLURM-aware wrapper with run-specific SWEEP_DIR under outputs/pipeline_runs/<run_id>/, submitted job IDs, dependency tracking, resume/status support, and no writes into historical graph directories by default |

## Direct Answers

1. Deterministic replay stages that can be enabled safely first:
   `phase1_symmetry_inverse_evidence` can run now as a read-only golden-master validation. `phase1_allocation_export` and `phase1_support_genericity_matrix_export` should be next, but only after wrappers write run-scoped outputs and compare to frozen canonical artifacts.

2. Graph construction stages that are dangerous because they write to historical artifact paths:
   `phase2_stage4_core_graph_construction`, `phase2_stage5_repair`, `phase2_stage6_refinement`, `phase2_stage7_eta_aware_replacement`, `phase2_stage11_connectivity_repair`, `phase2_stage12_path_repair`, actual `phase2_B0_largest_component_extraction`, and `phase2_C1_stage13_pruning_candidate`.

3. Stages that need run-specific output directories before replay:
   all materialized Phase I exports and all Phase II replay stages except the read-only `phase1_symmetry_inverse_evidence` check.

4. Stages that need SLURM job-state tracking before replay:
   `phase2_C1_stage13_pruning_candidate`. It submits `sbatch` jobs and creates dependent summary jobs.

5. Stages that must remain frozen-only for now:
   Stage11 and Stage12 connectivity/path repair because the current script can query WDQS; C1 Stage13 because it requires SLURM orchestration; Stage4 through Stage7 graph construction until run-directory wrappers exist.

6. Can B0 be regenerated safely today through the runner?
   No. The current runner can validate and package frozen B0, but it should not regenerate B0 from historical construction stages yet.

7. Can B0/C1 be packaged safely today through the runner?
   Yes. Level 1 `construct-candidates --from-frozen` is the safe path because it verifies frozen registered candidate hashes, copies artifacts to the run directory, and evaluates the copied graph.

8. First Level 2 implementation boundary:
   Phase I replay/export wrapper only. It should consume frozen hop support and compact composition artifacts, write regenerated allocation/matrix outputs under the pipeline run directory, and compare to canonical frozen artifacts. It should not touch historical graph/data artifacts.

## Stage Assessments

### `phase1_symmetry_inverse_evidence`

- Classification: `safe_replay_now`
- Current command: `["python", "scripts/reconstruction/check_phase1_dashboard_extraction.py"]`
- Inputs: `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl`
- Outputs: none
- Output path scope: none_read_only_check
- Overwrite risk: none
- Runtime risk: low
- Dependency risk: low_local_python_only
- Can run without WDQS/LLM/SLURM: `true`
- Can run without modifying historical artifacts: `true`
- Required wrapper before enabling: none for validation; use a future run-scoped export wrapper only if materialized evidence tables are needed
- Recommended Level 2 status: enable_first_as_read_only_golden_master_validation
- Evidence: configs/pipeline/kg_pipeline.default.json: phase1_symmetry_inverse_evidence; scripts/reconstruction/check_phase1_dashboard_extraction.py validates frozen Phase I counts without Streamlit, WDQS, or LLM calls
- Note: This is not a materializing replay of dashboard exports; it is a deterministic check over frozen Phase I inputs.
### `phase1_allocation_export`

- Classification: `needs_read_only_wrapper`
- Current command: `["python", "scripts/reconstruction/check_phase1_dashboard_extraction.py"]`
- Inputs: `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl`, `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl`
- Outputs: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Output path scope: historical_global_canonical_artifact
- Overwrite risk: high_if_enabled_as_export_to_manifest_output
- Runtime risk: low
- Dependency risk: low_local_python_only
- Can run without WDQS/LLM/SLURM: `true`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: write regenerated allocation to outputs/pipeline_runs/<run_id>/phase1_replay/ and compare to canonical hash a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb; never overwrite src/Pruning graph/bidirectional_allocation_results5k.json
- Recommended Level 2 status: next_safe_boundary_after_phase1_validation
- Evidence: configs/pipeline/kg_pipeline.default.json: phase1_allocation_export expected_hashes; docs/reconstruction/46_phase1_extraction_implementation.md; scripts/reconstruction/check_phase1_dashboard_extraction.py golden-master allocation comparison
- Note: The extracted Phase I modules make this plausible, but the manifest output is the canonical allocation artifact and must remain frozen.
### `phase1_support_genericity_matrix_export`

- Classification: `needs_read_only_wrapper`
- Current command: `["python", "scripts/reconstruction/check_phase1_dashboard_extraction.py"]`
- Inputs: `archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json`
- Outputs: `archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json`
- Output path scope: historical_global_canonical_artifact
- Overwrite risk: high_if_enabled_as_export_to_manifest_output
- Runtime risk: low
- Dependency risk: low_local_python_only
- Can run without WDQS/LLM/SLURM: `true`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: write regenerated genericity matrix to outputs/pipeline_runs/<run_id>/phase1_replay/ and compare relation set/content against the frozen canonical matrix; never overwrite archive input matrix
- Recommended Level 2 status: next_safe_boundary_after_phase1_validation
- Evidence: configs/pipeline/kg_pipeline.default.json: phase1_support_genericity_matrix_export; scripts/reconstruction/check_phase1_dashboard_extraction.py verifies genericity matrix relation set
- Note: Current manifest input and output are the same historical path, so direct replay is unsafe.
### `phase2_stage1_genericity_scoring`

- Classification: `needs_run_directory_wrapper`
- Current command: `["python", "archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py", "--stage", "stage1"]`
- Inputs: `archive/hetzner_version/src/kg_builder/input/`
- Outputs: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage01_genericity/`
- Output path scope: historical_global_run_directory
- Overwrite risk: medium_to_high_if_historical_run_dir_is_reused
- Runtime risk: medium
- Dependency risk: medium_config_and_run_context_required
- Can run without WDQS/LLM/SLURM: `true`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: correct the command to the historical subcommand score-genericity with --config and a fresh --run-dir under outputs/pipeline_runs/<run_id>/level2_replay/; verify inputs and compare output summaries to frozen historical evidence
- Recommended Level 2 status: do_not_enable_until_run_scoped_wrapper_exists
- Evidence: archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py parse_args defines subcommands, not --stage; RunContext.create refuses existing run directories; ensure_stage_can_write_once guards stage outputs inside a run directory
- Note: The manifest command is not the actual CLI shape; a wrapper must translate manifest stage IDs to historical subcommands.
### `phase2_stage3_candidate_audit`

- Classification: `needs_run_directory_wrapper`
- Current command: `["python", "archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py", "--stage", "stage3"]`
- Inputs: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards/`
- Outputs: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage03_candidate_audit/`
- Output path scope: historical_global_run_directory
- Overwrite risk: high_if_historical_run_dir_is_reused
- Runtime risk: medium
- Dependency risk: medium_requires_frozen_stage02_shards_and_pipeline_config
- Can run without WDQS/LLM/SLURM: `true`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: copy or reference frozen Stage2 candidate shards into a fresh run directory, call audit-candidates with --config/--run-dir, and write only run-scoped Stage3 outputs
- Recommended Level 2 status: enable_after_stage1_wrapper_or_as_stage3_only_replay_from_frozen_stage2_shards
- Evidence: archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py stage_audit_candidates reads stage02_candidates/shards inside ctx.run_dir; Stage2 candidate collection is WDQS-backed and outside safe Level 2 replay
- Note: Stage3 itself is local over frozen shards, but it assumes a run directory layout.
### `phase2_stage4_core_graph_construction`

- Classification: `needs_run_directory_wrapper`
- Current command: `["python", "archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py", "--stage", "stage4"]`
- Inputs: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage03_candidate_audit/`
- Outputs: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/`
- Output path scope: historical_global_run_directory
- Overwrite risk: high
- Runtime risk: medium_to_high
- Dependency risk: medium_requires_stage02_shards_stage03_audit_config_and_allocation
- Can run without WDQS/LLM/SLURM: `true`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: fresh run directory wrapper with frozen Stage2/Stage3 inputs, explicit no-live policy, and output hash/report comparison; never target prod_refine_20260315_180520
- Recommended Level 2 status: blocked_until_run_scoped_graph_construction_wrapper_exists
- Evidence: archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py stage_construct_graph writes stage04_core_graph/core_graph_triples.jsonl; configs/pipeline/kg_pipeline.default.json marks graph construction stages never_by_default
- Note: This is graph generation and should remain disabled until wrapper isolation and validation are in place.
### `phase2_stage5_repair`

- Classification: `needs_run_directory_wrapper`
- Current command: `["python", "archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py", "--stage", "stage5"]`
- Inputs: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/`
- Outputs: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage05_repair/`
- Output path scope: historical_global_run_directory
- Overwrite risk: high
- Runtime risk: medium_to_high
- Dependency risk: medium_requires_stage04_and_frozen_candidate_shards
- Can run without WDQS/LLM/SLURM: `true`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: fresh run directory wrapper that consumes run-scoped Stage4 output and frozen candidate shards; compare repair summary to historical evidence
- Recommended Level 2 status: blocked_until_stage4_wrapper_exists
- Evidence: archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py stage_repair_graph writes stage05_repair/repair_triples.jsonl
- Note: Safe replay depends on a fully run-scoped upstream graph construction replay.
### `phase2_stage6_refinement`

- Classification: `needs_run_directory_wrapper`
- Current command: `["python", "archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py", "--stage", "stage6"]`
- Inputs: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage05_repair/`
- Outputs: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refinement/`
- Output path scope: historical_global_run_directory
- Overwrite risk: high
- Runtime risk: medium_to_high
- Dependency risk: medium_requires_stage04_stage05_and_candidate_shards
- Can run without WDQS/LLM/SLURM: `true`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: fresh run directory wrapper and manifest correction: historical code writes stage06_refine_graph, while the current manifest names stage06_refinement
- Recommended Level 2 status: blocked_until_stage4_stage5_wrappers_exist_and_manifest_stage_name_is_corrected
- Evidence: archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py stage_refine_graph uses stage06_refine_graph/refined_graph_triples.jsonl; archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py also expects stage06_refine_graph
- Note: There is a manifest/code stage-name mismatch that must be resolved before replay orchestration.
### `phase2_stage7_eta_aware_replacement`

- Classification: `needs_run_directory_wrapper`
- Current command: `["python", "archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py"]`
- Inputs: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refinement/`
- Outputs: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_eta_aware/`
- Output path scope: historical_global_run_directory
- Overwrite risk: high_if_out_dir_targets_historical_run
- Runtime risk: medium
- Dependency risk: medium_requires_run_dir_manifest_allocation_and_prefilter_graph
- Can run without WDQS/LLM/SLURM: `true`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: call eta_aware_component_filter.py with explicit --run_dir pointing at a fresh replay run and explicit --out_dir under outputs/pipeline_runs/<run_id>/level2_replay/; do not use --force except inside disposable run dirs
- Recommended Level 2 status: enable_after_stage6_run_scoped_replay_or_as_standalone_from_frozen_prefilter_copy
- Evidence: archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py requires --run_dir and supports --out_dir; prepare_output_dir refuses non-empty output unless --force
- Note: This script is closer to wrapper-ready than Stage11/12 because it already supports explicit output directories and does not need live WDQS.
### `phase2_stage11_connectivity_repair`

- Classification: `driftable_not_replayable`
- Current command: `["python", "src/kg_building/repair_kg_connectivity.py"]`
- Inputs: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/`
- Outputs: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl`
- Output path scope: historical_global_graph_artifact
- Overwrite risk: very_high
- Runtime risk: high
- Dependency risk: high_live_wdqs_possible_and_run_state_required
- Can run without WDQS/LLM/SLURM: `false`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: run-specific output_dir wrapper plus an audited frozen-local candidate source mode that prevents WDQS queries; record manifest/state/events and compare output hash to 73bc624bf9147b0bba4962ab286648bcfeeb931a94a1d1a727839f160b35ada5
- Recommended Level 2 status: frozen_only_until_no_live_query_wrapper_exists
- Evidence: src/kg_building/repair_kg_connectivity.py defines SPARQL_ENDPOINT and WDQS query helpers; repair_kg_connectivity.py requires --output_dir and manages run manifest/state/events; artifact bundle manifest treats Stage11 graph_output.jsonl as external frozen evidence
- Note: The existing script can write to a fresh output_dir, but its candidate acquisition can be live and driftable; that blocks safe replay today.
### `phase2_stage12_path_repair`

- Classification: `driftable_not_replayable`
- Current command: `["python", "src/kg_building/repair_kg_connectivity.py"]`
- Inputs: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl`
- Outputs: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/graph_output.jsonl`
- Output path scope: historical_global_graph_artifact
- Overwrite risk: very_high
- Runtime risk: high
- Dependency risk: high_live_wdqs_possible_and_stage11_dependency_required
- Can run without WDQS/LLM/SLURM: `false`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: same as Stage11: fresh output_dir, no-live frozen-local candidate policy, strict input hash check on Stage11 output, and output comparison to 89ec9bf9c8932962fd3d966073b51f76345666eda5ed5d9beb18659d02e294b0
- Recommended Level 2 status: frozen_only_until_no_live_query_wrapper_exists
- Evidence: src/kg_building/repair_kg_connectivity.py WDQS query helpers; artifact bundle manifest treats Stage12 graph_output.jsonl as external frozen evidence
- Note: Stage12 is downstream of Stage11 and shares the same live-query and historical-output risks.
### `phase2_B0_largest_component_extraction`

- Classification: `needs_read_only_wrapper`
- Current command: `["bash", "scripts/reconstruction/01_audit_B0_final_graph.sh"]`
- Inputs: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/graph_output.jsonl`
- Outputs: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Output path scope: historical_global_graph_artifact_in_manifest; actual script writes rebuild audit reports
- Overwrite risk: high_for_actual_extraction; low_to_medium_for_current_audit_without_force
- Runtime risk: low_for_audit_only; medium_for_actual_extraction
- Dependency risk: low_local_files_only_for_current_audit
- Can run without WDQS/LLM/SLURM: `true`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: separate validation from extraction: keep 01_audit_B0_final_graph.sh as frozen audit, and if extraction is needed create a run-scoped largest-component extractor that writes under outputs/pipeline_runs/<run_id>/ and compares hash c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9
- Recommended Level 2 status: validate_only_now; actual extraction_not_enabled
- Evidence: scripts/reconstruction/01_audit_B0_final_graph.sh performs B0 re-audit and writes rebuild report/summary with overwrite checks; configs/pipeline/kg_pipeline.default.json labels this as largest-component extraction but command points to audit wrapper
- Note: The manifest stage label and command semantics are not aligned; today this is an audit, not a safe extraction replay.
### `phase2_C1_stage13_pruning_candidate`

- Classification: `needs_slurm_wrapper`
- Current command: `["bash", "scripts/run_stage13_branch_sweep.sh"]`
- Inputs: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`
- Outputs: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`
- Output path scope: historical_or_timestamped_global_graph_directory
- Overwrite risk: medium_for_timestamped_sweep_dirs; high_without_explicit_output_root_policy
- Runtime risk: high_expensive_batch_sweep
- Dependency risk: high_requires_slurm_and_downstream_summary_jobs
- Can run without WDQS/LLM/SLURM: `false`
- Can run without modifying historical artifacts: `false`
- Required wrapper before enabling: SLURM-aware wrapper with run-specific SWEEP_DIR under outputs/pipeline_runs/<run_id>/, submitted job IDs, dependency tracking, resume/status support, and no writes into historical graph directories by default
- Recommended Level 2 status: frozen_only_until_slurm_job_state_wrapper_exists
- Evidence: scripts/run_stage13_branch_sweep.sh submits sbatch jobs and writes SWEEP_DIR under the Stage12 graph tree by default; configs/pipeline/kg_pipeline.default.json marks graph construction never_by_default
- Note: C1 can be packaged in Level 1 from frozen artifacts, but replaying its pruning branch is not safe in the current runner.


## Implementation Sequence

1. Add a Phase I replay/export wrapper that writes allocation and genericity matrix artifacts under the pipeline run directory and compares them to canonical hashes/sets.
2. Correct manifest-to-historical-command translation for `relation_balanced_kg_pipeline.py` subcommands and create a dry-run/read-only validation wrapper for Stage1 and Stage3 layouts.
3. Add run-scoped wrappers for Stage4 through Stage7 graph construction only after Stage1/Stage3 replay is stable.
4. Treat Stage11 and Stage12 separately because `repair_kg_connectivity.py` can query WDQS and needs an audited frozen-local source mode before replay.
5. Treat C1 Stage13 separately because it requires SLURM job-state tracking and run-scoped sweep directories.

## Guardrails

- Do not enable Level 2 graph construction against historical run directories.
- Do not use the current manifest `--stage` commands for `relation_balanced_kg_pipeline.py`; that script uses subcommands and config/run-dir arguments.
- Do not treat `scripts/reconstruction/01_audit_B0_final_graph.sh` as actual largest-component extraction; it is an audit wrapper.
- Do not replay Stage11/Stage12 until live WDQS access is impossible by construction.
- Do not replay C1 Stage13 until SLURM job state and run-scoped output roots are managed by the runner.
