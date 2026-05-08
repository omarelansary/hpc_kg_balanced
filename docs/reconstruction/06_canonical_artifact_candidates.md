# Canonical Artifact Candidates

## Scope

This decision pack evaluates candidate thesis-reported artifacts in the copied workspace:

`/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced_refactor_work`

Only evidence-backed statements are used. "Inference" means the conclusion is supported by multiple artifacts or logs but is not directly stated in a single run manifest.

## Path Mismatch Found

The requested Stage13 paths under `src/Pruning graph/stage13_branch_sweep_20260423_160635/...` were not present at that location. The copied Stage13 branch sweep exists under:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/`

Evidence: read-only `find` search for `stage13_branch_sweep_20260423_160635`; `logs/stage13_prune_revised_29012090.out` lines reporting `PRUNE_DIR=src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded`.

## Candidate Artifact Table

| Path | Type | Size Bytes | SHA256 | Likely Role | Upstream Dependencies If Identifiable | Downstream Use If Identifiable | Evidence Files / Logs | Confidence | Safe To Cite In Thesis? | Unresolved Concerns |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- | --- |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` | CSV graph | 601555 | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` | Candidate final graph before Stage13 pruning | Stage11 eta-aware repair and Stage12 path repair; allocation family points to `bidirectional_allocation_results5k.json` through manifests and eta summary | Input graph for Stage13 branch sweep | `stage12_path_repair_prod/report.json`; `largest_component_eta_analysis/summary.json`; `logs/stage13_prune_revised_29012090.out` | High for existence and metrics; medium for full upstream input path | Yes, as "candidate final post-repair largest component" | External production input path is not mapped; no direct Stage12 SLURM log found in `logs/`. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component_eta_analysis/summary.json` | JSON report | 35045 | `116b45d20b4efb0fa66b6e044d1ea38c956f9aa3c3a9641a778bcdc68c03c299` | Stage12 eta audit | Graph path stored as external `runs/prod_refine_.../largest_component.csv`; allocation path stored as `src/kg_builder/input/bidirectional_allocation_results5k.json` | Supports Stage12 thesis metrics | Same file; `largest_component_supervisor_summary.md` | High for audit metrics | Yes, with path-translation caveat | Stored allocation path does not exist in this copied workspace. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl` | JSONL graph | 2127003 | `e01d7137c1dbcd790082825a025cade7198a957b3c936f0d9b5b3f0b33780b73` | Candidate final balance-pruned graph | Stage12 `largest_component.csv`; `src/Pruning graph/bidirectional_allocation_results5k.json`; Stage13 revised density-aware pruning script | Reported by Stage13 branch summary; visualized and audited by Stage13 outputs | `logs/stage13_prune_revised_29012090.out`; `pruned_graph.report.json`; branch `summary.csv` | High | Yes, as "candidate final pruned graph" after human confirms Stage13 is in thesis pipeline | Pruning worsens total deficit relative to Stage12; Stage13 is optional/post-pipeline unless accepted as final reported stage. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.report.json` | JSON report | 482600 | `e22c096662f534a5c7482ba88cdc017ad66bc37a3e8cdb504c5b4e2ab0161a54` | Stage13 pruning report | Stage12 graph and `5k` allocation, as shown in log and config paths | Supports Stage13 graph metrics and pruning rationale | Same file; `logs/stage13_prune_revised_29012090.out` | High | Yes, for pruning/report metrics | Report lacks top-level input/output path fields; paths are in config/logs instead. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/eta_analysis/summary.json` | JSON report | 35142 | `87186e71cb3a7f19cbff7dba915e9d24dffca9b4803bc7a1328e6df3e580ff2c` | Stage13 eta audit | `pruned_graph.jsonl`; `src/Pruning graph/bidirectional_allocation_results5k.json` | Supports final pruned graph eta metrics | Same file; Stage13 summary/log | High | Yes | Must be cited as pruned-graph audit, not Stage12 audit. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/summary.csv` | CSV summary | 6999 | `8ead76bf5f836756c386b9285a79a3642119e885384836ab82ecadf3daadd8ff` | Stage13 branch sweep comparison table | Six Stage13 branch run outputs | Downselects aggressive branch among alternatives | Same file; `summary.md`; Stage13 branch directories | High | Yes, as branch-comparison evidence | It summarizes branches, but does not alone justify choosing a branch. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/summary.md` | Markdown summary | 2217 | `5157df922be5f8a03cb084864c30c85f2a2068e090da82d40d345986eca8d3a4` | Human-readable Stage13 branch summary | Stage13 summary CSV | Thesis discussion support | Same file | Medium to high | Yes, as supporting note | Contains guidance, not a formal manifest. |
| `src/Pruning graph/bidirectional_allocation_results5k.json` | JSON allocation | 85288 | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` | Strongest allocation candidate for Stage12/Stage13 | Pattern groups and support/composition sources not directly embedded | Used by Stage13; local equivalent of Stage12 manifest allocation family | Stage13 log; Stage11/12 manifests; Stage12/13 eta summaries; allocation comparison notes | High for Stage13, medium-high for Stage12 path translation | Yes, after human confirms final graph family | Direct allocation export log is still missing. |
| `src/Pruning graph/bidirectional_allocation_results5k.csv` | CSV allocation matrix | 2119 | `cd018c815cbf99539fa9b0d2daa999d9121c56627bc6ac983de1017bdc5c8569` | Compact relation-to-pattern matrix for 5k allocation | Same allocation family as `bidirectional_allocation_results5k.json` | Metadata enrichment and thesis tables | `scripts/enrich_allocation_csv_with_relation_metadata.py`; file header | Medium | Yes, as supporting allocation table | JSON is safer as canonical allocation because it contains config and eta values. |
| `src/Pruning graph/bidirectional_allocation_results5k.enriched.csv` | CSV allocation metadata | 16868 | `230b21ad779434208de0a962d17cf056ac69270f6231919f75c5d9c6c78fdcab` | Enriched allocation table for readability | `bidirectional_allocation_results5k.csv` plus relation metadata | Thesis tables/appendix | `scripts/enrich_allocation_csv_with_relation_metadata.py` | Medium | Yes, as derived presentation artifact | Must cite JSON as canonical source. |
| `data/processed/hop_support_v3/bidirectional_allocation_results_hop_v3_patchedby_v2_allsup50_60sym_99anti_90inv_95comp.json` | JSON allocation | 80637 | `472b32e6418b344267bf87237f3f4474d6a0542e3e8a46cf96bdfef393f94eec` | Allocation for Trial2 online Phase4 branch | Hop-v3 support/composition family; exact dashboard/export run not logged | Trial1/Trial2 online construction and checkpoint postprocess | Trial2 SLURM runners; `trial2_stage12_ablation_comparison.md`; `hop_v3_vs_5k_allocation_comparison.md` | High for Trial2 linkage | Yes, for Trial2/abandoned branch claims | Not the strongest allocation for Stage12/Stage13 final candidates. |
| `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json` | JSON allocation | 104372 | `aafade9887a863ee5bcebe8fb67a6e0f151ac2c696a6bc2c283044bca9b8090e` | Allocation for Trial9/allsupp50 online and repair branch | Direct allocation export run not logged | Trial9 online and repair audits | Trial9 SLURM runners; repair manifests; relation audit reports | High for Trial9 linkage | Yes, for Trial9 branch claims | Not linked to Stage12/Stage13 final candidates. |
| `data/connectedgraph/bidirectional_allocation_results_allsupp8_conf97_compconf90.json` | JSON allocation | 122333 | `790e856388e592c29cb2957dbea36aa4edcd43667d14b820b767748cfc8d19e5` | Allocation for allsupp8 online branch | Direct allocation export run not logged | Trial10 runner references | `scripts/slurm/phase4_connectedgraph_sparql_watch_trial10_sup8.slurm` | Medium | Yes, only for allsupp8 branch | No strong final graph linkage found. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/manifest.json` | JSON manifest | 2164 | `2e4ad9130fc41c25a99c22d44aa0c992c0dc24cc9254188af05774c68ac64c85` | Stage11 repair manifest | External production run input; 5k allocation path under `/home/kg_benchmark` | Supports Stage11 provenance | Same file | High for manifest facts | Yes, with external-path caveat | External input graph path mapping unresolved. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/report.json` | JSON report | 119394 | `e9be44da03112550b21e824a0fd36c4e25c800941d94bedc1475e0faff0ac944` | Stage11 repair report | Stage11 manifest and input graph | Supports Stage11 repair metrics | Same file | High | Yes | No direct SLURM log found in `logs/`. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/manifest.json` | JSON manifest | 2468 | `cbf244965001c5b709314b1dffe934e5b946cb90906f53fda77a4c13bdeace70` | Stage12 path repair manifest | Stage11 output; 5k allocation path under `/home/kg_benchmark` | Supports Stage12 provenance | Same file | High for manifest facts | Yes, with external-path caveat | External input path mapping unresolved. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/report.json` | JSON report | 2664 | `01165428ca948c37198d8ae792624158a69ca4fc2926aa600e256ceb2ca4f8fa` | Stage12 path repair report | Stage12 manifest | Supports Stage12 repair metrics | Same file | High | Yes | No direct SLURM log found in `logs/`. |
| `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition_verified.jsonl` | JSONL | 395432579 | `1313b2d0b6d8afc8f1a9ba3ae291abfb685731b75a9f2c4b8ac7b291827c5fba` | V2 composition verification output | Domain/range-compatible hop support v2 input | Potential upstream evidence for allocation, but no direct allocation input path embedded | `logs/composition_min8_jsonl_27683654.out`; stats file | High for composition run; low for direct Stage12/13 allocation linkage | Yes, for composition verification claim | Direct link to 5k allocation generation not embedded. |
| `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.jsonl` | JSONL | 173827779 | `884a445788c9a0c200cc79d91bb91c28facd744fed5c5594142d508233b9f1ec` | V3 composition verification output | Hop-v3 compatible-target input | Potential upstream evidence for hop-v3 allocation | `logs/composition_hop_support_v3_min8_jsonl_28197929.out`; stats file | High for composition run; medium for hop-v3 allocation family | Yes, for v3 composition claim | Not directly linked to 5k allocation in a manifest. |
| `data/processed/output_hop_support_v3_from_hop_discovery_from_json_and_support_v2_rerun.normalized.jsonl` | JSONL | 3584582 | `3795b62b2302695dd5bdf439b96241337b898ce770254b13f4f59c22b649eb15` | Hop support v3 normalized output | Hop support v2 converted input | Upstream to v3 composition/allocation analysis | `logs/normalized_hop_support_v3_rerun28049486.out` | High for run | Yes, for hop-support-v3 claim | Direct allocation export linkage still missing. |
| `data/processed/output_hop_support_v3_triplets_from_hop_discovery_from_json_and_support_v2_rerun.normalized.jsonl` | JSONL | 7937471 | `4f67605f4b46336456ef17769d5e80068d4ef751892bcd1b15c314a4ea615850` | Hop support v3 triplet-level output | Hop support v3 run | Upstream evidence for support matrix/pattern analysis | `logs/normalized_hop_support_v3_rerun28049486.out` | High for run | Yes, for hop-support-v3 details | Direct final allocation export linkage still missing. |

