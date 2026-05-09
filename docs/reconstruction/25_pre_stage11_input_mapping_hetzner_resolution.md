# Hetzner Resolution for Pre-Stage11 Input Mapping

## Conclusion

The stale pre-Stage11 input graph path is now **resolved with strong evidence** to the Hetzner archive copy:

- Local equivalent: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`
- Stale path: `/home/kg_benchmark/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`
- SHA256: `c7d5132bd0b20aa0da4a64ecbf183abf412c3effca38bef84105c7791126fb4b`

This supersedes the earlier unresolved status in `docs/reconstruction/24_pre_stage11_input_mapping_investigation.md` and `artifacts/final_graph/selected_final_graph/rebuild/path_translation_manifest.v2.json`. The earlier search did not include the newly identified `archive/hetzner_version` path deeply enough as a resolved run mirror.

## Verification Checks

| Check | Result |
|---|---:|
| `path_suffix_matches_stale_path` | `True` |
| `line_count_matches_stage11_report` | `True` |
| `unique_triples_match_stage11_report` | `True` |
| `jsonl_parse_errors_zero` | `True` |
| `contains_h_r_t_fields` | `True` |
| `unique_relations_139` | `True` |
| `candidate_subset_of_stage11_output` | `True` |
| `overlap_with_stage11_output_equals_candidate` | `True` |
| `stage11_output_minus_candidate_count_equals_added_core` | `True` |
| `candidate_equals_stage11_output_minus_added_core` | `True` |
| `stage11_output_minus_candidate_equals_added_core` | `True` |
| `stage7_summary_kept_triples_matches_candidate` | `True` |
| `stage7_progress_kept_triples_matches_candidate` | `True` |

## Resolved File Profile

| Field | Value |
|---|---:|
| `path` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl` |
| `size_bytes` | `8431178` |
| `sha256` | `c7d5132bd0b20aa0da4a64ecbf183abf412c3effca38bef84105c7791126fb4b` |
| `line_count` | `17965` |
| `jsonl_parse_ok` | `True` |
| `parse_error_count` | `0` |
| `unique_triple_count` | `17965` |
| `unique_relation_count` | `139` |
| `overlap_with_stage11_graph_output` | `17965` |
| `stage11_output_minus_candidate_triples` | `6705` |

First-record keys include `h`, `r`, `t`, and `triple_id`, plus scoring/selection fields from eta-aware filtering.

## Stage7 Provenance Evidence

- Stage7 manifest: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/manifest.json`
- Stage7 summary: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/summary.json`
- Stage7 progress: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/progress.json`
- Stage7 log: `archive/hetzner_version/logs/eta_aware_component_filter_prod.out`
- Stage7 script copy: `archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py`

Stage7 summary records:

- `input_triples`: `18513`
- `kept_triples`: `17965`
- `removed_triples`: `548`
- `realized_relations_after`: `139`
- `total_postfilter_deficit`: `2035`
- `prefilter_source`: `stage06_refine_graph`

The Stage7 log records loading 18,513 pre-filter rows from `/home/kg_benchmark/runs/prod_refine_20260315_180520/stage06_refine_graph/refined_graph_triples.jsonl`, then filtering components under eta-aware retention. The Stage7 summary and progress files both record 17,965 kept triples, matching the resolved file and the Stage11 reported input.

## Stage11 Consistency Evidence

- Stage11 manifest: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/manifest.json`
- Stage11 report: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/report.json`
- Stage11 state: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/state.json`
- Stage11 graph output: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl`

The resolved file is exactly the inferred Stage11 input set: Stage11 `graph_output.jsonl` minus `state.json` `added_core_triples`. It is a subset of Stage11 output with 17,965/17,965 overlap; the remaining 6,705 Stage11 output triples are exactly the recorded Stage11 additions.

## Updated Translation Manifest

- Created: `artifacts/final_graph/selected_final_graph/rebuild/path_translation_manifest.v3.json`
- Status: `resolved_strong`

The original Stage11/Stage12 manifests and graph artifacts were not modified.
