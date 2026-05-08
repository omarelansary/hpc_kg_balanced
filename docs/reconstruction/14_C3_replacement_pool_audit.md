# C3 Replacement-Pool Audit

Status: audit and freezing plan only. C3 has not been run, no C3 graph has been generated, no frozen replacement pool has been created, and `docs/reconstruction/graph_candidates.tsv` has not been edited for C3.

This audit inspects local candidate-pool-like artifacts that could support the planned C3 remove-and-replace experiment. No live WDQS query was made. Large JSONL files were sampled and counted by streaming local records.

## 1. Candidate Pool Inventory

### Baseline Context

| Item | Value | Evidence |
| --- | --- | --- |
| B0 graph | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` | B0 evaluator reports in `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`; local compatibility audit read the file directly |
| B0 unique triples | 24683 | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` |
| B0 unique entities | 21893 | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` |
| B0 target relation counts | `P31=5957`, `P279=750`, `P131=353` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` |
| Canonical allocation for controlled candidates | `src/Pruning graph/bidirectional_allocation_results5k.json` | `experiments/graph_candidates/B0_stage12_largest_component/manifest.json`; `experiments/graph_candidates/C2_targeted_generic_pruning/decision.md` |

### Trial9 Relation-Absence Repair Candidate Files

These files contain local/frozen records, but the summaries link them to an older allocation file, not the controlled 5k allocation used for B0/C1/C2.

