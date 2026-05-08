# Actual Pipeline Reconstruction

## Reconstruction Method

This file reconstructs actual execution reality from workspace evidence, not from the intended abstract phase design. Evidence includes SLURM logs, runner scripts, Python entrypoints, comments, configs, manifests, reports, timestamps, and artifact names.

Confidence terms:

| Confidence | Meaning |
| --- | --- |
| High | Direct command/log/report evidence identifies the script, inputs, outputs, and outcome. |
| Medium | Source and artifacts align, but direct run log or complete provenance is missing. |
| Low | Source or artifact exists, but production execution or completeness is not established. |

## Step Table

| Step ID | Likely Phase/Stage | Script Or Command | Inputs | Outputs | Calls WDQS/SPARQL | Uses LLM | Determinism | Repeatability | Evidence | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A0 | Relation profile preparation | `src/composition_verification/classify_relations_pipeline.py` | Wikidata relation/property metadata; exact production input not fully proven | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` | No direct WDQS evidence in this script | Yes, OpenAI Chat Completions; default model `gpt-4.1-mini`, temperature `0.2` | LLM nondeterminism and provider drift despite low temperature | One-time or repeatable only with frozen prompts/model/version | Script source; raw output file; no matching production SLURM log found | Low |
| A1 | Phase I, relation universe selection and empirical two-hop discovery | `scripts/slurm/hop_discovery_json.slurm` running `src/archive/hop_discovery.py` | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` from original source path in log | `data/processed/hop_discovery_from_json.jsonl` | Yes, WDQS endpoint `https://query.wikidata.org/sparql` | No | Not fully deterministic because live WDQS, retry behavior, and endpoint failures | Repeatable only against frozen WDQS snapshot or cached output | `logs/hop_discovery_json_27530562.out`; `src/archive/hop_discovery.py`; output file | High |
| A2 | Phase I, hop support v2 | `scripts/slurm/hop_support_v2.slurm` running `src/hop_support_and_sym_anti_verification/hop_support_v2.py` | `data/raw/wikidata_ontology.hop_discovery_run2.json`; resumed `data/processed/hop_support_v2.jsonl` in original source | `data/processed/hop_support_v2.jsonl`; later enriched and normalized derivatives | Yes | No | Not fully deterministic because live WDQS and resume state | Repeatable only with frozen input, output resume state, and endpoint snapshot | `logs/hop_support_v2_27520503.out`; runner; script | High |
| A3 | Phase I, hop-support cleanup/recovery/enrichment | `src/enrichments_and_filters/*` utilities | Hop support v2 and failed-status artifacts | Joined, recovered, profile-checked, and target-enriched JSONL files under `data/processed/` and `data/archived/` | Some utilities inspect existing records; exact WDQS use depends on script | No evidence of LLM in these utilities | Mixed | Repeatable if exact inputs are frozen | File names; utility scripts; no complete command log for every derivative | Medium |
| A4 | Phase I, inverse alias candidate construction | `scripts/slurm/build_inverse_alias_topk.slurm` intended to run `build_inverse_alias_topk.py` | Relation aliases/profiles and hop support | `data/processed/wikidata_ontology.inverse_mode_aliases_topk.json` | No direct WDQS evidence | No | Deterministic if inputs and alias selection are frozen | Repeatable if runner path is corrected | `logs/build_inverse_alias_topk_27543764.out`; `src/inverse_verification_legacy/build_inverse_alias_topk.py` | Medium |
| A5 | Phase I, inverse LLM verification | `scripts/slurm/llm_classification_inv.slurm` running inverse classifier shards | `data/processed/hop_support.wikibase_item_only.jsonl`; alias top-k file | `data/processed/hop_support.wikibase_item_only.inv_llm.shard*.jsonl`; shard reports | No | Yes, configured `MODEL="gpt-4.1"` in runner | LLM/provider dependent; shard reports include many API failures | Repeatable only with frozen model/prompt and complete shard outputs | `logs/llm_classification_inv_27548189.out`; `logs/llm_classification_inv_27548189.err`; `src/inverse_verification_legacy/llm_classification_inv.py` | Low to medium |
| A6 | Phase I, domain/range compatibility for composition targets | `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py` | Hop support with target enrichment; relation profiles; properties file | `data/processed/pairs_with_compatible_targets_dom_rng_v1.jsonl`; `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.jsonl`; v3 variants | No live WDQS evidence in the documented example command | No | Deterministic if inputs are fixed | Repeatable if exact command and checkpoint state are preserved | Script comments include command; output files exist | Medium |
| A7 | Phase I, sampled composition verification v2 | `scripts/slurm/composition_range_domain_improved_min8_jsonl.slurm` running `src/composition_verification/composition_range_domain_improved.py` | `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.jsonl` | `*.composition_verified.jsonl`; compact JSONL; checkpoint; stats; report | Yes | No | Uses deterministic sample option and seed derived from relation/offset, but WDQS can drift | Repeatable with frozen WDQS responses or preserved output | `logs/composition_min8_jsonl_27683654.out`; `logs/composition_min8_jsonl_27683654.err`; stats/report files | High |
| A8 | Phase I, hop support v3 normalized rerun | `src/hop_support_and_sym_anti_verification/hop_support_v3.py` | `data/processed/hop_support_v2_before_target_enrichment_hopdiscovery_like.jsonl` | `data/processed/output_hop_support_v3_from_hop_discovery_from_json_and_support_v2_rerun.normalized.jsonl`; `data/processed/output_hop_support_v3_triplets_from_hop_discovery_from_json_and_support_v2_rerun.normalized.jsonl` | Yes | No | Not fully deterministic because live WDQS; normalized output structure is deterministic given responses | Repeatable only with frozen input and endpoint responses | `logs/normalized_hop_support_v3_rerun28049486.out` | High |
| A9 | Phase I, cancelled hop support v3 sharded branch | `scripts/job_based/shard_hop_support_v3_input.py`; shard SLURM run | `data/archived/last_quarter_of_hop_support_before_enrichment_hop_discovery_like.jsonl` | Shard manifest and partial shard outputs | Yes for shard worker | No | Same WDQS caveats | Branch appears incomplete because job was cancelled | `logs/hop_support_v3_sharded_28056979_0.out`; `logs/hop_support_v3_sharded_28056979_0.err`; `data/processed/shards/hop_support_v3_input.manifest.json` | High for cancellation |
| A10 | Phase I, composition verification v3 delta | Same composition verifier and SLURM runner configured for v3 | `data/processed/hop_support_v3/new_pairs_composition_in_v3_only.jsonl` | `data/processed/hop_support_v3/new_pairs_composition_in_v3_only.composition_verified.*`; stats/report | Yes | No | Deterministic sampling plus live WDQS drift | Repeatable with cached/frozen responses | `logs/composition_hop_support_v3_min8_jsonl_28197929.out`; `.err`; stats files | High |
| A11 | Phase I, interactive pattern analysis and allocation export | `src/statistics/hop_pattern_analysis_dashboard.py`; `src/kg_building/bidirectional_triple_allocation.py` | Hop support, inverse/composition labels, thresholds, support matrix | Allocation JSON/CSV files under `data/connectedgraph/`, `data/processed/hop_support_v3/`, and `src/Pruning graph/` | No direct WDQS evidence for allocation itself | No | Allocation algorithm is deterministic if thresholds and inputs are fixed | Repeatable if dashboard state/config is captured | Source code; allocation artifacts; no direct dashboard export log | Medium |
| B1 | Abandoned or superseded online graph construction | `src/kg_building/run_phase4_sparql_from_allocation.py` through SLURM/watch runs | Allocation JSON, live WDQS, checkpoint state | Trial graphs/checkpoints under `data/connectedgraph/trial9/` and `data/connectedgraph/hop_support_v3/` | Yes | No | Random seed exists, but online attach feasibility depends on WDQS and checkpoint state | Repeatability weak without frozen candidate responses | `logs/trial9_phase4_connectedgraph_sparql_watch_27985436.out`; `logs/trial2_hop_v3_phase4_connectedgraph_sparql_watch_28234517.out`; source | High |
| B2 | Relation-absence repair after online construction | `src/kg_building/repair_relation_allocated_absence.py` | Trial9 repaired graph; hop support archive; allocation JSON; priority/missing relation files | `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/repaired_graph.jsonl`; repair report/checkpoint | Yes | No | Has `--random_seed 13`; WDQS still drifts | Repeatable only with frozen graph/input/WDQS responses | `logs/repair_rel_alloc_abs_28220089.out`; output report | High |
| B3 | Connectivity bridge repair | `src/kg_building/repair_kg_connectivity.py` or related repair runner | Relation-absence repaired graph and candidate data | `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/repair_connectivity_top200/report.json` and repaired outputs | Yes or candidate-pool dependent; exact mode needs script-specific confirmation | No | Reported audit-safe run; live data risk if WDQS queried | Repeatable with frozen inputs/candidates | Report JSON; repair scripts; related SLURM runners | Medium to high |
| C1 | Intended Phase II offline pipeline scaffold | `src/kg_building/relation_balanced_kg_pipeline.py` | `src/kg_building/relation_balanced_kg_pipeline_config.yaml` | Stage directories if run: stage01 through stage07 | Config uses `candidate_source_mode: wdqs`, so live WDQS is configured | No | Would depend on stage and config | Execution not confirmed in workspace | Source exposes subcommands; config exists; no run log found | Low for execution, high for scaffold |
| D1 | Stage11 eta-aware connectivity repair | Generated run under `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/` | Prior graph from `/home/kg_benchmark/runs/prod_refine_20260315_180520/...` according to manifest | Stage11 repaired output and `report.json` | Unknown from manifest alone; repair script version recorded | No | Manifested production run; path is external to copied workspace | Repeatable only if source graph and config are restored | `manifest.json`; `report.json` under Stage11 folder | High |
| D2 | Stage12 path repair | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/` | Stage11 output | Stage12 repaired graph; `largest_component.csv`; reports; eta analysis | Unknown from manifest alone | No | Manifested production run | Repeatable only with original run inputs | Stage12 `manifest.json`; `report.json`; `largest_component_eta_analysis/summary.json` | High |
| D3 | Stage13 balance pruning branch sweep | `scripts/slurm/stage13_balance_prune_revised_density_aware.slurm`; pruning scripts under `src/Pruning graph/` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`; `src/Pruning graph/bidirectional_allocation_results5k.json` | Branch outputs under `src/Pruning graph/stage13_branch_sweep_20260423_160635/`; selected candidate `aggressive_but_guarded/pruned_graph.jsonl` | No evidence of WDQS in pruning stage | No | Deterministic if graph/allocation/config fixed | Repeatable with frozen inputs and exact script | `logs/stage13_prune_revised_29012090.out`; branch `summary.csv`; `summary.md` | High |

