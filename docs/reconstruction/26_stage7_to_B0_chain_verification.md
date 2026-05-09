# Stage7 to B0 Chain Verification

## Conclusion

Wrapper: `scripts/reconstruction/04_verify_stage7_to_B0_chain.sh`

Generated JSON: `artifacts/final_graph/selected_final_graph/rebuild/stage7_to_B0_chain_verification.json`

Overall result: **True**

This verifies the local frozen evidence chain from the resolved Hetzner Stage7 eta-aware filtered graph through Stage11 repair, Stage12 path repair, and the selected B0 largest component. It does not prove full end-to-end Phase I reproducibility.

## Verified Chain

```text
archive/hetzner_version/.../stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl
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
| `stage7_has_h_r_t_triple_id_fields` | `True` |
| `stage7_progress_kept_triples_17965` | `True` |
| `stage7_row_count_17965` | `True` |
| `stage7_sha256_matches_expected` | `True` |
| `stage7_subset_of_stage11_graph_output` | `True` |
| `stage7_summary_kept_triples_17965` | `True` |
| `stage7_unique_relations_139` | `True` |
| `stage7_unique_triples_17965` | `True` |

## Key Metrics

| Artifact | Unique triples | Unique relations | Notes |
|---|---:|---:|---|
| Stage7 filtered graph | 17965 | 139 | Resolved Hetzner archive input; SHA256 `c7d5132bd0b20aa0da4a64ecbf183abf412c3effca38bef84105c7791126fb4b` |
| Stage11 graph output | 24670 | 139 | Stage7 plus 6705 recorded core repair triples |
| Stage12 graph output | 24715 | 139 | Stage11 plus 45 recorded path repair triples |
| B0 largest component | 24683 | 139 | Selected final graph; subset of Stage12 graph output |

## Set Relationships

| Relationship | Count |
|---|---:|
| `B0_overlap_with_stage12_graph_output` | `24683` |
| `stage11_output_minus_stage7_triples` | `6705` |
| `stage11_overlap_with_stage12_graph_output` | `24670` |
| `stage12_output_minus_B0_triples` | `32` |
| `stage12_output_minus_stage11_triples` | `45` |
| `stage7_overlap_with_stage11_graph_output` | `17965` |

## Stage7 Evidence

- Filtered graph: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`
- Manifest: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/manifest.json`
- Summary: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/summary.json`
- Progress: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/progress.json`
- Log: `archive/hetzner_version/logs/eta_aware_component_filter_prod.out`

Stage7 summary extract:

- `input_triples`: `18513`
- `kept_triples`: `17965`
- `prefilter_source`: `stage06_refine_graph`
- `realized_relations_after`: `139`
- `removed_triples`: `548`
- `total_postfilter_deficit`: `2035`

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
| `stage7_filtered_graph` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl` | `c7d5132bd0b20aa0da4a64ecbf183abf412c3effca38bef84105c7791126fb4b` |
| `stage7_log` | `archive/hetzner_version/logs/eta_aware_component_filter_prod.out` | `74889ae5711647c249692e45c26e931c1b008f242f249d998f08080f934c35d9` |
| `stage7_manifest` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/manifest.json` | `dda38ff4990088601ce4efb317ade1cbecda2da0baf1519dcc818c93f28baa7e` |
| `stage7_progress` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/progress.json` | `73feac80a5ba7485f07e5c0b0d95d518dcf20b2c1ddf7aea7ad18e8c9d1d9a03` |
| `stage7_summary` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/summary.json` | `31c884be276a69a5e1be65c4b49fc87753d80fc884cf5de45b206373efd633e8` |

## Boundaries

- No Stage7, Stage11, Stage12, B0, or allocation artifact was modified.
- No graph was generated.
- No WDQS or LLM call was made.
- This narrows the Stage7-to-B0 historical hash chain, but does not solve Phase I LLM provenance, inverse completion, allocation export provenance, or full environment locking.