| Path | Type | Size bytes | SHA256 | Records | Schema / sample fields | Contains triples? | Query/provenance fields | Linkage | Live WDQS dependency | Confidence |
| --- | ---: | ---: | --- | ---: | --- | --- | --- | --- | --- | --- |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/collected_candidates_all.jsonl` | JSONL | 497163 | `43ca5edc5a0c2b798575a2ce709220b58ce15250c3c4c5c003dca8e098b4e1c5` | 272 | `missing_relation`, `realized_relation`, `orientation`, `candidate_triple_h`, `candidate_triple_r`, `candidate_triple_t`, `graph_context_h`, `graph_context_r`, `graph_context_t`, `anchor_entity`, `new_entity`, `wdqs_query_template`, `wdqs_query_hash`, `wdqs_query`, `hop_support`, `relation_pair_score` | Yes, direct candidate triples in `candidate_triple_*`; 188 unique triples and 84 duplicate candidate-triple records | Yes: full WDQS query text and `wdqs_query_hash` on all 272 records | Trial9 relation-absence repair; summary points to `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json` | Generated from WDQS historically; local file is frozen | High for schema/count; medium for C3 usefulness |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/pair_candidates.jsonl` | JSONL | 87194 | `67265064f25c56ef461d0df3fd8816ebfa52d3d5b41cc8577353e8f85366a4d8` | 365 | `missing_relation`, `realized_relation`, `orientation`, `hop_support`, `anchor_count`, `giant_component_anchor_fraction`, `score`, `priority_value` | No direct triples; relation-pair metadata only | No query text/hash | Trial9 relation-pair ranking metadata | Derived from prior WDQS-based repair pipeline | High for schema/count; low as direct C3 pool |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/accepted_repairs.jsonl` | JSONL | 94963 | `c825108a9afe2c28eaff45697a0e838ebd1d5d3db6de482b02f41538b0c0bfab` | 141 | `missing_relation`, `realized_relation`, `candidate_triple_h`, `candidate_triple_r`, `candidate_triple_t`, `wdqs_query_hash`, `accepted_at_unix` | Yes, accepted repair triples | Partial: query hash and repair metadata, not full query text in accepted records | Trial9 accepted repairs | Generated from WDQS historically; local file is frozen | High for schema/count; medium for exploratory use |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/new_triples_added.jsonl` | JSONL | 6752 | `88654122e8bbfed852ac471540f16e1528cfe339a1b59c6231045e69e630478b` | 141 | `h`, `r`, `t` | Yes, direct h/r/t triples | No query text/hash in this file | Trial9 accepted additions | Depends on upstream WDQS-derived repair records | High for schema/count; medium for exploratory use |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/collected_candidates_unused.jsonl` | JSONL | 251694 | `5a9946ab00b5b20090b3bf22a59556c8fc1f1237bcfeadb843be4ebaf3356457` | 131 | Candidate triple fields plus `reason`, `details`, `wdqs_query`, `wdqs_query_hash` | Yes, unused candidate triples | Yes: full WDQS query text/hash | Trial9 rejected/unused candidates | Generated from WDQS historically; local file is frozen | High for schema/count; medium for exploratory use |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/rejected_repairs.jsonl` | JSONL | 32334 | `153e6886ccf7ea2efcfd37ade743d82102aa68e251fba961204686ed593bad0f` | 132 | Candidate triple fields plus `reason`, `details`; some rows have null candidate endpoints | Partial; includes rejected candidate fields, not always complete triples | No full query text/hash | Trial9 rejected repair records | Depends on upstream WDQS-derived repair records | High for schema/count; low as replacement pool |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/summary.json` | JSON | 2195 | `678873ad5f824b1d0b7715b385fcdf23d0d935c2e959b6c99711ef8d290b2a9e` | 1 | `graph_input_triples=3351`, `graph_output_triples=3492`, `new_triples_added=141`, `missing_relations_requested=128`, `missing_relations_repaired=30`, `allocation_results_json` | Metadata only | Provenance metadata | Confirms older allocation: `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json` and eta field `eta_expected` | Describes historical WDQS-derived repair | High |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/collected_candidates_all.jsonl` | JSONL | 6672538 | `9e6ea1b4041449fa72e2eb85a0a92a29788d778ba872af783246c4e3f065570e` | 4609 | Same candidate triple schema as trial1 | Yes, direct candidate triples; 542 unique triples and 4067 duplicate candidate-triple records | Yes: full WDQS query text/hash on all 4609 records | Trial9 relation-absence repair; summary points to older allocation | Generated from WDQS historically; local file is frozen | High for schema/count; medium for C3 usefulness |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/pair_candidates.jsonl` | JSONL | 724807 | `16d691783b0a96d360135a844c38190cff2c655a9c82be94e211a24c99673dac` | 3034 | Same relation-pair metadata schema as trial1 | No direct triples | No query text/hash | Trial9 relation-pair ranking metadata | Derived from prior WDQS-based repair pipeline | High for schema/count; low as direct C3 pool |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/accepted_repairs.jsonl` | JSONL | 119904 | `a75aa1ddcb971bc91a2c45565a588ad56d240063d16d2b57d3931798934a8736` | 178 | Accepted candidate triple fields plus `wdqs_query_hash`, `accepted_at_unix` | Yes, accepted repair triples | Partial: query hash and repair metadata | Trial9 accepted repairs | Generated from WDQS historically; local file is frozen | High for schema/count; medium for exploratory use |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/new_triples_added.jsonl` | JSONL | 8465 | `49ccdd467dbb9ffd9e764e5b830add3eb81215935de2053b5368da99517b9bf6` | 178 | `h`, `r`, `t` | Yes, direct h/r/t triples | No query text/hash in this file | Trial9 accepted additions | Depends on upstream WDQS-derived repair records | High for schema/count; medium for exploratory use |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/collected_candidates_unused.jsonl` | JSONL | 6710086 | `ede9f47fa9201e48d5247e7cd83fab629820c9b1e136ec38f5e9e9b92b72358f` | 4431 | Candidate triple fields plus `reason`, `details`, `wdqs_query`, `wdqs_query_hash` | Yes, unused candidate triples | Yes: full WDQS query text/hash | Trial9 rejected/unused candidates | Generated from WDQS historically; local file is frozen | High for schema/count; medium for exploratory use |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/rejected_repairs.jsonl` | JSONL | 1302119 | `955a20b0265ae98b89ebffa19d9919455841b3f12acd936d4746e2ff874b6a81` | 5186 | Candidate triple fields plus `reason`, `details`; some rows have null candidate endpoints | Partial; rejected candidates are not always complete triples | No full query text/hash | Trial9 rejected repair records | Depends on upstream WDQS-derived repair records | High for schema/count; low as replacement pool |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/summary.json` | JSON | 2367 | `ef767c5bff25727fa223a2f46d1b1d2738af28e57c213e83ce8bcf7a19b69d35` | 1 | `graph_input_triples=3518`, `graph_output_triples=3696`, `new_triples_added=178`, `missing_relations_repaired=31`, `allocation_results_json` | Metadata only | Provenance metadata | Confirms older allocation: `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json` and eta field `eta_expected` | Describes historical WDQS-derived repair | High |

