# Pipeline Reconstruction DAG

Status: evidence-first pipeline DAG draft. This document does not modify thesis LaTeX, code, graph artifacts, logs, or old pipeline scripts.

Machine-readable companion:

`docs/reconstruction/pipeline_reconstruction_dag.tsv`

## Scope

This DAG records the current end-to-end evidence chain for the thesis pipeline, from Phase I relation filtering through final B0 artifact registration. It separates:

- confirmed execution evidence,
- partial or inferred links,
- intended design that is not proven as executed,
- nonselected candidate analyses,
- final-selected artifacts.

The selected final graph is B0:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`

Final graph SHA256:

`c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`

Final artifact package:

`artifacts/final_graph/selected_final_graph/`

## High-Level DAG

```text
Phase I relation/profile evidence
  P1-01 relation-profile metadata artifact
    -> P1-02 wikibase-item relation universe filtering
    -> P1-03 empirical two-hop discovery
    -> P1-04 hop-support estimation
       -> P1-05 symmetry / anti-symmetry verification
       -> P1-06 inverse verification
       -> P1-07 composition target filtering
          -> P1-08 domain/range compatibility filtering
          -> P1-09 sampled composition shortcut verification
       -> P1-10 interactive pattern analysis / allocation export
       -> P1-11 canonical 5k allocation selected for final graph

Phase II graph evidence
  P2-01 intended offline/candidate-pool design
       (scaffold/design evidence only; full execution not confirmed)

  P2-02 abandoned online/frontier branch
       (confirmed negative branch; not final)

  P2-01a Stage3 candidate audit / Stage2 candidate shard evidence
    -> P2-01b Stage4 core graph construction
    -> P2-02a Stage5 repair delta verified empty
    -> P2-02b verified Stage6 refined graph from Hetzner archive
    -> P2-02c resolved Stage7 eta-aware filtered graph from Hetzner archive
    + P1-11 canonical allocation family
    -> P2-03 Stage11 eta-aware connectivity repair
    -> P2-04 Stage12 path repair
    -> P2-05 B0 largest-component extraction / selection
    -> P2-09 final B0 artifact registration

Post-B0 candidate analyses
  P2-05 B0
    -> P2-06 Stage13/C1 candidate analysis
    -> P2-07 C2 deletion-only candidate analysis
    -> P2-08 C3 pool/probe analysis
