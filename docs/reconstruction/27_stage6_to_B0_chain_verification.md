# Stage6 to B0 Chain Verification

## Conclusion

Wrapper: `scripts/reconstruction/05_verify_stage6_to_B0_chain.sh`

Generated JSON: `artifacts/final_graph/selected_final_graph/rebuild/stage6_to_B0_chain_verification.json`

Overall result: **True**

This verifies the local frozen evidence chain from the Hetzner Stage6 refined graph through Stage7 eta-aware filtering, Stage11 repair, Stage12 path repair, and the selected B0 largest component. It does not prove Stage1-to-Stage6 provenance or full Phase I end-to-end reproducibility.

## Verified Chain

```text
archive/hetzner_version/.../stage06_refine_graph/refined_graph_triples.jsonl
  -> archive/hetzner_version/.../stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl
  -> src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl
  -> src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/graph_output.jsonl
  -> src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv
```

## Verification Checks

| Check | Result |
|---|---:|
| `B0_subset_of_stage12_graph_output` | `True` |
| `B0_unique_triples_24683` | `True` |
| `path_translation_status_resolved_strong` | `True` |
| `stage11_added_core_unique_triples_6705` | `True` |
| `stage11_graph_output_unique_triples_24670` | `True` |
| `stage11_output_minus_stage7_equals_added_core` | `True` |
| `stage11_subset_of_stage12_graph_output` | `True` |
| `stage12_added_path_unique_triples_45` | `True` |
| `stage12_graph_output_matches_report_expected_unique_triples` | `True` |
| `stage12_graph_output_unique_triples_24715` | `True` |
| `stage12_output_minus_stage11_equals_added_path_triples` | `True` |
| `stage6_graph_exists` | `True` |
| `stage6_has_h_r_t_like_fields` | `True` |
| `stage6_minus_stage7_unique_triples_548` | `True` |
| `stage6_row_count_18513` | `True` |
| `stage6_unique_triples_18513` | `True` |
| `stage7_log_supports_transition` | `True` |
| `stage7_progress_kept_triples_17965` | `True` |
| `stage7_progress_removed_triples_548` | `True` |
| `stage7_subset_of_stage11_graph_output` | `True` |
| `stage7_subset_of_stage6` | `True` |
| `stage7_summary_input_triples_18513` | `True` |
| `stage7_summary_kept_triples_17965` | `True` |
| `stage7_summary_prefilter_source_stage06` | `True` |
| `stage7_summary_removed_triples_548` | `True` |
| `stage7_to_B0_previous_verification_passed` | `True` |
| `stage7_unique_triples_17965` | `True` |

## Key Metrics

| Artifact | Unique triples | Unique relations | Notes |
|---|---:|---:|---|
| Stage6 refined graph | 18513 | 139 | Source graph consumed by Stage7 according to Stage7 summary/log evidence |
| Stage7 filtered graph | 17965 | 139 | Stage6 minus 548 filtered triples |
| Stage11 graph output | 24670 | 139 | Stage7 plus 6705 recorded core repair triples |
| Stage12 graph output | 24715 | 139 | Stage11 plus 45 recorded path repair triples |
| B0 largest component | 24683 | 139 | Selected final graph; subset of Stage12 graph output |

## Stage6 to Stage7 Evidence

| Evidence | Value |
|---|---:|
| Stage6 graph rows | 18513 |
| Stage6 unique triples | 18513 |
| Stage7 summary `input_triples` | 18513 |
| Stage7 summary `kept_triples` | 17965 |
| Stage7 summary `removed_triples` | 548 |
| Stage7 progress `kept_triples_estimate` | 17965 |
| Stage7 progress `removed_triples_estimate` | 548 |
| Stage7 overlap with Stage6 | 17965 |
| Stage6 minus Stage7 | 548 |

Stage7 log checks:

- `kept_triples_17965`: `True`
- `loaded_18513_prefilter_rows`: `True`
- `loaded_from_stage06_refined_graph`: `True`
- `removed_triples_548`: `True`
- `run_completed_successfully`: `True`

## Full Chain Set Relationships

| Relationship | Count |
|---|---:|
| `B0_overlap_with_stage12_graph_output` | `24683` |
| `stage11_output_minus_stage7_triples` | `6705` |
| `stage11_overlap_with_stage12_graph_output` | `24670` |
| `stage12_output_minus_B0_triples` | `32` |
| `stage12_output_minus_stage11_triples` | `45` |
| `stage6_minus_stage7_triples` | `548` |
| `stage7_overlap_with_stage11_graph_output` | `17965` |
| `stage7_overlap_with_stage6` | `17965` |