## Evidence Chain Summary

### Stage12 Candidate

```text
5k allocation family
  -> Stage11 eta-aware connectivity repair manifest/report
  -> Stage12 path repair manifest/report
  -> largest_component.csv
  -> largest_component_eta_analysis/summary.json
```

Verified facts:

- Stage12 `largest_component.csv` contains 24683 unique triples, 139 unique relations, 21893 entities, and one weak component by direct graph check.
- Stage12 eta summary reports 139 allocated relations covered, zero relations with observed count 0, total expected eta 20000, total observed allocated triples 24683, total deficit 2019, total surplus 6702, and weighted fulfillment ratio 1.23415.

Evidence: `largest_component.csv`; `largest_component_eta_analysis/summary.json`; `largest_component_eta_analysis/largest_component_supervisor_summary.md`; Stage11/12 manifests and reports.

Unresolved: Stage12 manifests point to `/home/kg_benchmark/...` and `src/kg_builder/input/bidirectional_allocation_results5k.json`; local path translation points to `src/Pruning graph/bidirectional_allocation_results5k.json`, but the external input graph mapping still needs human confirmation.

### Stage13 Aggressive Candidate

```text
Stage12 largest_component.csv
  + src/Pruning graph/bidirectional_allocation_results5k.json
  -> stage13_balance_prune_revised_density_aware.slurm
  -> aggressive_but_guarded/pruned_graph.jsonl
  -> pruned_graph.report.json
  -> aggressive_but_guarded/eta_analysis/summary.json
  -> branch summary.csv / summary.md
```

Verified facts:

- Stage13 log directly reports `INPUT_GRAPH=src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`.
- Stage13 log directly reports `ALLOCATION_MANIFEST=src/Pruning graph/bidirectional_allocation_results5k.json`.
- Stage13 aggressive branch contains 24223 unique triples, 139 unique relations, 21893 entities, and one weak component by direct graph check.
- Stage13 report says `total_removed=460`, `rounds_completed=10`, no guard triggered, final `weak_component_count=1`, and final `largest_component_ratio=1.0`.
- Stage13 eta summary reports total expected eta 20000, total observed allocated triples 24223, total deficit 2359, total surplus 6582, weighted fulfillment ratio 1.21115, and zero relations 0.

Evidence: `logs/stage13_prune_revised_29012090.out`; `aggressive_but_guarded/pruned_graph.report.json`; `aggressive_but_guarded/eta_analysis/summary.json`; branch `summary.csv`; branch `summary.md`.

Unresolved: Stage13 is a strong candidate final artifact only if the thesis explicitly treats balance pruning as part of the reported pipeline rather than optional post-pipeline analysis.