## Evidence Details For Key Runs

### Hop Discovery

Verified facts:

- The run started `2026-02-15 13:00:54` and finished `2026-02-17 03:24:56`.
- It loaded 2445 documents from the original source path `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json`.
- It selected 1703 file-mode candidates marked as `wikibase-item`.
- It completed with `scanned=1703`, `processed=1703`, `success=1140`, `not_found=51`, `errors=512`.

Evidence: `logs/hop_discovery_json_27530562.out`; `scripts/slurm/hop_discovery_json.slurm`; `src/archive/hop_discovery.py`; `data/processed/hop_discovery_from_json.jsonl`.

### Hop Support V2

Verified facts:

- The run used `src/hop_support_and_sym_anti_verification/hop_support_v2.py`.
- It loaded 1703 input documents and resumed from an existing output with 777 already-processed `r1` values.
- It queued 926 remaining records, finishing with output lines 1703 and `ok=619`, `err=307` for the queued segment.
- Runtime parameters included `chunk_size=30`, `qps=0.03`, `workers=2`, `max_inflight=1`, and `timeout=180`.

Evidence: `logs/hop_support_v2_27520503.out`; `scripts/slurm/hop_support_v2.slurm`; `src/hop_support_and_sym_anti_verification/hop_support_v2.py`.

