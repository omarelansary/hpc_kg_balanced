# Intended Phase Mapping

## Status Legend

| Status | Meaning |
| --- | --- |
| Confirmed | Direct evidence supports the intended step. |
| Partially confirmed | Some required behavior exists, but execution, completeness, or exact integration is incomplete. |
| Not found | No supporting evidence found in the current workspace. |
| Contradicted | Evidence conflicts with the intended description. |
| Superseded | Evidence shows an earlier path was replaced or abandoned by later artifacts. |
| Optional | Evidence shows the step ran, but it should not be treated as native main flow without a thesis decision. |
| Unclear | Evidence is insufficient or conflicting. |

## Phase I Mapping

| Intended Abstract Step | Actual Script(s) / Folder(s) | Actual Inputs | Actual Outputs | Evidence | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Relation universe selection: wikibase-item properties only | `src/archive/hop_discovery.py`; `scripts/slurm/hop_discovery_json.slurm` | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` | 1703 candidate relations processed into `data/processed/hop_discovery_from_json.jsonl` | `logs/hop_discovery_json_27530562.out` says `File mode candidates (wikibase-item): 1703` | Confirmed | The relation profile JSON generation itself remains unclear. |
| Empirical two-hop discovery | `src/archive/hop_discovery.py` | 1703 wikibase-item candidates | Observed `(r1, r2)` discovery records | `logs/hop_discovery_json_27530562.out`; output JSONL | Confirmed | Live WDQS failures were frequent: 512 error records reported. |
| Hop-support estimation | `src/hop_support_and_sym_anti_verification/hop_support_v2.py`; `src/hop_support_and_sym_anti_verification/hop_support_v3.py` | Hop discovery inputs and normalized derivatives | `hop_support_v2.jsonl`; enriched support files; v3 normalized support/triplets | `logs/hop_support_v2_27520503.out`; `logs/normalized_hop_support_v3_rerun28049486.out` | Confirmed | v2 and v3 both query live WDQS. |
| Branch A: symmetry verification | Hop support support metrics; dashboard analysis | Hop support JSONL with loop/non-loop/total support | Pattern groups and allocation categories | `src/statistics/hop_pattern_analysis_dashboard.py`; allocation JSON group summaries | Partially confirmed | Group outputs exist, but direct export command is not logged. |
| Branch A: anti-symmetry verification | Same as above | Same as above | Anti-symmetric group allocations | Allocation JSON artifacts include anti-symmetric group counts | Partially confirmed | Thresholds are embedded in artifact names and dashboard state, not in a separate manifest. |
| Branch A: inversion verification | `src/inverse_verification_legacy/build_inverse_alias_topk.py`; `src/inverse_verification_legacy/llm_classification_inv.py` | Hop support, alias/property metadata | `wikidata_ontology.inverse_mode_aliases_topk.json`; inverse LLM shard outputs/reports | `logs/build_inverse_alias_topk_27543764.out`; `logs/llm_classification_inv_27548189.out/.err` | Partially confirmed | Inverse alias construction is stronger evidence than full inverse LLM completion; shard log shows many 429 errors. |
| Branch B: composition candidate creation | Domain/range enrichment and composition verifier inputs | Hop-support pairs plus target relation profiles | Compatible-target JSONL and min-support JSONL | `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py`; output files | Partially confirmed | Exact production command is present as script comment, but no direct run log was found. |
| Branch B: LLM target filtering for `r3` | `src/composition_verification/classify_relations_pipeline.py` | Relation/property metadata | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` | Script source; raw output file; hop discovery log consumes this file | Partially confirmed | The production LLM run log and exact model metadata for this artifact were not found. |
| Branch B: domain/range compatibility | `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py` | Hop support with targets; relation profiles; properties | `pairs_with_compatible_targets_dom_rng_v1.jsonl`; `min8_hop_support_v2_with_compatible_targets_dom_rng_v1.jsonl` | Script comments and output artifacts | Partially confirmed | Deterministic if exact inputs are frozen. |
| Branch B: sampled shortcut verification | `src/composition_verification/composition_range_domain_improved.py` | Domain/range-compatible min-support pairs | Composition-verified JSONL, compact JSONL, checkpoint, stats, report | `logs/composition_min8_jsonl_27683654.out`; `logs/composition_hop_support_v3_min8_jsonl_28197929.out` | Confirmed | V2 and v3 runs are both directly evidenced. |
| Optional Wilson lower bound | `src/statistics/hop_pattern_analysis_dashboard.py` | Composition/pattern records | Dashboard-level Wilson-filter columns and UI | Source search for `wilson_interval`, `wilson_lower_bound`, `Use Wilson filter` | Partially confirmed | Implemented in dashboard analysis, not confirmed as part of composition verifier output. |
| Interactive pattern analysis | `src/statistics/hop_pattern_analysis_dashboard.py` | Hop-support, inverse, composition, thresholds | Accepted candidates, relation groups, allocation UI exports | Dashboard source; allocation artifacts | Partially confirmed | Interactive state is not fully manifested. |
| Accepted candidates and relation groups | Allocation JSON files | Filtered pattern groups | `pattern_groups` and relation-group summaries in allocation artifacts | Allocation JSON artifacts under `data/connectedgraph/`, `data/processed/hop_support_v3/`, and `src/Pruning graph/` | Confirmed as artifacts, medium for exact generation |
| Relation-level allocation | `src/kg_building/bidirectional_triple_allocation.py`; dashboard | Pattern groups and eta settings | Allocation JSON/CSV with eta values | Allocation artifacts; source implementation | Partially confirmed | Direct run/export command not found. |
| Support matrix export | Dashboard/export utilities | Filtered hop-support pairs | Pattern/support matrix CSV/JSON artifacts | `scripts/export_pattern_group_matrix.py`; allocation matrix CSV files; dashboard source | Partially confirmed | Exact canonical matrix needs human selection. |
| Eta quotas `eta_r` | Allocation JSON artifacts | Pattern groups and eta-per-group settings | Per-relation allocations in JSON/CSV | `data/connectedgraph/bidirectional_allocation_results_*.json`; `src/Pruning graph/bidirectional_allocation_results5k.json` | Confirmed as artifacts | Canonical thesis allocation is uncertain between multiple candidates. |

