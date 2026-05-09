# Stage5 to B0 Chain Verification

## Conclusion

Wrapper: `scripts/reconstruction/06_verify_stage5_to_B0_chain.sh`

Generated JSON: `artifacts/final_graph/selected_final_graph/rebuild/stage5_to_B0_chain_verification.json`

Overall result: **True**

Stage5 full graph status: `no_full_graph_artifact_found_empty_repair_delta`

No full Stage5 graph artifact was found in `stage05_repair/`. The verified Stage5 evidence is an empty repair-delta artifact, `stage05_repair/repair_triples.jsonl`, plus `stage05_repair/summary.json` reporting zero repairs. Stage6 is verified as a no-op refinement because its output is byte-identical to the Stage4 core graph and `stage06_refine_graph/summary.json` records zero accepted moves.

This verifies the Stage5/Stage6 transition in a bounded way: Stage5 repair introduced no repair triples, Stage6 introduced no refinement changes, and the full graph entering Stage7 is exactly the Stage4 core graph. It does not prove Stage1-to-Stage4 provenance or full Phase I end-to-end reproducibility.

## Verified Chain

```text
archive/hetzner_version/.../stage04_core_graph/core_graph_triples.jsonl
  + archive/hetzner_version/.../stage05_repair/repair_triples.jsonl (empty repair delta)
  -> archive/hetzner_version/.../stage06_refine_graph/refined_graph_triples.jsonl (byte-identical to Stage4)
  -> archive/hetzner_version/.../stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl
  -> src/Pruning graph/.../stage11_eta_aware_connectivity_repair_full/graph_output.jsonl
  -> src/Pruning graph/.../stage12_path_repair_prod/graph_output.jsonl
  -> src/Pruning graph/.../stage12_path_repair_prod/largest_component.csv
```

## Verification Checks

| Check | Result |
|---|---:|
| `stage4_core_graph_rows_18513` | `True` |
| `stage4_core_graph_unique_triples_18513` | `True` |
| `stage4_stage6_byte_equal` | `True` |
| `stage4_stage6_set_difference_empty` | `True` |
| `stage4_stage6_sha256_equal` | `True` |
| `stage4_subset_of_stage6` | `True` |
| `stage5_dir_exists` | `True` |
| `stage5_full_graph_artifact_absent` | `True` |
| `stage5_repair_triples_exists` | `True` |
| `stage5_repair_triples_rows_0` | `True` |
| `stage5_summary_auxiliary_repair_disabled` | `True` |
| `stage5_summary_component_merge_repairs_0` | `True` |
| `stage5_summary_missing_relation_repairs_0` | `True` |
| `stage6_graph_rows_18513` | `True` |
| `stage6_graph_unique_triples_18513` | `True` |
| `stage6_objective_before_equals_after` | `True` |
| `stage6_refinement_moves_empty` | `True` |
| `stage6_subset_of_stage4` | `True` |
| `stage6_summary_accepted_moves_0` | `True` |
| `stage6_summary_termination_no_addition_candidates` | `True` |
| `stage6_summary_total_proposals_evaluated_0` | `True` |
| `stage6_to_B0_previous_verification_passed` | `True` |

## Stage5 and Stage6 Relationship

| Field | Value |
|---|---|
| `interpretation` | `No full Stage5 graph artifact was found. Stage5 repair evidence is an empty repair delta, and Stage6 is byte-identical to the Stage4 core graph with zero accepted refinement moves. Thus the Stage5 repair and Stage6 refinement steps are verified as no-op transitions relative to the last full graph artifact, Stage4 core_graph_triples.jsonl.` |
| `stage5_full_graph_status` | `no_full_graph_artifact_found_empty_repair_delta` |
| `verified_stage4_to_stage6_identity` | `True` |
| `verified_stage5_repair_delta_noop` | `True` |
| `verified_stage6_refinement_noop` | `True` |

## Key Metrics

| Artifact | Rows | Unique triples | Unique relations | SHA256 |
|---|---:|---:|---:|---|
| Stage4 core graph | 18513 | 18513 | 139 | `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd` |
| Stage5 repair delta | 0 | 0 | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Stage6 refined graph | 18513 | 18513 | 139 | `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd` |

## Set Relationships

| Relationship | Count |
|---|---:|
| `stage4_minus_stage6_triples` | `0` |
| `stage4_overlap_with_stage6` | `18513` |
| `stage5_repair_delta_unique_triples` | `0` |
| `stage6_minus_stage4_triples` | `0` |

## Summary Evidence

Stage5 summary:

- `auxiliary_repair_enabled`: `False`
- `component_merge_repairs`: `0`
- `missing_relation_repairs`: `0`

Stage6 summary:

- `accepted_moves`: `0`
- `total_proposals_evaluated`: `0`
- `termination_reason`: `no_addition_candidates`
- `locked_repair_triples`: `0`
- `objective_before == objective_after`: `True`

## Hashes

| Role | Path | SHA256 |
|---|---|---|
| `stage4_core_graph` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_triples.jsonl` | `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd` |
| `stage5_repair_triples` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage05_repair/repair_triples.jsonl` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `stage5_summary` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage05_repair/summary.json` | `11395ad3b01d9df8898a42c490381b8222c3bd75bce8ed36a3fb257586b8bb98` |
| `stage6_refined_graph` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/refined_graph_triples.jsonl` | `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd` |
| `stage6_refinement_moves` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/refinement_moves.jsonl` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `stage6_summary` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/summary.json` | `9df8301d8be4483916d39efa59f9ae438cdfe7d9ca21209b03d8110ea276e539` |
| `stage6_to_B0_doc` | `docs/reconstruction/27_stage6_to_B0_chain_verification.md` | `ae2b54c2417db7093021cb14fbb902cce334cb0105a871b01716bad7b526fd17` |
| `stage6_to_B0_verification` | `artifacts/final_graph/selected_final_graph/rebuild/stage6_to_B0_chain_verification.json` | `f2d394ba890c1db95975e29549f84e6246aaf9ed8ab19c865c71ce0cbf864d52` |
| `this_verification_script` | `scripts/reconstruction/06_verify_stage5_to_B0_chain.sh` | `281153f049c0d6ea25265a457c7fbf0a782a3fdf2062fb11f21ce0fff426eaae` |

## Boundaries

- No Stage4, Stage5, Stage6, Stage7, Stage11, Stage12, B0, or allocation artifact was modified.
- No graph was generated.
- No WDQS or LLM call was made.
- This narrows the Stage5/Stage6 portion of the historical hash chain, but does not establish Stage1-to-Stage4 provenance, allocation export provenance, exact environment locking, or full Phase I reproducibility.