```

## Confirmed Final Pipeline Chain To B0

The strongest confirmed local chain to the selected final graph now includes partial Stage3-to-Stage4 evidence, Stage4 core graph construction evidence, Stage5 repair/no-op evidence, Stage6 refinement, Stage7 eta-aware filtering, and Stage11/Stage12 repair artifacts. Stage4 construction is linked to the frozen Stage2 candidate shard pool by archived pipeline code and subset checks. The Stage3 audit artifact is relation-level rather than a direct graph input, so the Stage3 -> Stage4 status is partial rather than fully confirmed. This narrows the Stage3-to-B0 gap, but it is still not a fully reproduced offline Phase II run from Phase I allocation outputs and does not establish Stage1-to-Stage2 collection reproducibility.

| Order | Node | Evidence | Status |
| ---: | --- | --- | --- |
| 1 | Canonical allocation family selected for final graph | `src/Pruning graph/bidirectional_allocation_results5k.json`; `artifacts/final_graph/selected_final_graph/final_graph_manifest.json` | Confirmed artifact, generation provenance partial |
| 2 | Stage3 audit and Stage4 candidate-pool evidence | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage03_candidate_audit/candidate_relation_audit.jsonl`; `stage02_candidates/shards/*.jsonl`; `docs/reconstruction/30_stage3_to_B0_chain_verification.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage3_to_B0_chain_verification.json` | Partial: Stage4 reads Stage2 shards directly; Stage3 audit is relation-level |
| 3 | Stage4 core graph construction | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_triples.jsonl`; `core_graph_selection_log.jsonl`; run manifest; archived pipeline script | Confirmed Stage4 artifact and Stage2-shard subset evidence |
| 4 | Stage5 repair/no-op evidence | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage05_repair/summary.json`; empty `stage05_repair/repair_triples.jsonl`; `docs/reconstruction/28_stage5_to_B0_chain_verification.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage5_to_B0_chain_verification.json` | Stage5 full graph absent, but repair delta verified empty |
| 5 | Verified Stage6 refined graph input to Stage7 | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/refined_graph_triples.jsonl`; `docs/reconstruction/27_stage6_to_B0_chain_verification.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage6_to_B0_chain_verification.json` | Locally verified Stage6 graph artifact; upstream Stage1-to-Stage2 provenance still partial |
| 6 | Resolved pre-Stage11 Stage7 graph input | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`; `docs/reconstruction/25_pre_stage11_input_mapping_hetzner_resolution.md`; `artifacts/final_graph/selected_final_graph/rebuild/path_translation_manifest.v3.json` | Resolved strong local mapping for stale absolute path |
| 7 | Stage11 eta-aware connectivity repair | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/manifest.json`; `report.json`; `events.jsonl`; `state.json` | Confirmed historical run |
| 8 | Stage12 path repair | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/manifest.json`; `report.json`; `events.jsonl`; `state.json` | Confirmed historical run |
| 9 | B0 largest component and eta audit | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`; `largest_component_eta_analysis/summary.json`; `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json` | Confirmed selected graph artifact |
| 10 | Final B0 registration | `artifacts/final_graph/selected_final_graph/final_graph_manifest.json`; `final_graph_metrics.json`; `final_graph_hashes.tsv`; `final_graph_decision.md` | Confirmed documentation-only final registration |

Important limitation: Stage11 and Stage12 manifests still contain stale absolute `/home/kg_benchmark/...` paths. The pre-Stage11 input graph is now mapped with strong evidence to the Hetzner archive copy, and `scripts/reconstruction/07_verify_stage3_to_B0_chain.sh` verifies Stage4 against the Stage2 candidate shard pool, then reuses the Stage5 -> B0 chain. This does not prove full Phase I-to-Phase II end-to-end reproducibility or Stage1-to-Stage2 candidate collection reproducibility.

## Node Table

| Stage ID | Stage name | Main scripts | Command / log evidence | Inputs | Outputs | Used in final graph decision? | Evidence strength | Reproducibility status | Gaps | Recommended action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1-01 | Relation-profile metadata artifact | `src/composition_verification/classify_relations_pipeline.py` | No production run log found | Wikidata property metadata or MongoDB collection; exact production input unclear | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` | Indirectly yes | Partial | Depends on incomplete LLM provenance | Missing production command, prompt/model/run metadata, raw responses | Create run card with prompt/model/version/input hash/output hash. |
| P1-02 | Relation universe / `wikibase-item` filtering | `src/archive/hop_discovery.py`; `scripts/slurm/hop_discovery_json.slurm` | `logs/hop_discovery_json_27530562.out` | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` | `data/processed/hop_discovery_from_json.jsonl` | Indirectly yes | Confirmed | Depends on live WDQS for rerun | Upstream profile generation partial | Keep 1,703 `wikibase-item` claim; cite log. |
| P1-03 | Empirical two-hop discovery | `src/archive/hop_discovery.py` | `logs/hop_discovery_json_27530562.out` | 1,703 `wikibase-item` relations | `data/processed/hop_discovery_from_json.jsonl` | Indirectly yes | Confirmed | Depends on live WDQS | 340k thesis claim unsupported; cached output supports 56,278 `valid_r2` entries | Correct thesis count or locate missing evidence for 340k. |
| P1-04 | Hop-support estimation | `src/hop_support_and_sym_anti_verification/hop_support_v2.py`; `hop_support_v3.py` | `logs/hop_support_v2_27520503.out`; `logs/normalized_hop_support_v3_rerun28049486.out` | Hop-discovery outputs and normalized derivatives | `data/processed/hop_support_v2.jsonl`; v3 normalized support/triplets | Indirectly yes | Confirmed | Depends on live WDQS | Endpoint drift; v2 resumed from prior output | Freeze support outputs and record exact hashes. |
| P1-05 | Symmetry / anti-symmetry verification | `src/statistics/hop_pattern_analysis_dashboard.py` | No direct export log found | Hop-support loop/non-loop/total counts | Pattern group assignments in allocation artifacts | Indirectly yes | Partial | Rerunnable from frozen inputs if dashboard state is captured | Interactive threshold/export state not fully manifested | Capture dashboard state and allocation thresholds. |
| P1-06 | Inverse verification | `src/inverse_verification_legacy/build_inverse_alias_topk.py`; `llm_classification_inv.py` | `logs/build_inverse_alias_topk_27543764.out`; `logs/llm_classification_inv_27548189.out/.err` | Relation aliases/profiles; hop support | `data/processed/wikidata_ontology.inverse_mode_aliases_topk.json`; inverse shard outputs/reports | Indirectly yes | Partial | Depends on incomplete LLM provenance | Shard completion not proven; OpenAI 429 failures in `.err` | Audit shard completion before strong inverse claims. |
| P1-07 | Composition target filtering | `src/composition_verification/classify_relations_pipeline.py` | No production run log found | Relation profile metadata | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json`; 615 `composition_target=YES` records | Indirectly yes | Partial | Depends on incomplete LLM provenance | Production LLM provenance incomplete | Describe as stored LLM-derived artifact, not fully reproducible run. |
| P1-08 | Domain/range filtering | `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py` | No direct production log found | Hop support with targets; relation profiles; properties | `data/processed/pairs_with_compatible_targets_dom_rng_v1.jsonl`; `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.jsonl`; v3 variants | Indirectly yes | Partial | Rerunnable from frozen local inputs if exact command captured | Direct command/log missing | Create command card and hash exact outputs. |
| P1-09 | Composition shortcut verification | `src/composition_verification/composition_range_domain_improved.py` | `logs/composition_min8_jsonl_27683654.out`; `logs/composition_hop_support_v3_min8_jsonl_28197929.out` | Domain/range-compatible composition candidates | Composition-verified JSONL, compact JSONL, checkpoints, stats, reports | Indirectly yes | Confirmed | Depends on live WDQS | WDQS shortcut checks can drift | Freeze verifier outputs and response caches if available. |
| P1-10 | Interactive pattern analysis / allocation | `src/statistics/hop_pattern_analysis_dashboard.py`; `src/kg_building/bidirectional_triple_allocation.py` | No direct dashboard export log found | Hop support, inverse labels, composition labels, thresholds, support matrix | Allocation JSON/CSV artifacts | Yes, through selected allocation | Partial | Rerunnable if dashboard state and inputs are captured | Multiple allocation artifacts; export command missing | Create allocation run card with selected thresholds and hashes. |
| P1-11 | Canonical allocation selected for final graph | Allocation artifact | `artifacts/final_graph/selected_final_graph/final_graph_manifest.json` | `src/Pruning graph/bidirectional_allocation_results5k.json` | Same allocation; SHA256 `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` | Yes | Confirmed artifact | Historical artifact only | Export provenance still partial; Stage11/12 manifests point to `/home/kg_benchmark/src/kg_builder/input/...` | Keep selected allocation hash; map stale path to local file. |
| P2-01 | Intended offline/candidate-pool design | `src/kg_building/relation_balanced_kg_pipeline.py`; config YAML | No matching execution log found | Allocation, support matrix, candidate source config | Stage directories would be produced if run | No direct final-chain use; thesis design only | Partial | Documentation/design only; config may use live WDQS | Config uses `candidate_source_mode: wdqs`; no offline frozen candidate-pool execution log | Keep qualified as intended design. |
| P2-01a | Stage3 candidate audit and Stage4 candidate-pool evidence | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py` | `archive/hetzner_version/runs/prod_refine_20260315_180520/manifest.json`; `stage03_candidate_audit/summary.json`; `candidate_relation_audit.jsonl`; `docs/reconstruction/30_stage3_to_B0_chain_verification.md` | Stage2 candidate shards; allocation | Stage3 relation-level audit rows; Stage4 receives Stage2 shards directly according to archived code | Yes, as partial Stage3/Stage4 evidence | Partial | Historical artifact only; Stage2 collection used WDQS | Stage3 audit is not direct h/r/t input; Stage2 collection reproducibility not proven | Treat Stage3 -> Stage4 as partial; cite Stage4 subset of Stage2 shards. |
| P2-01b | Stage4 core graph construction | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py` | Run manifest stage info; archived pipeline code; `stage04_core_graph/*`; `docs/reconstruction/30_stage3_to_B0_chain_verification.md` | `stage02_candidates/shards/*.jsonl`; allocation | `stage04_core_graph/core_graph_triples.jsonl`; `core_graph_selection_log.jsonl`; relation/component reports | Yes, as start of verified graph chain | Confirmed artifact and Stage2-shard subset evidence | Historical artifact only; upstream candidate collection may depend on WDQS | No separate Stage4-specific log found; no Stage4 manifest file besides run-level manifest | Preserve Stage4 hash and candidate-shard subset evidence; keep upstream claims bounded. |
| P2-02 | Abandoned online/frontier branch | `src/kg_building/run_phase4_sparql_from_allocation.py` | Trial9/Trial2 logs under `logs/` | Allocation JSONs, live WDQS, checkpoint state | Trial graph/checkpoint artifacts under `data/connectedgraph/` | Yes as negative evidence | Confirmed | Depends on live WDQS | Some log-referenced outputs missing; manifests differ from B0 | Use only as abandoned/superseded evidence. |
| P2-02a | Stage5 repair/no-op evidence | Stage5 repair script not fully reconstructed here | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage05_repair/summary.json`; empty `stage05_repair/repair_triples.jsonl`; `docs/reconstruction/28_stage5_to_B0_chain_verification.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage5_to_B0_chain_verification.json` | Upstream Stage4 core graph; exact Stage1-to-Stage4 chain not verified in this DAG update | Empty repair delta; no full Stage5 graph artifact found | Yes, as no-op transition evidence | Confirmed no-op repair delta; full Stage5 graph absent | Historical artifact only | No full Stage5 graph artifact; Stage1-to-Stage4 provenance not fully verified | Treat as verified empty repair stage, not as a standalone full graph output. |
| P2-02b | Stage6 refined graph from Hetzner archive | Stage6 script not fully reconstructed here; artifact verified | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/summary.json`; `docs/reconstruction/27_stage6_to_B0_chain_verification.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage6_to_B0_chain_verification.json` | Stage4 core graph plus empty Stage5 repair delta; exact Stage1-to-Stage4 chain not verified in this DAG update | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/refined_graph_triples.jsonl`; 18,513 unique triples | Yes, as Stage7 input evidence | Confirmed artifact; Stage6 no-op relative to Stage4 | Historical artifact only | Stage1-to-Stage4 provenance not fully verified | Keep as verified local artifact, not as proof of the full upstream run chain. |
| P2-02c | Stage7 eta-aware component filtering | `archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py` | `archive/hetzner_version/logs/eta_aware_component_filter_prod.out`; Stage7 manifest/summary/progress; `docs/reconstruction/31_stage7_implementation_provenance.md` | Stage6 refined graph; selected allocation family | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`; 17,965 unique triples | Yes, as Stage11 input evidence | Confirmed artifact and transition; confirmed as standalone replacement for the earlier monolithic `stage07_filtering` output | Historical artifact only | Exact shell submission script for the standalone Stage7 command is missing; rerun environment and upstream Stage4 provenance incomplete | Preserve Stage6 -> Stage7 hash relationship; keep rerun claims bounded. |
| P2-03 | Stage11 eta-aware connectivity repair | Manifest records `kg-repair-audit-safe-1.0` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/manifest.json`; `report.json`; `docs/reconstruction/25_pre_stage11_input_mapping_hetzner_resolution.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage7_to_B0_chain_verification.json` | Resolved Stage7 graph `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`; stale allocation path mapped to local allocation | `graph_output.jsonl`; `events.jsonl`; `state.json`; `report.json` | Yes | Confirmed | Historical artifact only; rerun depends on live WDQS unless query/cache behavior is fully frozen | Stage11 rerun environment/query reproducibility still incomplete | Preserve resolved Stage7 hash chain; keep rerun claims bounded. |
| P2-04 | Stage12 path repair | Manifest records `kg-path-repair-audit-safe-1.0` | `stage12_path_repair_prod/manifest.json`; `report.json` | Stale Stage11 graph path; stale allocation path | `graph_output.jsonl`; `events.jsonl`; `state.json`; `report.json` | Yes | Confirmed | Historical artifact only; rerun depends on live WDQS and stale input | External paths need local mapping | Preserve manifest/report hashes; map stale paths. |
| P2-05 | B0 largest-component extraction / selection | Extraction script not identified; evaluator is `tools/graph_candidate_evaluation/evaluate_graph_candidate.py` | Stage12 eta summary; B0 evaluator report; final graph manifest | Stage12 repaired graph; canonical allocation | `largest_component.csv`; `largest_component_eta_analysis/summary.json`; B0 evaluator report; final metrics | Yes, final selected graph | Confirmed | Historical artifact; evaluator rerunnable from frozen local inputs | Exact LCC extraction command not fully identified | Keep B0 final; add extraction provenance if found. |
| P2-06 | Stage13/C1 candidate analysis | `scripts/slurm/stage13_balance_prune_revised_density_aware.slurm`; pruning/stat scripts | `logs/stage13_prune_revised_29012090.out` | B0; canonical allocation | `stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl`; reports; summaries | Yes as nonselected comparison evidence | Confirmed | Rerunnable from frozen local inputs if scripts/env preserved | Not final; distinct from strict destructive balance-pruned ablation | Keep as post hoc candidate analysis. |
| P2-07 | C2 deletion-only candidate analysis | `tools/graph_candidate_generation/targeted_generic_dominance_prune.py`; evaluator | C2 command/config/report under `experiments/graph_candidates/C2_targeted_generic_pruning/` | B0; canonical allocation | C2 graph, generation report, evaluator report, decision | Yes as rejected exploratory evidence | Confirmed | Rerunnable from frozen local inputs | Failed surplus threshold; not final | Use as negative evidence that deletion-only pruning is insufficient. |
| P2-08 | C3 pool/probe analysis | `build_c3_replacement_pool.py`; `filter_c3_replacement_pool.py`; `probe_c3_remove_replace_feasibility.py` | Probe report under `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/` | Stage11/12 events/state; B0; allocation; eligible pool | Frozen pool, eligible subset, feasibility probe report | Yes as negative feasibility evidence; not a graph candidate | Confirmed | Documentation/evaluation only from frozen local inputs | No C3 graph generated | Use only as feasibility evidence. |
| P2-09 | Final B0 artifact registration | Documentation package; no graph-generation script | Final manifest/decision docs | B0, canonical allocation, evaluator report | `final_graph_manifest.json`; `final_graph_metrics.json`; `final_graph_hashes.tsv`; `final_graph_decision.md` | Yes | Confirmed | Documentation-only | Does not prove upstream end-to-end reproducibility | Treat final package as authoritative artifact manifest. |

## Two-Hop Pair Count Finding

The 340k claim was found in thesis/draft LaTeX files and the prior audit, but not as a supporting execution artifact:

- `docs/latex/main_v05.tex`
- `docs/latex/staged_version.tex`
- `docs/latex/working_version.tex`
- `docs/latex/all_changes.txt`
- `docs/latex/staged_changes.txt`
- `docs/reconstruction/21_thesis_claim_evidence_audit.md`

The supported cached value from `data/processed/hop_discovery_from_json.jsonl` is:

| Metric | Value | Evidence |
| --- | ---: | --- |
| JSONL rows / `r1` records | 1703 | `data/processed/hop_discovery_from_json.jsonl`; `logs/hop_discovery_json_27530562.out` |
| Success records | 1140 | Same cached JSONL and log |
| Not-found records | 51 | Same cached JSONL and log |
| Error records | 512 | Same cached JSONL and log |
| Summed `valid_r2_count` | 56278 | Direct sum over cached JSONL |

Conclusion: until a missing artifact or calculation supporting approximately 340,000 is found, thesis text should use the supported 56,278 `valid_r2` entries or avoid the numeric claim.

## Partial Or Inferred Nodes

| Node | Why partial / inferred |
| --- | --- |
| P1-01 relation-profile metadata | Artifact exists, but production command, prompt/model metadata, and raw LLM response provenance are incomplete. |
| P1-05 symmetry / anti-symmetry verification | Formulas and allocation outputs exist, but direct dashboard export state/log is incomplete. |
| P1-06 inverse verification | Alias construction is evidenced, but full inverse LLM shard completion is not proven. |
| P1-07 composition target filtering | Stored LLM-derived relation-profile artifact exists, but production LLM provenance is incomplete. |
| P1-08 domain/range filtering | Source and artifacts exist, but direct production run log is missing. |
| P1-10 interactive allocation | Allocation artifacts exist, including the final selected allocation, but exact export command and UI state are incomplete. |
| P2-01 intended offline/candidate-pool design | Scaffold and config exist; no direct run log found; config uses `candidate_source_mode: wdqs`. |
| P2-05 B0 largest-component extraction | B0 artifact and eta/evaluator reports exist; exact extraction command remains unclear. |

## Resolved Former Path-Mapping Gaps

The Stage3-to-Stage4 relationship is now partially verified:

- Stage3 audit artifact:
  `archive/hetzner_version/runs/prod_refine_20260315_180520/stage03_candidate_audit/candidate_relation_audit.jsonl`
  contains 139 relation-level audit rows and no h/r/t graph triples.
- Stage4 direct candidate input according to archived pipeline code:
  `archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards/*.jsonl`.
- Stage4 core graph:
  `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_triples.jsonl`
  has SHA256 `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd`.
- Verified relationship:
  all 18,513 Stage4 core triples are contained in the combined Stage2 candidate shard pool.
- Status:
  `partial`, because Stage3 is a relation-level audit stage and no Stage4-specific manifest/log was found that identifies the Stage3 audit JSONL as a direct h/r/t graph input.
- Evidence:
  `docs/reconstruction/30_stage3_to_B0_chain_verification.md`;
  `artifacts/final_graph/selected_final_graph/rebuild/stage3_to_B0_chain_verification.json`.

The Stage5/Stage6 transition is now locally verified in a bounded way:

- No full Stage5 graph artifact was found under:
  `archive/hetzner_version/runs/prod_refine_20260315_180520/stage05_repair/`.
- Stage5 repair delta:
  `archive/hetzner_version/runs/prod_refine_20260315_180520/stage05_repair/repair_triples.jsonl`
  is empty.
- Stage5 summary reports zero missing-relation repairs and zero component-merge repairs.
- Stage6 refinement reports zero accepted moves, zero proposals evaluated, `termination_reason=no_addition_candidates`, an empty `refinement_moves.jsonl`, and identical objective before/after.
- Stage6 refined graph is byte-identical to the Stage4 core graph.
- Evidence:
  `docs/reconstruction/28_stage5_to_B0_chain_verification.md`;
  `artifacts/final_graph/selected_final_graph/rebuild/stage5_to_B0_chain_verification.json`.

The Stage6-to-Stage7 transition is now locally verified:

- Stage6 refined graph:
  `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/refined_graph_triples.jsonl`.
- Stage7 filtered graph:
  `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`.
- Verified transition:
  18,513 unique Stage6 triples -> 17,965 unique Stage7 triples, with 548 unique triples removed.
- Evidence:
  `docs/reconstruction/27_stage6_to_B0_chain_verification.md`;
  `artifacts/final_graph/selected_final_graph/rebuild/stage6_to_B0_chain_verification.json`.

The previous stale pre-Stage11 input gap is now narrowed:

- Stale path:
  `"/home/kg_benchmark/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl"`.
- Resolved local equivalent:
  `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`.
- Resolution status: `resolved_strong`.
- Evidence:
  `docs/reconstruction/25_pre_stage11_input_mapping_hetzner_resolution.md`;
  `docs/reconstruction/26_stage7_to_B0_chain_verification.md`;
  `artifacts/final_graph/selected_final_graph/rebuild/path_translation_manifest.v3.json`;
  `artifacts/final_graph/selected_final_graph/rebuild/stage7_to_B0_chain_verification.json`.

The stale allocation path in Stage11/Stage12 manifests is mapped to:

`src/Pruning graph/bidirectional_allocation_results5k.json`

This path resolution does not solve full end-to-end reproducibility, because Phase I provenance, allocation export provenance, exact environment, and live-query behavior remain incomplete.

## Missing Evidence

1. Production provenance for `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json`.
2. Complete inverse LLM shard inventory and success/failure accounting.
3. Direct dashboard/allocation export command for `src/Pruning graph/bidirectional_allocation_results5k.json`.
4. Canonical exported support matrix linked by hash to the selected allocation and Phase II design.
5. Direct execution evidence that `src/kg_building/relation_balanced_kg_pipeline.py` produced the final B0 path.
6. Exact B0 largest-component extraction command.
7. Environment lock for exact reruns.
8. Missing artifact or calculation that supports the thesis claim of approximately 340,000 observed two-hop pairs.

## Candidates For Future Wrapper Scripts

These are documentation/planning candidates only; no wrapper scripts were created by this task.

| Candidate wrapper | Purpose |
| --- | --- |
| `scripts/run_phase1_hop_discovery_from_profiles.sh` | Capture relation-profile input hash, WDQS endpoint, command, and hop-discovery output hash. |
| `scripts/run_phase1_hop_support_v2_v3.sh` | Normalize support estimation commands and record resume state/output hashes. |
| `scripts/run_phase1_composition_verification.sh` | Bind domain/range-compatible input to composition verifier outputs and WDQS metadata. |
| `scripts/export_phase1_allocation_5k.sh` | Reproduce or document the selected allocation export with thresholds and matrix mode. |
| `scripts/audit_final_graph_B0.sh` | Re-run duplicate-safe evaluator against B0 and selected allocation. |
| `scripts/register_final_graph_manifest.sh` | Rebuild final manifest/metrics/hashes from selected graph/allocation/evaluator report without copying graph files. |

## Candidates For Future Code Refactor

These are future refactor targets only; no code was changed by this task.

| Candidate refactor | Reason |
| --- | --- |
| Separate generated artifacts from `src/Pruning graph/` | Large outputs, reports, and graphs are mixed with source-like paths. |
| Rename or wrap paths containing spaces | `src/Pruning graph/` requires careful quoting and is fragile in scripts. |
| Consolidate Phase II stage numbering | Intended eight-stage design and scaffold stage labels do not align cleanly. |
| Add manifest writing to Phase I scripts | Hop discovery/support/composition outputs need command, input hash, endpoint, and output hash metadata. |
| Add LLM provenance bundle writer | LLM filtering and inverse classification need prompt, model, temperature, schema, raw response, and output hash records. |
| Add allocation export manifest | The selected allocation needs a reproducible export record with thresholds, input files, matrix mode, and seed/tie-break behavior. |
| Add path-translation manifest for copied workspace | Stale `/home/kg_benchmark/...` paths in Stage11/12 manifests need explicit local equivalents or "not present" markers. |

## Current Thesis-Safe Interpretation

Safe:

- B0 is the selected final reported graph.
- B0 is the Stage12 repaired largest component.
- B0 metrics are supported by the final artifact package and duplicate-safe evaluator.
- Stage13/C1, C2, and C3 probe are post hoc candidate/probe analyses that did not supersede B0.
- Online/frontier construction is a confirmed negative branch, but not a formal impossibility proof.

Not safe without more evidence:

- The final graph was produced by a fully proven offline eight-stage Phase II execution.
- Full end-to-end reproducibility from raw/live inputs is solved.
- Inverse LLM verification fully completed.
- The 340k observed two-hop pair count is supported by current artifacts.
- C3 was generated as a graph candidate.