## Phase II Mapping

| Intended Abstract Step | Actual Script(s) / Folder(s) | Actual Inputs | Actual Outputs | Evidence | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Phase II input: allocated relations, eta quotas, support matrix | Allocation JSON/CSV artifacts; support matrix artifacts | Allocations and support data | Inputs for graph construction attempts | Allocation files and Phase4 logs | Partially confirmed | Several allocation artifacts exist; canonical input needs human confirmation. |
| Stage 1: Genericity scoring | `src/kg_building/relation_balanced_kg_pipeline.py`; config references support matrix | Allocation/config/support matrix | `stage01_genericity` if pipeline is run | Source subcommands and config | Partially confirmed | Scaffold exists; execution not confirmed. |
| Stage 2: Candidate collection | `relation_balanced_kg_pipeline.py` | Allocation and candidate source | `stage02_candidate_collection` if run | Source; `relation_balanced_kg_pipeline_config.yaml` | Contradicted in part | Config uses `candidate_source_mode: wdqs` and `candidate_input_path: null`, so offline frozen candidate-pool execution is not proven. |
| Stage 3: Candidate audit | `relation_balanced_kg_pipeline.py` | Candidate collection output | `stage03_candidate_audit` if run | Source subcommands | Partially confirmed | No run log found. |
| Stage 4: Core graph construction | `relation_balanced_kg_pipeline.py`; older `run_phase4_sparql_from_allocation.py` | Allocation and candidate data or live WDQS | Constructed graph outputs | Source; online Phase4 logs | Partially confirmed / superseded | Confirmed actual online construction exists; offline quota-aware construction run is unclear. |
| Stage 5: Repair | `relation_balanced_kg_pipeline.py`; `repair_relation_allocated_absence.py`; `repair_kg_connectivity.py` | Constructed graph, hop support, allocation | Repaired graphs/reports | Repair logs and reports | Confirmed for post-online repair; unclear for scaffold stage | Actual repair path may not match intended native Stage 5. |
| Stage 6: Refinement | Intended local swap-based improvement | Unclear | Unclear | No direct evidence identified in confirmed logs | Not found / unclear | Related pruning/refinement scripts exist but exact intended Stage 6 mapping is not confirmed. |
| Stage 7: Allocation-aware component filtering | `relation_balanced_kg_pipeline.py`; Stage12 largest-component analysis | Graph and allocation | Largest component and eta analysis | Source scaffold; Stage12 summary | Partially confirmed | Stage12 largest component exists; allocation-aware small-component retention policy needs source/run confirmation. |
| Stage 8: Final audit | `relation_balanced_kg_pipeline.py`; Stage12 eta analysis; Stage13 summaries | Final or candidate graph and allocation | Final audit reports, relation fulfillment, connectivity diagnostics | `largest_component_eta_analysis/summary.json`; Stage13 `summary.csv`/`summary.md` | Partially confirmed | Scaffold labels final audit as `stage07_final_audit`, not Stage 8. |
| Abandoned online/frontier SPARQL attempt | `src/kg_building/run_phase4_sparql_from_allocation.py` | Allocation JSON and WDQS | Trial9 and Trial2 online graph artifacts | Phase4 logs; checkpoint postprocess; existing comparison note | Confirmed and superseded | Treat as abandoned/superseded unless thesis chooses to discuss as negative result. |
| Optional post-pipeline connectivity repair | Stage11 and Stage12 folders under `src/Pruning graph/` | Production refine graph outside copied workspace | Repaired graph, largest component, eta summary | Stage11/12 manifests and reports | Confirmed, optional | Ran in practice, but should not automatically be treated as native main stage without thesis decision. |
| Stage13 balance pruning | `scripts/slurm/stage13_balance_prune_revised_density_aware.slurm`; pruning scripts | Stage12 largest component and 5k allocation | Branch sweep outputs and pruned graph | `logs/stage13_prune_revised_29012090.out`; branch summary files | Confirmed, optional or final-candidate | Strong reportable candidate, but final thesis selection needs human confirmation. |