Conflict requiring human attention: `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/repaired_graph.jsonl` currently has 178 h/r/t records and SHA256 `49ccdd467dbb9ffd9e764e5b830add3eb81215935de2053b5368da99517b9bf6`, identical to `new_triples_added.jsonl`, while `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/summary.json` reports `graph_output_triples=3696`. This makes Trial9 trial2 graph-output provenance unsafe for C3 unless resolved.

### Trial9 Connectivity Repair Top200

| Path | Type | Size bytes | SHA256 | Records | Schema / sample fields | Contains triples? | Query/provenance fields | Linkage | Live WDQS dependency | Confidence |
| --- | ---: | ---: | --- | ---: | --- | --- | --- | --- | --- | --- |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/repair_connectivity_top200/events.jsonl` | JSONL | 85583 | `a5032b4006b758ce753f9dabf62a9586cc9a73c7a2347298768fecc5d9d9431b` | 191 | `event_type`, `component_rank`, `anchor_node`, `query_depth`, `bridge_triples`, `classification_label`, `accepted_into_core` | Yes, bridge triples in event records; 53 event records include bridge triples | Cache keys and WDQS event types, but no query text/hash in events | Trial9 connectivity repair after relation-absence repair | Historical WDQS repair run; manifest gives user agent and query settings | High for schema/count; low for canonical C3 use |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/repair_connectivity_top200/state.json` | JSON | 66294 | `5eb5314aab03df93e753082fe5c267ff3274cfa306b33c59b0f44b93a201e810` | 1 | `added_core_triples`, `query_cache`, `noncore_candidate_samples`, `components` | Yes, `added_core_triples` has 14 triples; `query_cache` has 21 entries | Query cache records WDQS-returned triples but not full query text/hash | Trial9 connectivity repair | Historical WDQS repair run | High for schema/count; low for canonical C3 use |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/repair_connectivity_top200/manifest.json` | JSON | 2607 | `081f9db32a63ede38da0cf57cfe90f030b6212d1521b4f78e3141a4c4715e1a6` | 1 | `inputs`, `cli_args`, `user_agent`, `query_limit`, `timeout_sec` | Metadata only | Full run configuration | Input graph path points to original source workspace; allocation points to older allsupp50 allocation | Confirms live WDQS settings | High |
| `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/repair_connectivity_top200/report.json` | JSON | 1863 | `6171c632d3c60e005cbbcae1b69ea60d95cb73a880fbfcdff0a9a85d10b25e58` | 1 | `original_graph`, `final_graph`, `wdqs_queries`, `core_bridges_added`, `added_core_triples_count` | Metadata only | Run summary | Reports 3518 input triples, 1 final weak component, 14 added core triples | Confirms historical WDQS run | High |

### Stage11 / Stage12 Repair Evidence

These files are directly linked to the Stage11 and Stage12 repair workflow that produced the B0 family of artifacts. They are better aligned with C3 than Trial9, but they are raw event/state files, not a frozen C3 replacement pool.

| Path | Type | Size bytes | SHA256 | Records | Schema / sample fields | Contains triples? | Query/provenance fields | Linkage | Live WDQS dependency | Confidence |
| --- | ---: | ---: | --- | ---: | --- | --- | --- | --- | --- | --- |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/events.jsonl` | JSONL | 111368539 | `d1f7d5ee50d3a0d602d6f026ffdb0b8129cd9e8c34dd59b43d87d2e7fa0247f8` | 250477 | `event_type`, `component_rank`, `anchor_node`, `query_depth`, `bridge_triples`, `classification_label`, `accepted_into_core`, `acceptance_decision`, `cache_key` | Yes, bridge triples in 131586 event records. Event lifecycle duplicates candidates across `candidate_found`, `candidate_classified`, `candidate_saved_noncore`, and selected/applied events. | WDQS event types and cache keys, but no full query text/hash in event rows | Stage11 connectivity repair before Stage12 and B0 | Historical live WDQS run; local file is frozen | High for schema/count; medium for C3 after derived freezing |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/state.json` | JSON | 73014604 | `5fd9191eefbfa0c0826b6f8c5dfc94b3185cbc803d0f433b86015c9c1bed75e8` | 1 | `added_core_triples`, `query_cache`, `noncore_candidate_samples`, `components`, `original_stats` | Yes, `added_core_triples` has 6705 triples; `query_cache` has 24675 entries | Query cache stores WDQS-returned triples keyed by query parameters, but not full query text/hash | Stage11 repair state | Historical live WDQS run; local file is frozen | High for schema/count; medium for C3 after derived freezing |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/manifest.json` | JSON | 2164 | `2e4ad9130fc41c25a99c22d44aa0c992c0dc24cc9254188af05774c68ac64c85` | 1 | `inputs`, `cli_args`, `user_agent`, `query_limit=500`, `max_components=6020` | Metadata only | Full run configuration | Inputs point to `/home/kg_benchmark/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl` and 5k allocation path under `/home/kg_benchmark/src/kg_builder/input/bidirectional_allocation_results5k.json` | Confirms historical live WDQS settings | High |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/report.json` | JSON | 119394 | `e9be44da03112550b21e824a0fd36c4e25c800941d94bedc1475e0faff0ac944` | 1 | `original_graph`, `final_graph`, `wdqs_queries`, `candidate_outcomes`, `core_bridges_added` | Metadata only | Run summary | Reports 17965 input triples, 6021 original weak components, 60 final weak components, 6705 added core triples | Confirms historical live WDQS run | High |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/events.jsonl` | JSONL | 3121682 | `6f3b52a5bb2e620e5e13082fbb2a5fd2b353759bebc377d3a07dc43f71568527` | 8041 | `event_type`, `component_rank`, `anchor_node`, `current_node`, `path_triples`, `path_nodes`, `path_relations`, `classification_label`, `accepted_into_graph`, `relation_deficit_gain` | Yes, path triples in 2213 event records. Event lifecycle duplicates path candidates across found/classified/selected/applied records. | WDQS event types and cache keys, but no full query text/hash in event rows | Stage12 path repair; B0 is largest component from this Stage12 output directory | Historical live WDQS run; local file is frozen | High for schema/count; medium-high for C3 after derived freezing |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/state.json` | JSON | 1612882 | `fe0458cc5c465713a8a8353a0d388ea5677bdbbb196a7028ad9d7d2fa80c4cf1` | 1 | `added_path_triples`, `query_cache`, `components`, `original_stats` | Yes, `added_path_triples` has 45 triples; `query_cache` has 1402 entries | Query cache stores WDQS-returned triples keyed by query parameters, but not full query text/hash | Stage12 path repair directly upstream of B0 | Historical live WDQS run; local file is frozen | High for schema/count; medium-high for C3 after derived freezing |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/manifest.json` | JSON | 2468 | `cbf244965001c5b709314b1dffe934e5b946cb90906f53fda77a4c13bdeace70` | 1 | `inputs`, `cli_args`, `max_hops=3`, `allow_auxiliary_edges=false`, `allow_pattern_only_edges=true`, `query_limit=200` | Metadata only | Full run configuration | Input is Stage11 graph output; relation scope points to 5k allocation path under `/home/kg_benchmark` | Confirms historical live WDQS settings | High |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/report.json` | JSON | 2664 | `01165428ca948c37198d8ae792624158a69ca4fc2926aa600e256ceb2ca4f8fa` | 1 | `original_graph`, `final_graph`, `candidate_paths_found`, `paths_applied`, `triples_added`, `wdqs_queries` | Metadata only | Run summary | Reports 24670 input triples, 60 original weak components, 31 final weak components, 728 candidate paths, 29 applied paths, 45 triples added | Confirms historical live WDQS run | High |

Candidate-pool files referenced by Stage11/Stage12 reports: no separate candidate-pool artifact path is named in the Stage11/Stage12 `report.json` files. The usable local evidence is embedded in `events.jsonl`, `state.json`, and `graph_output.jsonl` within the Stage11/Stage12 directories.

## 2. Compatibility With C3

### Compatibility Table

| Source | Can provide replacement triples? | One-hop replacements? | Two-hop / path replacements? | Relation IDs? | h/r/t available? | Entity compatibility with B0 | Useful for bridge-like `P31`/`P279`/`P131` removals? | Allocation alignment | Risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Trial9 `collected_candidates_all.jsonl` trial1 | Yes, from `candidate_triple_*` | Yes, single candidate edge | No explicit multi-edge path grouping | Yes | Yes | Partial: 56 records have both endpoints in B0, 88 have one endpoint, 128 have neither | Weak. Candidate relations are missing-relation repairs; target relation candidate counts are `P31=0`, `P279=0`, `P131=0`, so they may help replace generic edges with non-generic relations, but they are not bridge-specific for B0 | Older allsupp50 allocation, not 5k | High for canonical C3; medium as exploratory source |
| Trial9 `collected_candidates_all.jsonl` trial2 | Yes, from `candidate_triple_*` | Yes, single candidate edge | No explicit multi-edge path grouping | Yes | Yes | Partial: 449 records both endpoints in B0, 707 one endpoint, 3453 neither | Weak to moderate. It has more local overlap than trial1 but is still a missing-relation repair pool, not a bridge replacement pool | Older allsupp50 allocation, not 5k | High for canonical C3; medium as exploratory source |
| Trial9 `pair_candidates.jsonl` trial1/trial2 | No direct triples | No | No | Yes, relation-pair metadata | No direct h/r/t | Not applicable | Useful only for scoring relation-pair plausibility | Older allsupp50 allocation | High as direct pool; low as ranking metadata |
| Trial9 accepted/new triples | Yes | Yes, single edges | No explicit path grouping | Yes | Yes | Not fully audited against B0 for accepted files; trial collected files show partial overlap | Could add underfilled relations, but not bridge-specific and tied to Trial9 objective | Older allsupp50 allocation | Medium-high |
| Trial9 connectivity top200 events/state | Yes, bridge triples | Yes | Yes, bridge pairs | Yes | Yes | Low for B0: event triple endpoint overlap counts were 44 with neither endpoint in B0, 23 with one endpoint, 4 with both endpoints | Not suitable for B0 bridge replacement without heavy filtering; it repaired a much smaller Trial9 graph | Older allsupp50 allocation | High |
| Stage11 events/state | Yes, bridge triples and query-cache triples | Yes | Yes, mostly one-hop and two-edge bridge groups | Yes | Yes | Stronger than Trial9: event triple endpoint overlap counts were 165390 with one endpoint in B0, 66936 with both, 2310 with neither. Counts are event-record counts and include duplicate lifecycle events. | Moderate. Stage11 discovered many connectivity bridges, including `P31=34110`, `P279=2605`, `P131=1599` event-triple counts, but these are not deduplicated and may include edges already in B0 | 5k allocation according to manifest path, but original absolute path is `/home/kg_benchmark/...` | Medium |
| Stage12 events/state | Yes, path triples and query-cache triples | Yes | Yes, one-to-three-hop path candidates | Yes | Yes | Strong: event triple endpoint overlap counts were 3466 with both endpoints in B0 and 2568 with one endpoint; no zero-overlap event triples were observed in the audit. Counts include duplicate lifecycle events. | Moderate-high. Stage12 is directly upstream of B0 and contains candidate path evidence. It is target-heavy (`P31=2186`, `P279=275`, `P131=0` event-triple counts), so C3 must avoid using it to add new target surplus unless net balance improves. | 5k allocation according to manifest path, but original absolute path is `/home/kg_benchmark/...` | Medium |

### Compatibility Conclusions

Verified facts:

- Trial9 collected candidate files contain direct candidate triples and WDQS query text/hash, but Trial9 summaries link them to `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json`, not to `src/Pruning graph/bidirectional_allocation_results5k.json`.
- Stage11/Stage12 events and states contain bridge/path triples and query caches. They do not contain full WDQS query text/hash in the event rows, but their manifests document WDQS user agents, query limits, input paths, and relation-scope manifest paths.
- Stage12 is the closest local source to B0 because B0 lives under `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/`.

Evidence-based inference:

- Stage11/Stage12 local events/state are the best primary source for a C3 frozen replacement pool because they are directly connected to the B0 construction lineage and use the 5k allocation relation scope in their manifests.
- Raw Stage11/Stage12 files should not be used directly by the C3 generator because event lifecycle duplicates can inflate candidate counts, candidate paths may already be present in B0, and query-cache triples are not already normalized into replacement-candidate records.
- Trial9 candidates should be treated as exploratory or secondary because they provide useful non-generic direct triples with query hashes, but they are tied to a different graph scale and older allocation.

## 3. Frozen-Pool Recommendation

Recommended option: create a derived frozen C3 replacement pool from multiple local sources, with strict source tiers.

Primary tier:

- `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/events.jsonl`
- `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/state.json`
- `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/events.jsonl`
- `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/state.json`

Secondary exploratory tier:

- `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/collected_candidates_all.jsonl`
- `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/accepted_repairs.jsonl`
- `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/new_triples_added.jsonl`
- `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/collected_candidates_all.jsonl`
- `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/accepted_repairs.jsonl`
- `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/new_triples_added.jsonl`

Rejected as direct C3 pool:

- Raw Trial9 `pair_candidates.jsonl` files, because they do not contain h/r/t replacement triples.
- Trial9 trial2 `repaired_graph.jsonl`, because its current record count/hash conflicts with `summary.json`.
- Live WDQS output, because the task forbids live WDQS and thesis-track C3 needs a frozen pool.

Do not proceed directly from raw events. The next reproducibility-safe step is a separate pool-freezing utility that extracts, normalizes, deduplicates, hashes, profiles, and labels candidate triples/paths without running graph generation.

Proposed frozen pool location, not created in this task:

```text
artifacts/frozen_candidate_pools/C3_replacement_pool_v1/
  source_manifest.json
  replacement_candidates.jsonl
  pool_profile.json
  hashes.tsv
