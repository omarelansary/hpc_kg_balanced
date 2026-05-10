# Source Execution Map

Scope: read-only source-code execution map for the KG construction pipeline after the reconstruction/audit phase. This map identifies which scripts/functions correspond to Phase I, Phase II, post-hoc graph-candidate analyses, and reconstruction-only wrappers.

No WDQS query, LLM call, graph generation, artifact move/delete, or pipeline-source edit was performed while creating this document.

## Executive Summary

The clearest implemented Phase II source is the archived monolithic pipeline:

`archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py`

It implements Stage1 through Stage6 in named stage functions:

| Phase II stage | Function | Source location | Execution status |
|---|---|---|---|
| Stage1 genericity scoring | `stage_score_genericity(ctx)` / `score_genericity(...)` | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py:2128`, `:616` | Confirmed used by archived run |
| Stage2 candidate collection | `stage_collect_candidates(ctx)` / `WDQSCandidateSource` | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py:2154`, `:778` | Confirmed used; exact rerun partial because WDQS-backed |
| Stage3 candidate audit | `stage_audit_candidates(ctx)` / `audit_candidate_relation(...)` | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py:2255`, `:1166` | Confirmed relation-level audit |
| Stage4 core graph construction | `stage_construct_graph(ctx)` / `construct_core_graph(...)` | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py:2294`, `:1479` | Confirmed output, subset of Stage2 shards |
| Stage5 repair | `stage_repair_graph(ctx)` | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py:2342` | Confirmed no-op in final chain |
| Stage6 refinement | `stage_refine_graph(ctx)` | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py:2371` | Confirmed no-op in final chain |

The selected B0 chain does not use the monolithic pipeline's original Stage7 output. It uses a later standalone eta-aware Stage7 replacement:

`archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py`

The strongest verified final graph chain remains:

`Stage4 core graph -> Stage5 no-op repair -> Stage6 no-op refinement -> standalone eta-aware Stage7 -> Stage11 connectivity repair -> Stage12 path repair -> B0 largest component -> final graph package`

Evidence: `docs/reconstruction/30_stage3_to_B0_chain_verification.md`, `docs/reconstruction/31_stage7_implementation_provenance.md`, `docs/reconstruction/32_stage1_stage2_candidate_collection_provenance.md`, and `docs/reconstruction/39_final_reconstruction_status_summary.md`.

Phase I source execution is less complete. Hop discovery, hop support, empirical dashboard pattern grouping, and sampled composition shortcut verification are evidenced by scripts, logs, and cached outputs. The exact Streamlit dashboard export session and exact LLM production run/raw-response provenance are not preserved.

## Evidence Classes

| Status | Meaning |
|---|---|
| `confirmed_used` | Script/function is linked to preserved artifacts, manifests, logs, or reconstruction verification. |
| `likely_used` | Script is code-compatible and artifact-compatible, but direct command/log evidence is incomplete. |
| `side_branch` | Script/branch was run or prepared but did not feed the selected B0 final graph. |
| `historical_experimental` | Historical exploratory code or alternate experiment; useful evidence but not canonical final pipeline source. |
| `reconstruction_only` | Code created during reconstruction/audit after final graph selection; not part of historical thesis pipeline execution. |
| `unresolved` | Source role or execution status remains insufficiently evidenced. |

## Phase I Source Map

