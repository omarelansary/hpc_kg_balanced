# Stage3 to B0 Chain Verification

## Conclusion

Wrapper: `scripts/reconstruction/07_verify_stage3_to_B0_chain.sh`

Generated JSON: `artifacts/final_graph/selected_final_graph/rebuild/stage3_to_B0_chain_verification.json`

Overall wrapper result: **True**

Stage3 -> Stage4 status: **partial**

Partial. The archived pipeline code and run manifest confirm Stage3 candidate audit precedes Stage4, and Stage4 construction reads the frozen Stage2 candidate shard directory. Stage4 core triples are a subset of the combined Stage2 candidate shards. The Stage3 audit artifact itself is relation-level and contains no h/r/t triples, so it is not a direct graph input to Stage4.

Stage4 -> B0 remains verified through the previous Stage5-to-B0 verification report.

## Verified / Partial Chain

```text
archive/hetzner_version/.../stage02_candidates/shards/*.jsonl
  -> archive/hetzner_version/.../stage03_candidate_audit/candidate_relation_audit.jsonl (relation-level audit)
  -> archive/hetzner_version/.../stage04_core_graph/core_graph_triples.jsonl
  -> Stage5/Stage6/Stage7/Stage11/Stage12/B0 chain verified by prior wrappers
```

## Verification Checks

| Check | Result |
|---|---:|
| `pipeline_code_stage03_before_stage04` | `True` |
| `pipeline_code_stage04_reads_stage02_shards` | `True` |
| `run_manifest_stage03_completed` | `True` |
| `run_manifest_stage04_completed` | `True` |
| `run_manifest_stage04_core_triple_count_18513` | `True` |
| `run_manifest_stage04_realized_relations_139` | `True` |
| `stage02_combined_rows_match_summary` | `True` |
| `stage02_combined_unique_relations_139` | `True` |
| `stage02_shard_count_139` | `True` |
| `stage02_summary_total_written_candidates_81958` | `True` |
| `stage03_audit_rows_139` | `True` |
| `stage03_summary_relation_count_139` | `True` |
| `stage03_summary_zero_candidate_relations_0` | `True` |
| `stage04_component_report_count_6524` | `True` |
| `stage04_relation_counts_entries_139` | `True` |
| `stage04_relation_counts_total_18513` | `True` |
| `stage4_core_graph_exists` | `True` |
| `stage4_core_hash_matches_known` | `True` |
| `stage4_core_overlap_stage02_candidate_shards_18513` | `True` |
| `stage4_core_rows_18513` | `True` |
| `stage4_core_subset_of_stage02_candidate_shards` | `True` |
| `stage4_core_unique_relations_139` | `True` |
| `stage4_core_unique_triples_18513` | `True` |
| `stage4_selection_log_equals_core_graph_set` | `True` |
| `stage4_selection_log_sha_matches_core_graph` | `True` |
| `stage5_to_B0_previous_verification_passed` | `True` |

## Stage4 Evidence