```

Proposed `replacement_candidates.jsonl` schema:

| Field | Meaning |
| --- | --- |
| `source_artifact` | Path of the local source artifact used to derive the candidate |
| `source_sha256` | SHA256 of the source artifact at freeze time |
| `candidate_id` | Stable deterministic ID, for example SHA256 of source path, source record index, path group, and h/r/t |
| `h` | Candidate triple head entity |
| `r` | Candidate triple relation |
| `t` | Candidate triple tail entity |
| `path_role` | `single_edge`, `bridge_edge`, `path_edge`, `query_cache_edge`, or `trial9_direct_candidate` |
| `path_group_id` | Stable ID grouping edges that must be added together for a path replacement; null for independent single-edge candidates |
| `source_stage` | `stage11`, `stage12`, `trial9_absence_repair`, or `trial9_connectivity_repair` |
| `provenance_type` | `event_bridge_triples`, `event_path_triples`, `state_added_core_triples`, `state_added_path_triples`, `state_query_cache`, `trial9_candidate_triple`, or `trial9_accepted_triple` |
| `query_hash` | WDQS query hash if available; null for Stage11/Stage12 event/state sources that lack query hashes |
| `notes` | JSON object or string for source event type, classification label, accepted flag, relation-deficit gain, component rank, and known caveats |

Proposed `source_manifest.json` requirements:

- List every source path and SHA256.
- Record extraction timestamp.
- Record B0 graph path and SHA256.
- Record canonical allocation path and SHA256.
- Record whether Trial9 sources are included and under what policy.
- Record whether candidates already present in B0 were removed from the pool.
- Record duplicate-removal policy.
- Record whether candidate groups require adding one edge or multiple edges atomically.

Proposed `pool_profile.json` requirements:

- Total source records inspected.
- Total raw candidate triples extracted.
- Total unique candidate triples.
- Total candidate path groups.
- Counts by source stage, provenance type, relation, path length, and B0 endpoint overlap.
- Counts of candidates already present in B0 and removed.
- Counts of candidates by allocation status: underfilled relation, near-target relation, overfilled relation, unallocated relation, and target-generic relation.

## 4. Scoring Implications for C3

C3 should rank replacements using the canonical allocation `src/Pruning graph/bidirectional_allocation_results5k.json` and the duplicate-safe evaluator behavior in `tools/graph_candidate_evaluation/evaluate_graph_candidate.py`.

Recommended scoring policy:

- Prefer replacements whose relation is underfilled under the 5k allocation.
- Prefer replacements whose relation is near target and will not create new material surplus.
- Avoid replacements in already overfilled relations.
- Avoid adding `P31`, `P279`, or `P131` replacements unless a grouped path has positive net balance after removing a larger amount of target-generic surplus.
- Penalize two-hop or three-hop path replacements unless their grouped addition enables removing enough generic surplus to improve total surplus and does not increase total deficit beyond acceptance thresholds.
- Reject duplicate triples against the parent graph and against candidates already selected during the C3 run.
- Reject candidates that create a new severe surplus in any relation.
- Reject candidates that introduce relation loss, allocated relation absence, or weak disconnection.
- Treat path groups atomically: add all required replacement edges, verify connectivity, remove target generic edge(s), then evaluate the net eta impact.

Scoring implication from C2:

- C2 produced `would_disconnect_graph=75893` and `endpoint_degree_not_redundant=16212` in `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json`. A replacement candidate should therefore be scored by whether it preserves or restores the connectivity function of the generic edge, not only by relation balance.

## 5. Blockers Before C3 Generator Implementation

The following decisions are required before implementing or running C3:

1. Replacement pool source: decide whether `C3_replacement_pool_v1` may use only Stage11/Stage12 sources or may include Trial9 candidates as a secondary exploratory tier.
2. One-hop vs two-hop policy: decide whether C3 may add grouped two-hop or three-hop paths, or only single replacement edges.
3. New entity policy: decide whether replacement paths may introduce new entities. Stage11/Stage12 path records include new entities, and allowing them can preserve connectivity but may change graph population.
4. Trial9 allocation mismatch: decide whether Trial9 candidates are allowed despite being linked to `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json` rather than the canonical 5k allocation.
5. Live WDQS policy: decide whether any live WDQS run is allowed as exploratory only. Thesis-track C3 should not use live WDQS unless results are frozen and explicitly labeled as non-canonical until audited.
6. Derived frozen pool creation: decide whether to create `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/` as the next step. This task did not create it.
7. Duplicate lifecycle policy: decide how to deduplicate Stage11/Stage12 event candidates that appear across `candidate_found`, `candidate_classified`, `path_selected`, and applied events.
8. Already-in-B0 policy: decide whether candidates already present in B0 are excluded from the replacement pool or retained only as provenance evidence.
9. Query-cache policy: decide whether raw `state.json` query-cache triples can be used when no event-level classification label is attached.
10. Atomic path policy: decide how `path_group_id` candidates are evaluated when a path contains both underfilled and overfilled relations.

## 6. Recommendation

Proceed with a replacement-pool freezing step before implementing the C3 generator.

Do not use raw Trial9, Stage11, or Stage12 files directly as generator inputs. The raw files are valuable evidence, but they are not clean candidate pools. A derived frozen pool is needed to make C3 reproducible, deduplicated, hashable, and auditable.

Best source basis:

- Use Stage11/Stage12 events and state as the primary evidence basis because they are linked to B0 and the 5k allocation lineage.
- Keep Trial9 repair candidates as exploratory-only unless a human explicitly accepts the allocation mismatch and the trial2 graph-output conflict is resolved.
- Do not query live WDQS for thesis-track C3.

Current decision:

- C3 remains planned, not generated.
- The immediate next controlled artifact should be `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/`, but it was not created in this task.