| Component | Source script/function | Methodology role | Likely inputs | Likely outputs | External dependencies | Status | Evidence | Safe thesis claim | Unsafe thesis claim |
|---|---|---|---|---|---|---|---|---|---|
| Relation profile / property metadata | `src/composition_verification/classify_relations_pipeline.py::main`, `call_llm`, Mongo update path | Produces or updates `llm_classification` labels used as upstream relation-profile evidence | MongoDB relation profile collection; property metadata | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` after export | LLM/OpenAI; MongoDB | `likely_used` | `docs/reconstruction/38_composition_llm_relation_profile_provenance_audit.md`; `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` | Stored relation-profile artifact exists and contains 615 composition `YES` labels and 1,830 `NO_WAY` labels. | Exact LLM run, prompts, model metadata, raw responses, and export manifest are preserved. |
| Relation universe / wikibase-item filtering | `src/archive/hop_discovery.py::read_input_docs`, `discover_one_r1`; runner `scripts/slurm/hop_discovery_json.slurm` | Reads relation profiles and discovers second-hop relation candidates for wikibase-item properties | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` | `data/processed/hop_discovery_from_json.jsonl` | WDQS live query | `confirmed_used` | `docs/reconstruction/35_phase1_dashboard_input_provenance.md`; `logs/hop_discovery_json_27530562.out`; `scripts/slurm/hop_discovery_json.slurm` | Cached discovery used 1,703 wikibase-item first-hop relation records and supports 56,278 summed valid second-hop relation entries. | Approximately 340,000 observed two-hop pairs are supported by current evidence. |
| Hop-support estimation v2/v3 | `src/hop_support_and_sym_anti_verification/hop_support_v2.py::compute_support_v2`; `src/hop_support_and_sym_anti_verification/hop_support_v3.py::compute_support_v2`; runners `scripts/slurm/hop_support_v2.slurm`, `scripts/slurm/hop_support_v3.slurm`, `scripts/slurm/hop_support_v3_sharded.slurm` | Computes loop, non-loop, and total support for `(r1,r2)` pairs | Hop discovery/support-normalized inputs | v2/v3 support JSONL outputs; patched v3 support family | WDQS live query | `confirmed_used` for support artifacts; final allocation input family is `likely_used` | `docs/reconstruction/35_phase1_dashboard_input_provenance.md`; `docs/reconstruction/37_dashboard_empirical_pattern_logic_audit.md`; hop-support SLURM logs | Hop support was historically computed and cached; patched v3 support is most consistent with final allocation. | Exact rerun is stable without WDQS/cache/environment caveats. |
| Symmetric / anti-symmetric / inverse empirical grouping | `src/statistics/hop_pattern_analysis_dashboard.py::load_pair_counts`, `prepare_inverse_table`, `build_pattern_groups` | Dashboard computes empirical pattern groups from support statistics | Patched v3 hop support; relation metadata | Pattern relation sets inside allocation/export | Streamlit/manual UI; optional local file inputs | `confirmed_used` for logic; export session partial | `docs/reconstruction/37_dashboard_empirical_pattern_logic_audit.md`; `docs/reconstruction/35_phase1_dashboard_input_provenance.md` | Symmetric, anti-symmetric, and inverse groups were identified empirically from hop-support statistics in the dashboard. | Completed inverse LLM classification produced the final inverse group. |
| Inverse alias construction | `src/inverse_verification_legacy/build_inverse_alias_topk.py::main`; runner `scripts/slurm/build_inverse_alias_topk.slurm` | Builds inverse-mode alias candidates for wikibase-item relations | Relation profiles, aliases, label embeddings | `data/processed/wikidata_ontology.inverse_mode_aliases_topk.json` | Local artifacts only | `confirmed_used` for side-branch artifact | `docs/reconstruction/36_inverse_verification_completion_audit.md`; `logs/build_inverse_alias_topk_27543764.out` | Inverse alias candidates were generated for 1,703 relations. | Alias candidates prove inverse relations or completed inverse verification. |
| Inverse LLM classification side branch | `src/inverse_verification_legacy/llm_classification_inv.py::main`, `call_llm`; runner `scripts/slurm/llm_classification_inv.slurm`; merge `merge_llm_classification_inv_shards.py` | Attempts sharded inverse-candidate LLM classification | Hop support wikibase-item JSONL; inverse aliases; relation profiles | Intended shard outputs and merged output, not preserved locally | LLM/OpenAI | `side_branch` / incomplete | `docs/reconstruction/36_inverse_verification_completion_audit.md`; `logs/llm_classification_inv_27548189.out`; `logs/llm_classification_inv_27548189.err` | Inverse LLM was attempted for at least shard 7 and hit quota/error conditions. | Full inverse LLM verification completed and fed the final allocation. |
| Composition LLM target filtering | `src/composition_verification/classify_relations_pipeline.py::build_user_payload`, `call_llm`, `verify_classification` | High-recall pruning of plausible composition target relations | Relation metadata in MongoDB | `llm_classification.composition.composition_target` labels later exported in relation profiles | LLM/OpenAI; MongoDB | `likely_used` | `docs/reconstruction/38_composition_llm_relation_profile_provenance_audit.md` | LLM labels were upstream pruning/profiling signals, not proof of composition. | Candidate relations were selected directly by the LLM as final composition evidence. |
| Domain/range compatible target filtering | `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py::main`; older variant `src/enrichments_and_filters/enrich_dom_range old.py` | Filters composition target candidates by domain/range compatibility | Hop-support pair rows; relation profile target labels; property constraints | `data/processed/hop_support_v3/min8_hop_support_v3_pairs_with_compatible_targets_dom_rng_v1.jsonl` | Local artifacts; older script uses MongoDB | `likely_used` / partial direct run evidence | `docs/reconstruction/38_composition_llm_relation_profile_provenance_audit.md` | A v3 compatible-target artifact exists and is compatible with the downstream composition verifier. | The exact v3 domain/range enrichment command/log is fully preserved. |
| Sampled composition shortcut verification | `src/composition_verification/composition_range_domain_improved.py::run_candidates_jsonl`, `evaluate_composition_for_doc`; runner `scripts/slurm/composition_range_domain_improved_min8_jsonl.slurm` | Samples/queries shortcut evidence for candidate `(r1,r2,r3)` composition triples | Compatible-target JSONL; v3 new-pairs input | v3 composition verified JSONL, compact JSONL, stats, report | WDQS live query; MongoDB mode also exists | `confirmed_used` | `docs/reconstruction/38_composition_llm_relation_profile_provenance_audit.md`; `logs/composition_hop_support_v3_min8_jsonl_28197929.out`; composition stats | Final composition evidence comes from sampled shortcut verification and dashboard thresholds. | LLM labels alone prove composition. |
| Dashboard allocation/export | `src/statistics/hop_pattern_analysis_dashboard.py::run_phase3_allocation`, `build_square_adjacency_matrix`, `matrix_to_nested_json_dict`; allocation helper `src/kg_building/bidirectional_triple_allocation.py` | Converts accepted pattern groups and support matrix into relation quotas and support matrix export | Patched v3 support; v3 compact composition; property metadata | `src/Pruning graph/bidirectional_allocation_results5k.json`; `genericity_support_matrix.adjacency_support.json` | Streamlit/manual UI; optional SPARQL/MongoDB Phase4 UI code exists but not final evidence | `likely_used` / partial export provenance | `docs/reconstruction/33_allocation_5k_export_provenance.md`; `docs/reconstruction/34_support_matrix_provenance.md`; `docs/reconstruction/37_dashboard_empirical_pattern_logic_audit.md` | Final 5k allocation is most consistent with patched v3 inputs and Wilson disabled. | Checked-in v2 dashboard defaults produced the final 5k allocation; exact dashboard export session is preserved. |