## Hashes

| Role | Path | SHA256 |
|---|---|---|
| `B0_largest_component` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` |
| `path_translation_manifest_v3` | `artifacts/final_graph/selected_final_graph/rebuild/path_translation_manifest.v3.json` | `5718facf88302ff6e3f92e2b489c79a0af259b11edfe7abf0df5a13f02db9527` |
| `stage11_graph_output` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl` | `73bc624bf9147b0bba4962ab286648bcfeeb931a94a1d1a727839f160b35ada5` |
| `stage11_manifest` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/manifest.json` | `2e4ad9130fc41c25a99c22d44aa0c992c0dc24cc9254188af05774c68ac64c85` |
| `stage11_report` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/report.json` | `e9be44da03112550b21e824a0fd36c4e25c800941d94bedc1475e0faff0ac944` |
| `stage11_state` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/state.json` | `5fd9191eefbfa0c0826b6f8c5dfc94b3185cbc803d0f433b86015c9c1bed75e8` |
| `stage12_graph_output` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/graph_output.jsonl` | `89ec9bf9c8932962fd3d966073b51f76345666eda5ed5d9beb18659d02e294b0` |
| `stage12_manifest` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/manifest.json` | `cbf244965001c5b709314b1dffe934e5b946cb90906f53fda77a4c13bdeace70` |
| `stage12_report` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/report.json` | `01165428ca948c37198d8ae792624158a69ca4fc2926aa600e256ceb2ca4f8fa` |
| `stage12_state` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/state.json` | `fe0458cc5c465713a8a8353a0d388ea5677bdbbb196a7028ad9d7d2fa80c4cf1` |
| `stage6_refined_graph` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/refined_graph_triples.jsonl` | `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd` |
| `stage6_refinement_moves` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/refinement_moves.jsonl` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `stage6_summary` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/summary.json` | `9df8301d8be4483916d39efa59f9ae438cdfe7d9ca21209b03d8110ea276e539` |
| `stage7_filtered_graph` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl` | `c7d5132bd0b20aa0da4a64ecbf183abf412c3effca38bef84105c7791126fb4b` |
| `stage7_log` | `archive/hetzner_version/logs/eta_aware_component_filter_prod.out` | `74889ae5711647c249692e45c26e931c1b008f242f249d998f08080f934c35d9` |
| `stage7_manifest` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/manifest.json` | `dda38ff4990088601ce4efb317ade1cbecda2da0baf1519dcc818c93f28baa7e` |
| `stage7_progress` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/progress.json` | `73feac80a5ba7485f07e5c0b0d95d518dcf20b2c1ddf7aea7ad18e8c9d1d9a03` |
| `stage7_resolution_doc` | `docs/reconstruction/25_pre_stage11_input_mapping_hetzner_resolution.md` | `e1bf8b779945cda9d8041980303c732b5d5991c01f0d8d8ee35206faab92d4ed` |
| `stage7_summary` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/summary.json` | `31c884be276a69a5e1be65c4b49fc87753d80fc884cf5de45b206373efd633e8` |
| `stage7_to_B0_doc` | `docs/reconstruction/26_stage7_to_B0_chain_verification.md` | `b176d0bd52dbbe6655d80b1b5309077dca6c5e7135501a2fb3e17a675cc61487` |
| `stage7_to_B0_verification` | `artifacts/final_graph/selected_final_graph/rebuild/stage7_to_B0_chain_verification.json` | `e6dccdc4b12a3b8f4a249aee5a20d708f8cbb80d9d337f7ca0af99d2ffbdefa6` |
| `this_verification_script` | `scripts/reconstruction/05_verify_stage6_to_B0_chain.sh` | `86507dc24a46d6d1e935321b088a94d61987bc318238c2258f21fabf7e9a5192` |

## Boundaries

- No Stage6, Stage7, Stage11, Stage12, B0, or allocation artifact was modified.
- No graph was generated.
- No WDQS or LLM call was made.
- This narrows the Stage6-to-B0 historical hash chain, but does not establish Stage1-to-Stage6 provenance, allocation export provenance, exact environment locking, or Phase I end-to-end reproducibility.
