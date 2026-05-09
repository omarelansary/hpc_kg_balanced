# R2.7 Canonical 5k Allocation Export Provenance

## Executive Summary

The canonical allocation artifact for the selected B0 final graph is:

`src/Pruning graph/bidirectional_allocation_results5k.json`

Its SHA256 is:

`a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

The local allocation and the archived Hetzner copy are byte-identical to the extent verified by hash and size:

`archive/hetzner_version/src/kg_builder/input/bidirectional_allocation_results5k.json`

This confirms the identity of the allocation consumed by the verified Stage1/Stage2/Stage7/Stage11/Stage12/B0 chain. It does **not** prove exact allocation-export reproducibility, because no direct Streamlit/dashboard export command, saved dashboard state, or manifest linking all Phase I inputs to this exact JSON export was found.

Evidence strength: **partial provenance**.

- Confirmed: canonical file identity, schema, quota content, local/archive byte identity, and downstream use in the B0 chain.
- Evidence-based inference: the file was produced by `src/statistics/hop_pattern_analysis_dashboard.py` using `src/kg_building/bidirectional_triple_allocation.py`.
- Missing: exact dashboard command/export log and cryptographic same-run linkage to all upstream Phase I inputs and the exported genericity support matrix.

## Canonical File Identity

| Artifact | Size bytes | SHA256 | Status |
|---|---:|---|---|
| `src/Pruning graph/bidirectional_allocation_results5k.json` | 85288 | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` | canonical local allocation for B0 |
| `archive/hetzner_version/src/kg_builder/input/bidirectional_allocation_results5k.json` | 85288 | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` | archived Hetzner copy |
| `src/Pruning graph/bidirectional_allocation_results5k.csv` | 2119 | `cd018c815cbf99539fa9b0d2daa999d9121c56627bc6ac983de1017bdc5c8569` | compact relation-pattern matrix sibling |
| `archive/hetzner_version/src/kg_builder/input/bidirectional_allocation_results5k.csv` | 2119 | `cd018c815cbf99539fa9b0d2daa999d9121c56627bc6ac983de1017bdc5c8569` | archived compact matrix sibling |
| `src/Pruning graph/bidirectional_allocation_results5k.enriched.csv` | 16868 | `230b21ad779434208de0a962d17cf056ac69270f6231919f75c5d9c6c78fdcab` | presentation/enrichment derivative |

Verified fact: the local JSON and archived JSON have the same SHA256. The local CSV and archived CSV also have the same SHA256.

## Allocation Schema And Content

The 5k JSON is a top-level object with these keys:

`config`, `eta_per_group`, `pattern_groups`, `relations_universe`, `allocations`

Key content:

| Field | Value |
|---|---:|
| relations universe count | 1467 |
| allocation rows | 154 |
| unique allocated relations after relation merge | 139 |
| duplicate relation rows across pattern groups | 15 |
| row-level `eta_integer` sum | 20000 |
| merged relation-level `eta_integer` sum | 20000 |
| row-level `eta_expected` sum | 20000.0 |

The allocation rows contain:

`backward_score, eta_expected, eta_integer, eta_total, forward_score, p_avg, p_backward, p_forward, pattern, relation, relation_dom_rng_class`

Pattern group counts:

| Pattern | Rows |
|---|---:|
| `anti_symmetric` | 66 |
| `composition` | 26 |
| `inverse` | 44 |
| `symmetric` | 18 |

Eta per group recorded in the artifact:

| Pattern | Eta |
|---|---:|
| `anti_symmetric` | 5000 |
| `composition` | 5000 |
| `inverse` | 5000 |
| `symmetric` | 5000 |


The artifact config records:

```json
{
  "anti_min_conf": 0.99,
  "anti_min_support": 50,
  "base_max_total": 3253580,
  "base_min_total": 50,
  "comp_min_conf": 0.6,
  "comp_min_support": 50,
  "epsilon": 0.0,
  "integerize": true,
  "inv_min_conf": 0.6,
  "inv_min_support": 50,
  "matrix_min_support": 50,
  "matrix_mode": "log1p_balanced_norm",
  "sym_min_conf": 0.6,
  "sym_min_support": 50,
  "temperature": 1.0
}
```

Safe interpretation: the selected allocation uses `matrix_mode=log1p_balanced_norm`, `integerize=true`, `temperature=1.0`, `epsilon=0.0`, and 5,000 target mass for each of the four pattern groups. The artifact itself records these values.

## Duplicate Relation Rows

The JSON contains 154 allocation rows but 139 unique relation IDs, because 15 relation memberships appear in multiple pattern groups.

Duplicate relation IDs:

`P1268, P13177, P16, P1625, P2673, P2674, P2743, P3729, P3730, P4147, P461, P5607, P567, P568, P793`

Downstream Phase II code merges duplicate allocation rows by relation. This is consistent with the archived pipeline log, which reports merging 15 duplicate allocation rows across 139 unique relations from `src/kg_builder/input/bidirectional_allocation_results5k.json`.

Evidence:

- `archive/hetzner_version/logs/relation_balanced_kg_pipeline.out`
- `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py`
- `docs/reconstruction/32_stage1_stage2_candidate_collection_provenance.md`

## Likely Producer Code

Most likely producer: `src/statistics/hop_pattern_analysis_dashboard.py`, with allocation math implemented in `src/kg_building/bidirectional_triple_allocation.py`.

Evidence:

| Evidence | Path / lines | Interpretation |
|---|---|---|
| Allocation UI imports `allocate_for_patterns` | `src/statistics/hop_pattern_analysis_dashboard.py:62-69` | Dashboard uses the allocation library. |
| Allocation runner builds weight matrix and calls `allocate_for_patterns` | `src/statistics/hop_pattern_analysis_dashboard.py:650-678` | Code-path evidence for allocation computation. |
| Dashboard assembles `eta_per_group`, relation universe, matrix mode, and allocation call | `src/statistics/hop_pattern_analysis_dashboard.py:1396-1430` | Code-path evidence matches the JSON fields. |
| Dashboard builds allocation rows with `pattern`, `relation`, `eta_expected`, and `eta_integer` | `src/statistics/hop_pattern_analysis_dashboard.py:1464-1477` | Schema matches the 5k JSON. |
| Dashboard builds `result_payload` with `config`, `eta_per_group`, `pattern_groups`, `relations_universe`, and `allocations` | `src/statistics/hop_pattern_analysis_dashboard.py:1604-1626` | Exact top-level JSON schema match. |
| Dashboard exposes download buttons for allocation JSON, allocation CSV, and genericity matrix JSON | `src/statistics/hop_pattern_analysis_dashboard.py:1633-1649` | Export mechanism exists, but does not log a command by itself. |
| Allocation library defines expected/integer eta algorithm | `src/kg_building/bidirectional_triple_allocation.py:272-452` | Implementation evidence for quotas. |
| Phase II config says allocation JSON and support matrix are exported from dashboard and should be paired | `src/kg_building/relation_balanced_kg_pipeline_config.yaml:11-36` | Design evidence for the intended export pair. |
| Archived production config points to the 5k allocation and adjacency support matrix | `archive/hetzner_version/src/kg_builder/config.yaml:49-67` | Downstream production use evidence. |

Important caveat: the dashboard default eta inputs shown in the source are 1,000 per group, while this artifact records 5,000 per group. That is not a conflict; it means the user/session changed the interactive controls before export. The final control values are preserved in the exported JSON config, but the interactive session itself is not manifested.

## Command And Log Evidence

No direct command/log evidence was found for producing `bidirectional_allocation_results5k.json`.

Found evidence is downstream consumption evidence:

| Evidence | What it supports |
|---|---|
| `archive/hetzner_version/runs/prod_refine_20260315_180520/manifest.json` | Phase II run config uses `src/kg_builder/input/bidirectional_allocation_results5k.json`. |
| `archive/hetzner_version/logs/relation_balanced_kg_pipeline.out` | Stage1/Stage2 pipeline loaded and merged duplicate rows from the 5k allocation. |
| `archive/hetzner_version/logs/eta_aware_component_filter_prod.out` | Stage7 loaded 139 positive-eta allocations from the 5k allocation. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/manifest.json` | Stage11 relation scope uses stale `/home/kg_benchmark/src/kg_builder/input/bidirectional_allocation_results5k.json`. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/manifest.json` | Stage12 relation scope uses the same stale allocation path. |
| `artifacts/final_graph/selected_final_graph/final_graph_manifest.json` | Final B0 package records the local canonical allocation hash. |

Classification:

- Allocation export command evidence: **missing**.
- Downstream allocation consumption evidence: **confirmed**.
- Allocation file identity evidence: **confirmed**.

## Upstream Phase I Inputs

The 5k allocation JSON does not embed input paths or input hashes. The following artifacts are therefore likely upstream only by code-path/default-path evidence and prior reconstruction, not by an embedded manifest inside the allocation JSON.

| Artifact | Size bytes | SHA256 | Evidence role |
|---|---:|---|---|
| `data/archived/hop_support_v2_w_failed_statuses.wikibase_item_only_before_target_enrichment.jsonl` | 3562314 | `d97e3fd40152f99b01bd60347eb82d2fd2766c1bb9ee194f4fe64dbf942d0f8f` | likely dashboard input or related Phase I artifact |
| `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl` | 39087183 | `20761759cd58dd1b3bbae270e76171274975efee7f55fd30ff649e694508f987` | likely dashboard input or related Phase I artifact |
| `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition_verified.jsonl` | 395432579 | `1313b2d0b6d8afc8f1a9ba3ae291abfb685731b75a9f2c4b8ac7b291827c5fba` | likely dashboard input or related Phase I artifact |
| `data/raw/wikidata_ontology.properties.json` | 644751 | `daac555483634bfcb608c5fc04f9a2f14678772381edd91440822606db3a0380` | domain/range metadata used by dashboard |
| `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl` | 10021946 | `8fbc1db6847b7676c1f144521218b444e2768cb06345d1a6288afd58177df54e` | likely dashboard input or related Phase I artifact |
| `data/processed/output_hop_support_v3_from_hop_discovery_from_json_and_support_v2_rerun.normalized.jsonl` | 3584582 | `3795b62b2302695dd5bdf439b96241337b898ce770254b13f4f59c22b649eb15` | likely dashboard input or related Phase I artifact |


The strongest code-path evidence is that the dashboard defaults point to the hop-support v2 JSONL and compact v2 composition-verification JSONL, while separate hop-v3 allocation artifacts also exist. Because the selected 5k allocation does not store input paths, the exact upstream Phase I input set remains **partial** rather than confirmed.

## Support Matrix Linkage

Archived Phase II consumed:

`archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json`

SHA256:

`75794511aaa9ef72a7c63fd0d9a3c11969b72c4fa4bfb01237859b612f544041`

Profile:

| Metric | Value |
|---|---:|
| outer relation count | 139 |
| inner relation count | 129 |
| nonempty rows | 134 |
| nonzero cells | 831 |

The dashboard code exports a genericity matrix over the current positive-eta allocation relation set (`src/statistics/hop_pattern_analysis_dashboard.py:1576-1602`) and writes it through a download button (`src/statistics/hop_pattern_analysis_dashboard.py:1645-1649`). The archived production config uses the adjacency-support matrix as `support_matrix_path` (`archive/hetzner_version/src/kg_builder/config.yaml:64-67`).

Status: **partial**.

Why partial: the support matrix is co-located with the archived 5k allocation and matches the intended dashboard export shape, but the 5k allocation JSON does not embed the support matrix hash or path, and no same-run export manifest was found.

## Alternate Allocation Artifacts

These allocation files exist and should not be confused with the canonical B0 allocation:

| Path | SHA256 | Universe | Rows | Unique relations | Eta sum | Matrix mode | Config |
|---|---|---:|---:|---:|---:|---|---|
| `data/processed/hop_support_v3/bidirectional_allocation_results_hop_v3_patchedby_v2_allsup50_60sym_99anti_90inv_95comp.json` | `472b32e6418b344267bf87237f3f4474d6a0542e3e8a46cf96bdfef393f94eec` | 1467 | 143 | 125 | 20000 | `log1p_balanced_norm` | `{'base_min_total': 50, 'base_max_total': 3253580, 'sym_min_support': 50, 'sym_min_conf': 0.6, 'anti_min_support': 50, 'anti_min_conf': 0.99, 'inv_min_support': 50, 'inv_min_conf': 0.9, 'comp_min_support': 8, 'comp_min_conf': 0.95, 'matrix_min_support': 50, 'matrix_mode': 'log1p_balanced_norm', 'temperature': 1.0, 'epsilon': 0.0, 'integerize': True}` |
| `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json` | `aafade9887a863ee5bcebe8fb67a6e0f151ac2c696a6bc2c283044bca9b8090e` | 1148 | 209 | 164 | 20000 | `log1p_balanced_norm` | `{'base_min_total': 50, 'base_max_total': 298810, 'sym_min_support': 50, 'sym_min_conf': 0.97, 'anti_min_support': 50, 'anti_min_conf': 0.97, 'inv_min_support': 50, 'inv_min_conf': 0.97, 'comp_min_support': 50, 'comp_min_conf': 0.9, 'matrix_min_support': 50, 'matrix_mode': 'log1p_balanced_norm', 'temperature': 1.0, 'epsilon': 0.0, 'integerize': True}` |
| `data/connectedgraph/bidirectional_allocation_results_allsupp8_conf97_compconf90.json` | `790e856388e592c29cb2957dbea36aa4edcd43667d14b820b767748cfc8d19e5` | 1469 | 241 | 196 | 20000 | `log1p_balanced_norm` | `{'base_min_total': 8, 'base_max_total': 298810, 'sym_min_support': 8, 'sym_min_conf': 0.97, 'anti_min_support': 8, 'anti_min_conf': 0.97, 'inv_min_support': 8, 'inv_min_conf': 0.97, 'comp_min_support': 8, 'comp_min_conf': 0.9, 'matrix_min_support': 8, 'matrix_mode': 'log1p_balanced_norm', 'temperature': 1.0, 'epsilon': 0.0, 'integerize': True}` |
| `data/connectedgraph/bidirectional_allocation_results_allsup8_invsup200_allconf97_invcompconf90.json` | `ecd16be28f654185389590cca2cd504319a459a079bfe181567b7cacd81364ed` | 895 | 230 | 185 | 20000 | `log1p_balanced_norm` | `{'base_min_total': 8, 'base_max_total': 298809, 'sym_min_support': 8, 'sym_min_conf': 0.97, 'anti_min_support': 8, 'anti_min_conf': 0.97, 'inv_min_support': 200, 'inv_min_conf': 0.9, 'comp_min_support': 8, 'comp_min_conf': 0.9, 'matrix_min_support': 200, 'matrix_mode': 'log1p_balanced_norm', 'temperature': 1.0, 'epsilon': 0.0, 'integerize': True}` |
| `data/connectedgraph/bidirectional_allocation_results_backup.json` | `a56c60da7ba2b2134a356b6217d487a2406a2547f9a58190c0600e45ee572ccd` | 1469 | 354 | 317 | 4000 | `log1p_balanced_norm` | `{'min_total': 8, 'max_total': 298809, 'min_conf': 0.97, 'min_reverse_conf': 0.0, 'comp_min_support': 8, 'matrix_min_support': 8, 'matrix_mode': 'log1p_balanced_norm', 'temperature': 1.0, 'epsilon': 0.0, 'integerize': True}` |

The canonical B0 allocation remains `src/Pruning graph/bidirectional_allocation_results5k.json` because it is byte-identical to the archived Phase II input and is referenced by the final B0 package and downstream Stage1/Stage2/Stage7 evidence.

## Answers To R2.7 Questions

1. **Are the local and archived 5k allocation files byte-identical?**  
   Yes. Both JSON files have SHA256 `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` and size 85,288 bytes.

2. **What is the schema of the 5k allocation file?**  
   Top-level object with `config`, `eta_per_group`, `pattern_groups`, `relations_universe`, and `allocations`.

3. **How many allocated relations does it contain?**  
   It contains 154 allocation rows and 139 unique allocated relations after duplicate relation rows are merged.

4. **Which eta fields exist?**  
   `eta_expected`, `eta_integer`, and `eta_total`.

5. **Which script most likely produced it?**  
   `src/statistics/hop_pattern_analysis_dashboard.py`, using `src/kg_building/bidirectional_triple_allocation.py`. This is code-path and schema evidence, not a logged export run.

6. **Is there direct command/log evidence for producing it?**  
   No direct export command or dashboard session log was found. Logs confirm downstream consumption, not generation.

7. **Which upstream Phase I artifacts appear to feed it?**  
   The dashboard code points to hop-support v2, compact composition-verification v2, and property metadata inputs. The exact selected input hashes are not embedded in the 5k JSON.

8. **Does it link to the support matrix used by Stage1?**  
   Partially. The dashboard can export the genericity support matrix over positive-eta relations, and the archived Phase II run consumed `genericity_support_matrix.adjacency_support.json`. The allocation JSON itself does not record the support matrix path/hash.

9. **Is the allocation export provenance confirmed, partial, ambiguous, or unresolved?**  
   Partial: artifact identity/content and downstream use are confirmed; exact export command/session and full upstream hash chain are missing.

10. **What exact claim is safe in the thesis?**  
   Safe: "The selected final graph was evaluated against the canonical 5k allocation artifact `src/Pruning graph/bidirectional_allocation_results5k.json`, byte-identical to the archived Phase II input, containing integer quotas for 139 unique allocated relations after merging duplicate rows and recording the allocation thresholds and matrix mode."

11. **What claim is unsafe?**  
   Unsafe: "The canonical 5k allocation can be exactly regenerated from a preserved command, dashboard state, and complete Phase I input hash manifest." That evidence is not present.

## Thesis Claim Safety

| Claim | Status | Recommended wording |
|---|---|---|
| The final B0 graph uses the canonical 5k allocation. | Safe | State with path and SHA256. |
| The 5k allocation contains integer quotas for 139 unique relations after duplicate-row merging. | Safe | State with path and schema counts. |
| The allocation used 5,000 target mass per pattern group and `log1p_balanced_norm`. | Safe | Cite the allocation JSON `config` and `eta_per_group`. |
| The allocation was exported by the interactive dashboard. | Needs softer wording | Say the schema and code path are consistent with the dashboard export; direct export log is missing. |
| The genericity support matrix was exported in the same dashboard session. | Needs softer wording | Say the support matrix is co-located and code-compatible, but same-run linkage is not manifested. |
| The allocation can be exactly regenerated end-to-end from frozen Phase I inputs. | Unsupported | Do not claim until a run manifest/wrapper captures exact inputs, thresholds, matrix mode, and output hashes. |

## Remaining Gaps

- Missing exact Streamlit command or saved dashboard state for the 5k allocation export.
- Missing input hashes inside the allocation JSON for hop support, composition verification, property metadata, and support matrix.
- Missing same-run hash linkage between `bidirectional_allocation_results5k.json` and `genericity_support_matrix.adjacency_support.json`.
- Missing manifest for any manual rename/copy from dashboard download name `bidirectional_allocation_results.json` to `bidirectional_allocation_results5k.json`.
- Full Phase I-to-allocation rerun reproducibility remains incomplete.

## Machine-Readable Evidence

A structured evidence record was written to:

`artifacts/final_graph/selected_final_graph/rebuild/allocation_5k_export_provenance.json`