## Specific Checks Requested

| Check | Finding | Evidence | Status |
| --- | --- | --- | --- |
| Where wikibase-item universe is defined/produced | Hop discovery file-mode candidate filter selected 1703 wikibase-item properties from relation profiles | `logs/hop_discovery_json_27530562.out` | Confirmed |
| Where empirical two-hop discovery happens | `src/archive/hop_discovery.py` through `scripts/slurm/hop_discovery_json.slurm` | Hop discovery log and output JSONL | Confirmed |
| Where hop support is computed | `hop_support_v2.py` and `hop_support_v3.py` | Hop support logs | Confirmed |
| Where symmetry, anti-symmetry, inversion are verified | Symmetry/anti-symmetry in dashboard/allocation analysis; inverse in legacy inverse scripts | Dashboard source; allocation group counts; inverse logs | Partially confirmed |
| Where composition candidates are created, filtered, verified | Domain/range enrichment plus composition verifier | Enrichment script; composition logs | Confirmed for verifier, medium for enrichment |
| Where LLM target filtering occurs | `classify_relations_pipeline.py` | Source and consumed relation-profile artifact | Partially confirmed |
| Where domain/range compatibility is checked | `enrich_pairs_with_targets_dom_rng_based.py` | Script command comment; output artifacts | Partially confirmed |
| Where sampled shortcut verification occurs | `composition_range_domain_improved.py` | V2 and v3 composition logs | Confirmed |
| Whether Wilson lower bound is implemented | Dashboard only | `src/statistics/hop_pattern_analysis_dashboard.py` | Partially confirmed, not pipeline-core confirmed |
| Where accepted candidates/groups are stored | Allocation JSON artifacts | Allocation files | Confirmed as artifacts |
| Where allocation happens | Dashboard plus `bidirectional_triple_allocation.py` | Source and allocation files | Partially confirmed |
| Where support matrix is exported | Dashboard/export utility and matrix CSV artifacts | `scripts/export_pattern_group_matrix.py`; allocation matrix CSVs | Partially confirmed |
| Where eta quotas are produced | Allocation JSON/CSV artifacts | Allocation files | Confirmed as artifacts |
| Where Phase II Stage 1-8 scripts live | `relation_balanced_kg_pipeline.py` scaffold | Source/config | Partially confirmed, execution unclear |
| Where abandoned online/frontier SPARQL attempt exists | `run_phase4_sparql_from_allocation.py`; Trial9/Trial2 logs | Phase4 logs | Confirmed |
| Which post-pipeline repairs actually ran | Relation-absence repair, connectivity repair, Stage11, Stage12 | Logs/reports/manifests | Confirmed |
| Which outputs appear final/reportable | Stage12 largest component eta analysis and Stage13 April branch sweep outputs | Summary/report artifacts | Medium | Human selection still needed. |