### Composition Verification

Verified facts:

- V2 run input was `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.jsonl`.
- V2 stats show `lines_seen=22419`, `success_docs=22399`, `skipped=19`, `error_docs=1`, `saved_targets=11808`, and `sparql_posts_total=202736`.
- V3 delta run input was `data/processed/hop_support_v3/new_pairs_composition_in_v3_only.jsonl`.
- V3 stats show `lines_seen=9802`, `success_docs=9799`, `skipped=3`, `error_docs=0`, `saved_targets=1297`, and `sparql_posts_total=88199`.

Evidence: `logs/composition_min8_jsonl_27683654.out`; `logs/composition_hop_support_v3_min8_jsonl_28197929.out`; composition stats JSON files; `src/composition_verification/composition_range_domain_improved.py`.

### Allocation Exports

Evidence-based inference:

- Allocation artifacts were created from interactive pattern analysis and the allocation implementation, but direct dashboard export logs were not found.
- `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json` contains 1148 relations in the universe, 209 allocations, and 209 nonzero eta values.
- `data/connectedgraph/bidirectional_allocation_results_allsupp8_conf97_compconf90.json` contains 1469 relations in the universe and 241 allocations.
- `data/processed/hop_support_v3/bidirectional_allocation_results_hop_v3_patchedby_v2_allsup50_60sym_99anti_90inv_95comp.json` contains 1467 relations in the universe and 143 nonzero allocations.
- `src/Pruning graph/bidirectional_allocation_results5k.json` contains 1467 relations in the universe and 154 nonzero allocations.