| Field | Value |
|---|---|
| Run manifest | `archive/hetzner_version/runs/prod_refine_20260315_180520/manifest.json` |
| Pipeline script | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py` |
| Stage3 manifest info | `{'completed_at': '2026-03-15T17:16:58.682885+00:00', 'possible_undercollection_relations': ['P12994', 'P7209', 'P10374', 'P8308', 'P514', 'P4545', 'P2152', 'P2155', 'P8865'], 'relation_count': 139, 'relations_with_zero_candidates': 0}` |
| Stage4 manifest info | `{'completed_at': '2026-03-18T04:07:08.590320+00:00', 'core_triple_count': 18513, 'realized_relations': 139}` |
| Stage4 input paths from code | `['runs/prod_refine_20260315_180520/stage02_candidates/shards', 'src/kg_builder/input/bidirectional_allocation_results5k.json']` |
| Stage4 output paths | `['archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_triples.jsonl', 'archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_selection_log.jsonl', 'archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_relation_counts.json', 'archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_component_report.json']` |
| Selected triples count | `18513` |
| Relation count | `139` |
| Completion status | `completed` |

Script evidence:

- `has_stage_audit_candidates_function`: `True`
- `has_stage_construct_graph_function`: `True`
- `pipeline_order_stage03_before_stage04`: `True`
- `stage03_audit_reads_stage02_shards`: `True`
- `stage04_construct_reads_stage02_shards`: `True`
- `stage04_writes_core_graph_triples`: `True`

No separate Stage4-specific log was found; this is recorded in the JSON report.

## Candidate / Audit Artifacts

| Artifact | Rows | h/r/t records | Unique triples | Unique relations | Stage4 subset? | Direct Stage4 input? | Assessment |
|---|---:|---:|---:|---:|---|---|---|
| `archive/hetzner_version/runs/prod_refine_20260315_180520/stage03_candidate_audit/candidate_relation_audit.jsonl` | 139 | 0 | 0 | 0 | `False` | `False` | Relation-level audit rows; no h/r/t triples. Pipeline code audits Stage2 shards, but Stage4 construction reads Stage2 shards directly rather than this audit JSONL. |
| `archive/hetzner_version/runs/prod_refine_20260315_180520/stage03_candidate_audit/summary.json` | 3 |  | None | None | `False` | `False` | Stage3 relation-audit summary; no h/r/t triples. |
| `archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards` | 81958 | 81958 | 81958 | 139 | `True` | `True` | Archived pipeline code constructs Stage4 from ctx.run_dir/stage02_candidates/shards; Stage4 core triples are a subset of the combined shard triple set. |

## Stage4 Output Artifacts

| Artifact | Rows / keys | Unique triples | Unique relations | Assessment |
|---|---:|---:|---:|---|
| `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_triples.jsonl` | 18513 | 18513 | 139 | Stage4 output graph, not an input. |
| `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_selection_log.jsonl` | 18513 | 18513 | 139 | Stage4 selection log; byte/content-equivalent selected triples log, not an upstream input. |
| `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_relation_counts.json` | 139 | None | None | Stage4 output relation count report. |
| `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_component_report.json` | 6524 | None | None | Stage4 output component report. |

## Set Relationships

| Relationship | Count |
|---|---:|
| `core_minus_stage4_selection_log` | `0` |
| `stage02_candidate_pool_minus_stage4_core` | `63445` |
| `stage4_core_minus_stage02_candidate_pool` | `0` |
| `stage4_core_overlap_with_stage02_candidate_pool` | `18513` |
| `stage4_selection_log_minus_core` | `0` |
| `stage4_selection_log_overlap_with_core` | `18513` |

## Key Counts

- Stage2 candidate shard count: `139`
- Stage2 candidate rows: `81958`
- Stage2 unique triples: `81958`
- Stage2 unique relations: `139`
- Stage4 core graph SHA256: `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd`
- Stage4 core graph rows / unique triples / relations: `18513` / `18513` / `139`

## Hashes

| Role | Path | SHA256 |
|---|---|---|
| `B0_largest_component` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` |
| `pipeline_config` | `archive/hetzner_version/src/kg_builder/config.yaml` | `5dd43af7ad0c1a1c8c75ae4e0487818fd48ae805d47320dab1bed7918ec0f1eb` |
| `pipeline_runtime_config` | `archive/hetzner_version/src/kg_builder/config.runtime.json` | `e49e20dd29d17ca0879b9c4c649d07c25370544ddeedf8cad3a30876f4fcf4ad` |
| `pipeline_script` | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py` | `a1fec8c08783b3816ebc28e16f39499fb6be2f2a4d587948a00fa4fb9082a5e7` |
| `run_manifest` | `archive/hetzner_version/runs/prod_refine_20260315_180520/manifest.json` | `918546ec1c0f5e02e99f6b09d9dc8d8a6d3caa16ccd1cb31f3ab26d6cd3eaff9` |
| `stage02_summary` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/reports/summary.json` | `d9c6cd6124cb3c938b2045bf25c4bbdf8b6364c3002709547c6b45a98df8626d` |
| `stage03_audit_jsonl` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage03_candidate_audit/candidate_relation_audit.jsonl` | `9de5e0649dfebdf9c62aa00f8ea15ded587070a189748dbd981e66f01827ccf6` |
| `stage03_summary` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage03_candidate_audit/summary.json` | `8914081a4f7a81fa865c1eef04b4a3048f46b395e1648a8b4da5f05c68b4d6c2` |
| `stage04_component_report` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_component_report.json` | `e8659565533741b8c75cb8a373234d27712ea9f786c5d331e36e15ab3fe09164` |
| `stage04_core_graph` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_triples.jsonl` | `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd` |
| `stage04_relation_counts` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_relation_counts.json` | `3883b9f81036fcfd6b9022082b8dbb8b7321f2be6f4fff287772d0e4de057707` |
| `stage04_selection_log` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_selection_log.jsonl` | `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd` |
| `stage5_to_B0_doc` | `docs/reconstruction/28_stage5_to_B0_chain_verification.md` | `fddee7c2d68301abeec2cd863f4a3a1529c56b48797f6216b2fe597067ef5df0` |
| `stage5_to_B0_verification` | `artifacts/final_graph/selected_final_graph/rebuild/stage5_to_B0_chain_verification.json` | `cbd7e96c34b655a78d1fb01d9ea0c32213339678b6f5ee6542a8779128f158e9` |
| `this_verification_script` | `scripts/reconstruction/07_verify_stage3_to_B0_chain.sh` | `ef79bfb6737a2ed148b4cb2764c439f1c2059f8b2839effd023835ed1fe0d66b` |

The JSON report also records per-shard hashes for all Stage2 candidate shard files.

## Boundaries

- No Stage2, Stage3, Stage4, Stage5, Stage6, Stage7, Stage11, Stage12, B0, or allocation artifact was modified.
- No graph was generated.
- No WDQS or LLM call was made.
- Stage3 audit is relation-level and is not a direct graph input to Stage4.
- This narrows Stage3/Stage4 evidence, but does not prove Stage1-to-Stage2 collection reproducibility, allocation export provenance, environment locking, or full Phase I reproducibility.