## Phase II Source Map

| Component | Source script/function | Methodology role | Likely inputs | Likely outputs | External dependencies | Status | Evidence | Safe thesis claim | Unsafe thesis claim |
|---|---|---|---|---|---|---|---|---|---|
| Stage1 genericity scoring | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py::stage_score_genericity`, `score_genericity` | Scores allocated relations for genericity risk | Canonical 5k allocation; genericity support matrix; ontology compatibility | `stage01_genericity/relation_genericity.jsonl`, summary | Local frozen artifacts | `confirmed_used` | `docs/reconstruction/32_stage1_stage2_candidate_collection_provenance.md`; archived run manifest | Archived Stage1 output exists and consumed canonical allocation/support matrix. | Stage1 exact rerun is proven independent of environment. |
| Stage2 candidate collection | `relation_balanced_kg_pipeline.py::stage_collect_candidates`, `build_candidate_source`, `WDQSCandidateSource`, `LocalFrozenCandidateSource` | Collects candidate triples per allocated relation | Stage1 genericity output; canonical allocation; WDQS or local candidate source | `stage02_candidates/shards/*.jsonl`, checkpoints, summary | WDQS live query in executed config | `confirmed_used`; rerun reproducibility partial | `docs/reconstruction/32_stage1_stage2_candidate_collection_provenance.md`; `archive/hetzner_version/src/kg_builder/config.yaml`; run manifest | Frozen Stage2 shards are preserved and Stage4 core triples are a subset of them. | Stage2 is exactly rerunnable from current live WDQS. |
| Stage3 candidate audit | `relation_balanced_kg_pipeline.py::stage_audit_candidates`, `audit_candidate_relation` | Audits per-relation candidate availability | Stage2 candidate shards | `stage03_candidate_audit/candidate_relation_audit.jsonl`, summary | Local frozen artifacts | `confirmed_used` for audit; direct graph input no | `docs/reconstruction/30_stage3_to_B0_chain_verification.md` | Stage3 audited relation candidate availability and preceded Stage4. | Stage3 audit JSONL is the direct h/r/t input to Stage4. |
| Stage4 core graph construction | `relation_balanced_kg_pipeline.py::stage_construct_graph`, `construct_core_graph`, `select_seed_triples`, `candidate_total_score` | Quota-aware core graph selection from candidate shards | Stage2 shards; canonical allocation | `stage04_core_graph/core_graph_triples.jsonl`, selection log, relation counts | Local frozen artifacts | `confirmed_used` | `docs/reconstruction/30_stage3_to_B0_chain_verification.md` | Stage4 core graph has 18,513 unique triples and 139 relations; it is a subset of Stage2 shards. | Stage4 can be reproduced without the archived Stage2 shards/config. |
| Stage5 repair | `relation_balanced_kg_pipeline.py::stage_repair_graph`, `realize_missing_with_unused_candidates`, `merge_components_with_allocated_candidates` | Missing relation/component repair within candidate pool | Stage4 graph; unused Stage2 candidates | Empty repair delta in final verified chain | Local frozen artifacts | `confirmed_used` no-op | `docs/reconstruction/28_stage5_to_B0_chain_verification.md` | Stage5 was verified as a no-op in the final chain. | Stage5 materially changed the final selected graph. |
| Stage6 refinement | `archive/.../relation_balanced_kg_pipeline.py::stage_refine_graph`, `refine_graph_with_local_swaps` | Local swap-based refinement | Stage5/Stage4 graph; candidate pool | `stage06_refine_graph/refined_graph_triples.jsonl` | Local frozen artifacts | `confirmed_used` no-op | `docs/reconstruction/27_stage6_to_B0_chain_verification.md`; `docs/reconstruction/28_stage5_to_B0_chain_verification.md` | Stage6 was verified as no-op and byte-identical to Stage4. | Stage6 improved the selected graph. |
| Original monolithic Stage7 | `relation_balanced_kg_pipeline.py::stage_filter_components`, `filter_weak_components` | Original component filter in monolithic pipeline | Stage6 graph | `stage07_filtering/filtered_graph_triples.jsonl` | Local frozen artifacts | `historical_experimental` for final B0 chain | `docs/reconstruction/31_stage7_implementation_provenance.md` | Original monolithic Stage7 existed and was superseded for final B0 chain. | Original Stage7 output is the Stage7 input to Stage11/B0. |
| Standalone eta-aware Stage7 replacement | `archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py::main`, `filter_components_eta_aware`, `write_outputs` | Eta-aware component filtering replacement | Stage6 refined graph; canonical 5k allocation | `stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl` | Local frozen artifacts | `confirmed_used` | `docs/reconstruction/31_stage7_implementation_provenance.md`; `docs/reconstruction/27_stage6_to_B0_chain_verification.md` | Final B0 chain uses standalone eta-aware Stage7, 17,965 unique triples. | Stage7 implementation provenance is unresolved. |
| Stage11 connectivity repair | `archive/hetzner_version/src/kg_builder/repair_kg_connectivity.py::main`, `find_one_hop_bridge`, `find_two_hop_bridge`; local analog `src/kg_building/repair_kg_connectivity.py` | Adds eta-safe bridge/core triples to connect components | Stage7 eta-aware output; canonical allocation | `stage11_eta_aware_connectivity_repair_full/graph_output.jsonl`, events, state, report | WDQS live query | `confirmed_used` for artifacts; source path inferred from manifest version/code | `docs/reconstruction/26_stage7_to_B0_chain_verification.md`; Stage11 manifest/report | Stage11 output is verified and contains Stage7 plus 6,705 added core triples. | Stage11 is part of the original eight-stage offline Phase II design. |
| Stage12 path repair | `archive/hetzner_version/src/kg_builder/repair_kg_paths.py::main`, `search_bounded_path`; local analog absent in `src/kg_building` | Adds bounded paths to repair connectivity | Stage11 graph output; canonical allocation | `stage12_path_repair_prod/graph_output.jsonl`, events, state, report | WDQS live query | `confirmed_used` for artifacts; source path inferred from script version/code | `docs/reconstruction/26_stage7_to_B0_chain_verification.md`; Stage12 manifest/report | Stage12 output contains Stage11 plus 45 added path triples. | Stage12 graph output itself is the selected final graph without LCC extraction. |
| B0 largest-component extraction/selection | Extraction command not fully isolated; evaluated by `tools/graph_candidate_evaluation/evaluate_graph_candidate.py` | Selects/evaluates Stage12 largest weak component | Stage12 graph output; canonical allocation | `largest_component.csv`; final graph manifest package | Local frozen artifacts | `confirmed_used` for artifact and metrics; exact extraction command partial | `artifacts/final_graph/selected_final_graph/final_graph_manifest.json`; `docs/reconstruction/19_final_graph_selection_decision.md` | B0 is the selected final reported graph and Stage12 repaired largest component. | Exact B0 extraction command is fully reconstructed from preserved wrapper alone. |

## Post-Hoc Candidate Analysis Source Map

| Component | Source script/function | Role | Inputs/outputs | External dependencies | Status | Evidence | Safe thesis claim | Unsafe thesis claim |
|---|---|---|---|---|---|---|---|---|
| Abandoned online/frontier SPARQL branch | `src/kg_building/run_phase4_sparql_from_allocation.py::main`, `WikidataSparqlTripleSource`; runners `scripts/slurm/phase4_connectedgraph_sparql*.slurm` | Earlier online attach/frontier graph construction attempt | Allocation JSONs, WDQS, connectedgraph outputs/checkpoints | WDQS live query | `side_branch` / superseded | `docs/reconstruction/22_pipeline_reconstruction_dag.md`; Phase4 SLURM scripts/logs | Online/frontier attempts existed and are treated as superseded by later evidence. | This branch produced the selected final graph. |
| Relation-absence repair branch | `src/kg_building/repair_relation_allocated_absence.py::main`; runners `scripts/slurm/run_repair_relation_allocated_absence.slurm`, `run_repair_apply_topk.slurm` | Tries to repair absent allocated relations before final chain | Trial9 repair artifacts and candidate pools | WDQS live query | `side_branch` | `docs/reconstruction/14_C3_replacement_pool_audit.md`; SLURM scripts | Trial9 repair candidates exist as exploratory local evidence. | Trial9 candidates are canonical C3 pool v1 or selected final graph source. |
| C1 Stage13 pruning | `src/Pruning graph/kg_balance_pruner_revised_pruning_only.py::main`; runner `scripts/slurm/stage13_balance_prune_revised_density_aware.slurm`; older `kg_balance_pruner.py` | Post-hoc surplus/density pruning candidate | B0/Stage12 graph and allocation | Local frozen artifacts | `side_branch` / not selected | `docs/reconstruction/18_final_graph_decision_state_after_C3_probe.md`; `docs/reconstruction/19_final_graph_selection_decision.md` | C1 reduced surplus modestly but increased deficit and was not selected. | Stage13/C1 is final. |
| Strict balance-pruned ablation | `src/Pruning graph/kg_balance_pruner.py`; runner `scripts/slurm/stage13_balance_prune_ablation.slurm` | Ablation/experimental pruning | Stage12 graph and allocation | Local frozen artifacts | `historical_experimental` | Stage13 ablation artifacts and SLURM script | It is an exploratory ablation. | It supersedes B0. |
| C2 targeted deletion pruning | `tools/graph_candidate_generation/targeted_generic_dominance_prune.py::main`; evaluator `tools/graph_candidate_evaluation/evaluate_graph_candidate.py` | Controlled deletion-only target-generic candidate | B0 graph; canonical allocation; C2 config | Local frozen artifacts | `reconstruction_only` / rejected candidate | `docs/reconstruction/12_C2_result_interpretation.md`; C2 reports | C2 preserved hard constraints but failed surplus threshold and is negative evidence. | C2 is final or accepted. |
| C3 replacement-pool freeze/filter/probe | `tools/graph_candidate_generation/build_c3_replacement_pool.py`, `filter_c3_replacement_pool.py`, `probe_c3_remove_replace_feasibility.py` | Controlled replacement-pool derivation and feasibility probe, no graph candidate generated | Stage11/12 events/state; B0; allocation; eligible pool | Local frozen artifacts only | `reconstruction_only` / evidence only | `docs/reconstruction/15_C3_replacement_pool_v1_freeze_report.md`; `docs/reconstruction/16_C3_eligible_replacement_pool_v1_report.md`; `docs/reconstruction/17_C3_feasibility_probe_result.md` | C3_probe_v1 is feasibility evidence; no graph was generated. | C3 was generated or should be registered as a graph candidate. |
| C3 historical remove/replace prototype | `src/Pruning graph/kg_balance_remove_replace.py::main` | Earlier/prototype remove-replace pruner using existing repair helpers | Stage12/B0-like graph and allocation | Can reuse WDQS helpers | `historical_experimental` | Source scan; not selected as controlled C3 implementation | It may inform future design. | It has been run as the accepted C3 pipeline. |

## Reconstruction/Audit Wrapper Map

| Script | Role | Inputs | Outputs | External dependencies | Status |
|---|---|---|---|---|---|
| `scripts/reconstruction/00_common.sh` | Shared shell helpers, canonical paths/hashes | None beyond repo paths | Functions for wrappers | Local only | `reconstruction_only` |
| `scripts/reconstruction/01_audit_B0_final_graph.sh` | Re-audits B0 with standard evaluator | B0 graph; canonical allocation | `B0_reaudit.report.json`, summary under rebuild | Local only | `reconstruction_only` |
| `scripts/reconstruction/02_register_B0_final_manifest.sh` | Rebuilds documentation-only final manifest/metrics/hash TSV | Existing final graph, allocation, B0 reaudit report | Rebuilt manifest files under rebuild | Local only | `reconstruction_only` |
| `scripts/reconstruction/03_path_translation_manifest.sh` | Records stale path translations | Stage11/12 stale paths; local workspace search | `path_translation_manifest.json` | Local only | `reconstruction_only` |
| `scripts/reconstruction/04_verify_stage7_to_B0_chain.sh` | Verifies Stage7 -> Stage11 -> Stage12 -> B0 chain | Stage7, Stage11, Stage12, B0 artifacts | `stage7_to_B0_chain_verification.json` | Local only | `reconstruction_only` |
| `scripts/reconstruction/05_verify_stage6_to_B0_chain.sh` | Verifies Stage6 -> Stage7 -> B0 | Stage6, Stage7, Stage11, Stage12, B0 artifacts | `stage6_to_B0_chain_verification.json` | Local only | `reconstruction_only` |
| `scripts/reconstruction/06_verify_stage5_to_B0_chain.sh` | Verifies Stage5 no-op and Stage5/6 relationship | Stage5, Stage6, downstream artifacts | `stage5_to_B0_chain_verification.json` | Local only | `reconstruction_only` |
| `scripts/reconstruction/07_verify_stage3_to_B0_chain.sh` | Verifies Stage2/3/4 relationship and Stage4 -> B0 chain | Stage2 shards, Stage3 audit, Stage4 graph, downstream artifacts | `stage3_to_B0_chain_verification.json` | Local only | `reconstruction_only` |
| `scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh` | Wrapper-only audit entrypoint over frozen artifacts | Existing reconstruction wrappers and artifacts | Runtime audit manifest | Local only | `reconstruction_only` |

## WDQS-Touching Source Files Identified

These files contain code or runners that can make live WDQS/SPARQL requests. They must not be run during frozen-artifact validation unless a new tracked experiment is explicitly intended.

| Path | Role | Status |
|---|---|---|
| `src/archive/hop_discovery.py` | Two-hop discovery | Confirmed historical Phase I |
| `src/hop_support_and_sym_anti_verification/hop_support_v2.py` | Hop-support estimation | Confirmed historical Phase I |
| `src/hop_support_and_sym_anti_verification/hop_support_v3.py` | Hop-support estimation | Confirmed historical Phase I |
| `src/composition_verification/composition_range_domain_improved.py` | Composition shortcut verification | Confirmed historical Phase I |
| `src/statistics/hop_pattern_analysis_dashboard.py` | Optional dashboard Phase4 realization via SPARQL | Manual UI / not final graph evidence |
| `src/statistics/audit_absent_allocated_relations.py` | Sampled WDQS relation-absence audit | Side branch |
| `src/statistics/extract_subgraphs_from_checkpoint.py` | Optional WDQS component expansion | Side branch |
| `src/kg_building/relation_balanced_kg_pipeline.py` | Current copy of Phase II pipeline with WDQS candidate source | Source-compatible; not primary executed artifact |
| `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py` | Archived Phase II pipeline with WDQS Stage2 source | Confirmed used |
| `src/kg_building/run_phase4_sparql_from_allocation.py` | Online/frontier graph construction | Side branch |
| `src/kg_building/repair_kg_connectivity.py` | Connectivity repair | Local analog / Stage11 source-compatible |
| `archive/hetzner_version/src/kg_builder/repair_kg_connectivity.py` | Connectivity repair | Confirmed artifact family |
| `archive/hetzner_version/src/kg_builder/repair_kg_paths.py` | Path repair | Confirmed artifact family |
| `src/kg_building/repair_relation_allocated_absence.py` | Trial repair candidate collection | Side branch |
| `src/kg_building/kg_balanced_connected_sampler_sparql.py` | Earlier connected sampler | Historical/experimental |
| `scripts/slurm/hop_discovery_json.slurm` | WDQS hop discovery runner | Confirmed historical runner |
| `scripts/slurm/hop_support*.slurm` | WDQS hop support runners | Historical runners |
| `scripts/slurm/composition_range_domain_improved_min8_jsonl.slurm` | WDQS composition verifier runner | Confirmed historical runner |
| `scripts/slurm/phase4_connectedgraph_sparql*.slurm` | Online/frontier graph construction runners | Side branch |
| `scripts/slurm/run_repair_relation_allocated_absence.slurm` | WDQS repair runner | Side branch |
| `scripts/slurm/run_repair_apply_topk.slurm` | WDQS connectivity repair runner | Side branch |

## LLM/API-Touching Source Files Identified

| Path | Role | Status |
|---|---|---|
| `src/composition_verification/classify_relations_pipeline.py` | Relation-profile LLM classifier and MongoDB updater | Likely producer; exact production run missing |
| `src/inverse_verification_legacy/llm_classification_inv.py` | Inverse LLM classifier | Side branch; completion not evidenced |
| `scripts/slurm/llm_classification_inv.slurm` | Inverse LLM SLURM array runner | Partial/failed-heavy shard evidence |

No other OpenAI/LLM-calling Python files were identified in the inspected source areas by the source scan used for this map.

## MongoDB / Manual UI Touchpoints

| Path | Touchpoint | Role |
|---|---|---|
| `src/composition_verification/classify_relations_pipeline.py` | MongoDB + OpenAI | Relation profile classification and update |
| `src/composition_verification/composition_range_domain_improved.py` | MongoDB optional mode + WDQS | Composition verification, with JSONL mode used for preserved v3 run |
| `src/enrichments_and_filters/enrich_dom_range old.py` | MongoDB | Older domain/range enrichment path |
| `src/statistics/hop_pattern_analysis_dashboard.py` | Streamlit, optional MongoDB, optional WDQS | Manual dashboard for pattern analysis/allocation/export and old Phase4 realization UI |
| `src/statistics/hop_support_dashboard.py` | Streamlit | Hop-support exploration dashboard |

## Source-Looking Untracked Files To Review Later

These files were visible as untracked source-looking files in the local workspace at inspection time. They should not be hidden blindly because some are useful thesis utilities or historical experiment scripts.

| Path | What it appears to do | Reference status | Recommendation |
|---|---|---|---|
| `scripts/compare_compatible_targets.py` | Compare compatible-target artifacts and export subsets | Not confirmed as committed pipeline source | Hold for human review |
| `scripts/extract_entity_catalog_metadata.py` | Join graph entity IDs with entity catalog metadata | Utility for reporting/figures | Hold for human review |
| `scripts/generate_trial2_discussion_figures.py` | Generate discussion figures for trial2/Phase4 analyses | Experimental figure utility | Hold local unless figures are thesis-referenced |
| `scripts/prune_graph/` | Stage13/Stage2 pruning experiment scaffolds | Historical/post-hoc pruning experiments | Hold local or external artifact storage; do not refactor yet |
| `scripts/slurm/phase4_checkpoint_postprocess_hop_support_v3_trial2.slurm` | Phase4 postprocess/visualization runner | Side branch | Hold local |
| `scripts/slurm/stage13_balance_prune.slurm` | Stage13 pruning runner | Post-hoc candidate analysis | Hold for human review |
| `scripts/slurm/stage13_balance_prune_ablation.slurm` | Strict pruning ablation runner | Historical experimental | Hold for human review |

Source-looking files already tracked after prior support commits include `docs/latex/references.bib`, `scripts/enrich_allocation_csv_with_relation_metadata.py`, `scripts/export_pattern_group_matrix.py`, `src/statistics/extract_2paths.py`, and `src/statistics/kg_pattern_stats.py`.

## Files Not To Refactor Yet

Do not rewrite these as if they were clean production modules; they are historical evidence and should remain stable until provenance archival is complete.

| Path/family | Reason |
|---|---|
| `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py` | Executed archived Phase II source for Stage1-6 evidence. |
| `archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py` | Executed standalone Stage7 replacement evidence. |
| `archive/hetzner_version/src/kg_builder/repair_kg_connectivity.py` and `repair_kg_paths.py` | Stage11/Stage12 artifact-family source evidence. |
| `src/Pruning graph/` historical pruning scripts and outputs | Post-hoc candidate and ablation evidence with paths containing spaces. |
| `src/composition_verification/classify_relations_pipeline.py` | Important but incomplete LLM provenance; refactor only after preserving current behavior. |
| `src/composition_verification/composition_range_domain_improved.py` | Historical composition verification code tied to cached v3 outputs/logs. |
| `src/hop_support_and_sym_anti_verification/hop_support_v2.py` and `hop_support_v3.py` | Historical WDQS support estimators; reruns can drift. |
| `src/inverse_verification_legacy/` | Legacy side branch with incomplete inverse LLM completion evidence. |

## Safer Future Wrapper Refactor Boundary

Safe next refactor targets are wrapper/orchestration layers that validate existing artifacts without changing scientific logic:

- `scripts/reconstruction/*.sh`
- thin source maps/manifests under `docs/reconstruction/`
- parameterized wrappers around `tools/graph_candidate_evaluation/evaluate_graph_candidate.py`
- new wrapper scripts that call historical code in dry-run/read-only validation modes only

Do not refactor historical pipeline logic, WDQS query builders, LLM prompt logic, or artifact directory layout until the thesis artifacts and provenance are archived.

## Remaining Source/Provenance Gaps

1. Exact Streamlit dashboard export session for the 5k allocation and support matrix is missing.
2. Exact LLM relation-profile production command, model metadata, raw responses, and export manifest are missing.
3. Stage2 WDQS candidate collection is preserved as frozen shards, but exact replay depends on historical WDQS/cache/environment conditions.
4. Stage11 and Stage12 artifact families are verified; exact shell command files are incomplete, although manifests and code-compatible scripts exist.
5. Exact B0 largest-component extraction command remains less explicit than the graph identity and evaluator metrics.
6. Some source-looking pruning and reporting utilities remain untracked and need human review before commit or local exclusion.