Evidence: allocation JSON artifacts; `src/statistics/hop_pattern_analysis_dashboard.py`; `src/kg_building/bidirectional_triple_allocation.py`.

### Online Construction And Repairs

Verified facts:

- Trial9 online construction used `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json`.
- Trial2 hop-v3 online construction used `data/processed/hop_support_v3/bidirectional_allocation_results_hop_v3_patchedby_v2_allsup50_60sym_99anti_90inv_95comp.json`.
- Relation-absence repair added 178 triples, repaired 31 requested missing relations, and ended with 94 realized relations.
- Stage11 repaired 5952 of 6020 examined components and added 6705 core bridges.
- Stage12 examined 59 components, repaired 29, applied 29 paths, and added 45 triples.
- Stage12 largest-component eta analysis reports 24683 graph triples, 139 unique relations, expected eta 20000, total deficit 2019, surplus 6702, and zero relations 0.
- Stage13 April branch sweep retained weak connectivity for all listed branches; `aggressive_but_guarded` removed 460 triples and produced `pruned_graph.jsonl`.

Evidence: `logs/trial9_phase4_connectedgraph_sparql_watch_27985436.out`; `logs/trial2_hop_v3_phase4_connectedgraph_sparql_watch_28234517.out`; `logs/repair_rel_alloc_abs_28220089.out`; Stage11/12 manifests and reports; `logs/stage13_prune_revised_29012090.out`; Stage13 branch summaries.

## DAG-Like Pipeline Map

### Main Evidence-Backed Flow

```text
raw relation profiles / property metadata
  -> hop discovery from wikibase-item relation universe
  -> hop support v2
  -> cleanup, target enrichment, domain/range compatibility
  -> composition verification v2
  -> pattern analysis and allocation exports
  -> online Phase4 SPARQL construction attempts
  -> relation-absence repair
  -> connectivity repair
```

Evidence: `logs/hop_discovery_json_27530562.out`; `logs/hop_support_v2_27520503.out`; `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py`; `logs/composition_min8_jsonl_27683654.out`; allocation JSON artifacts; Phase4 and repair logs.

### V3 Evidence-Backed Branch

```text
hop support v2 converted to hop-discovery-like input
  -> hop support v3 normalized rerun
  -> v3-only composition verification
  -> hop-v3 allocation export
  -> Trial2 online Phase4 attempt
  -> checkpoint postprocess artifacts
```

Evidence: `logs/normalized_hop_support_v3_rerun28049486.out`; `logs/composition_hop_support_v3_min8_jsonl_28197929.out`; hop-v3 allocation JSON; `logs/trial2_hop_v3_phase4_connectedgraph_sparql_watch_28234517.out`; `data/connectedgraph/hop_support_v3/trial2_checkpoint_postprocess/`.

### Later Repair/Pruning Branch

```text
production refine graph outside copied workspace
  -> Stage11 eta-aware connectivity repair
  -> Stage12 path repair
  -> largest-component eta analysis
  -> Stage13 branch sweep / balance pruning
```

Evidence: Stage11/Stage12 manifests and reports under `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/`; `logs/stage13_prune_revised_29012090.out`.

### Dead-End Or Incomplete Branches

| Branch | Evidence | Status |
| --- | --- | --- |
| Hop support v3 sharded job | `logs/hop_support_v3_sharded_28056979_0.err` indicates cancellation | Dead-end or incomplete |
| Full inverse LLM classification | Shard7 log shows many OpenAI 429 insufficient-quota errors; complete shard set not proven | Incomplete or unclear |
| Online/frontier graph construction | Existing comparison note labels Trial2 online as abandoned; later Stage11/12/13 artifacts exist | Evidence-based inference: superseded |
| `relation_balanced_kg_pipeline.py` full run | Source/config exist; no matching execution logs or stage outputs found | Scaffold present, execution unclear |

