# Final Reconstruction Status Summary

Scope: consolidated thesis-pipeline reconstruction status based on the R2 evidence documents and rebuild JSON files under `artifacts/final_graph/selected_final_graph/rebuild/`. No WDQS query, LLM call, graph generation, or graph-artifact mutation is part of this summary.

## 1. Executive Status

| Question | Status | Evidence |
|---|---|---|
| Is B0 final graph identity confirmed? | Confirmed | `artifacts/final_graph/selected_final_graph/rebuild/final_graph_manifest.rebuilt.json`; `artifacts/final_graph/selected_final_graph/rebuild/final_graph_metrics.rebuilt.json`; `artifacts/final_graph/selected_final_graph/final_graph_decision.md` |
| Is the Stage4-to-B0 chain verified? | Confirmed | `docs/reconstruction/26_stage7_to_B0_chain_verification.md`; `docs/reconstruction/27_stage6_to_B0_chain_verification.md`; `docs/reconstruction/28_stage5_to_B0_chain_verification.md`; `docs/reconstruction/30_stage3_to_B0_chain_verification.md` |
| Is Stage1/Stage2-to-Stage4 provenance confirmed? | Partial | `docs/reconstruction/32_stage1_stage2_candidate_collection_provenance.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage1_stage2_candidate_collection_provenance.json`; `artifacts/final_graph/selected_final_graph/rebuild/stage3_to_B0_chain_verification.json` |
| Is Phase I-to-allocation provenance confirmed? | Partial | `docs/reconstruction/33_allocation_5k_export_provenance.md`; `docs/reconstruction/34_support_matrix_provenance.md`; `docs/reconstruction/35_phase1_dashboard_input_provenance.md`; `docs/reconstruction/37_dashboard_empirical_pattern_logic_audit.md`; `docs/reconstruction/38_composition_llm_relation_profile_provenance_audit.md` |
| Is full end-to-end reproducibility established? | No | Missing exact dashboard export session, exact LLM production run/raw responses, complete environment lock, Stage2 WDQS/cache replay evidence, and same-run allocation/support-matrix export manifest. |

The strongest verified graph chain starts at the archived Stage4 core graph and continues through final B0 registration. Upstream Phase I artifacts and Phase II Stage1/Stage2 artifacts are strong cached evidence, but they do not yet establish a fully replayable end-to-end run from live Wikidata/LLM inputs to B0.

## 2. Final Verified Chain Table

| Component ID | Component | Status | Evidence files | Main artifacts and hashes | Safe to claim | Unsafe to claim | Remaining gap |
|---|---|---|---|---|---|---|---|
| P1_REL_PROFILE | Relation-profile artifact | partial | `docs/reconstruction/38_composition_llm_relation_profile_provenance_audit.md`; `artifacts/final_graph/selected_final_graph/rebuild/composition_llm_relation_profile_provenance_audit.json` | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json`, SHA256 `a30635f0edc66c46b8aafe66fa01e047a65c2c8d01091be8f02926af8d952258`; 2,445 records; composition `YES=615`, `NO_WAY=1830` | A stored LLM-derived profile artifact exists and was used as upstream high-recall composition-target pruning evidence. | Exact LLM run is fully reproducible from preserved prompt/model/raw responses. | Exact production command/log, raw responses, model metadata, and export manifest are missing. |
| P1_HOP_DISCOVERY | Two-hop discovery | confirmed | `docs/reconstruction/35_phase1_dashboard_input_provenance.md`; `artifacts/final_graph/selected_final_graph/rebuild/phase1_dashboard_input_provenance.json`; `logs/hop_discovery_json_27530562.out` | `data/processed/hop_discovery_from_json.jsonl`; 1,703 first-hop records; 56,278 summed valid second-hop relation entries | Empirical discovery was performed over cached wikibase-item relations and produced 56,278 summed valid second-hop entries in the preserved artifact. | Approximately 340,000 observed two-hop pairs are supported by current artifacts. | If 340,000 is needed, a separate missing artifact or metric definition must be found. |
| P1_HOP_SUPPORT_V3 | Hop-support patched v3 | partial | `docs/reconstruction/35_phase1_dashboard_input_provenance.md`; `docs/reconstruction/37_dashboard_empirical_pattern_logic_audit.md` | `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl`; final allocation input family inferred from relation-set reproduction | Patched v3 hop support is the input family most consistent with the canonical 5k allocation. | The exact dashboard export session from this input was preserved. | Export session, widget state, and same-run manifest are missing. |
| P1_PATTERN_DASHBOARD | Dashboard empirical pattern grouping | confirmed | `docs/reconstruction/37_dashboard_empirical_pattern_logic_audit.md`; `artifacts/final_graph/selected_final_graph/rebuild/dashboard_empirical_pattern_logic_audit.json` | Reproduced group sizes: symmetric `18`, anti_symmetric `66`, inverse `44`, composition `26`; canonical allocation SHA256 `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` | Symmetric, anti-symmetric, and inverse groups are empirically identified from hop-support statistics; patched v3 support plus v3 compact composition reproduces the canonical pattern relation sets with Wilson disabled. | These groups are logical Wikidata axioms or completed inverse LLM classifications. | Exact Streamlit export session is missing. |
| P1_COMP_LLM | Composition LLM target filtering | partial | `docs/reconstruction/38_composition_llm_relation_profile_provenance_audit.md`; `src/composition_verification/classify_relations_pipeline.py` | Profile artifact above; code-compatible producer script `src/composition_verification/classify_relations_pipeline.py` | LLM labels were upstream high-recall pruning/profiling signals; 615 targets were retained and 1,830 were labelled `NO_WAY`. | LLM labels prove composition. | Exact LLM production run and raw-response archive are missing. |
| P1_DOM_RNG | Domain/range filtering | partial | `docs/reconstruction/38_composition_llm_relation_profile_provenance_audit.md`; `artifacts/final_graph/selected_final_graph/rebuild/composition_llm_relation_profile_provenance_audit.json` | `data/processed/hop_support_v3/min8_hop_support_v3_pairs_with_compatible_targets_dom_rng_v1.jsonl`, SHA256 `6f9bc2b6c2d0ec344a6603137f464436eb3bb541f8aba66a200d4698f4b75ec9`; 63,992 rows | A v3 compatible-target artifact exists and supports composition candidate preparation. | The exact v3 domain/range enrichment command/log is preserved. | Direct v3 enrichment command/log is incomplete. |
| P1_COMP_SHORTCUT | Composition shortcut verification | confirmed | `docs/reconstruction/38_composition_llm_relation_profile_provenance_audit.md`; `logs/composition_hop_support_v3_min8_jsonl_28197929.out` | v3 compact output `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl`, SHA256 `8fbc1db6847b7676c1f144521218b444e2768cb06345d1a6288afd58177df54e`; 9,802 rows | Final composition evidence comes from sampled shortcut verification and dashboard thresholds. | Upstream LLM target labels are sufficient proof of composition. | Live WDQS replay is not established; cached outputs are the defensible evidence. |
| P1_ALLOC_5K | 5k allocation export | partial | `docs/reconstruction/33_allocation_5k_export_provenance.md`; `artifacts/final_graph/selected_final_graph/rebuild/allocation_5k_export_provenance.json` | `src/Pruning graph/bidirectional_allocation_results5k.json`, SHA256 `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`; 154 allocation rows; 139 merged positive-eta relations; eta sum 20,000 | This is the canonical allocation consumed by selected B0 Phase II evidence. | The exact dashboard export command/session is preserved. | Direct export command/log and saved dashboard state are missing. |
| P1_SUPPORT_MATRIX | Support matrix export | partial | `docs/reconstruction/34_support_matrix_provenance.md`; `artifacts/final_graph/selected_final_graph/rebuild/support_matrix_provenance.json` | `archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json`, SHA256 `75794511aaa9ef72a7c63fd0d9a3c11969b72c4fa4bfb01237859b612f544041`; outer relation count `139`; nonzero cells `831` | Stage1 genericity scoring used a sparse adjacency-support matrix whose row set matches the 139 allocated relations. | The support matrix and allocation are cryptographically linked by a same-run dashboard manifest. | Same-run export linkage to the allocation is missing. |
| P2_STAGE1 | Phase II Stage1 genericity | confirmed | `docs/reconstruction/32_stage1_stage2_candidate_collection_provenance.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage1_stage2_candidate_collection_provenance.json` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage01_genericity/relation_genericity.jsonl`, SHA256 `d7b47683ecd08574f1d8fc8e97a213a0fd8f1b096b5f1bf7d71956df8387ca32`; 139 rows; high-genericity `P31`, `P279`, `P131` | Archived Stage1 genericity outputs exist and consumed the canonical allocation/support-matrix inputs. | Stage1 can be rerun exactly without environment/cache reconstruction. | Full replay environment is incomplete. |
| P2_STAGE2 | Phase II Stage2 candidate collection | partial | `docs/reconstruction/32_stage1_stage2_candidate_collection_provenance.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage1_stage2_candidate_collection_provenance.json` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards`; 139 shard files; 81,958 candidates; aggregate manifest SHA256 `5dad26e9bf51e67ad8c1a8b3df85a836bebbe9d0a63652b62a2aff1cf4af014c` | Frozen Stage2 candidate shards are preserved and Stage4 core triples are a subset of the combined shard pool. | Stage2 is exactly rerunnable against current WDQS with identical output. | Stage2 used WDQS; endpoint/cache/environment provenance limits exact replay. |
| P2_STAGE3 | Stage3 audit | partial | `docs/reconstruction/30_stage3_to_B0_chain_verification.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage3_to_B0_chain_verification.json` | Stage3 audit artifacts exist; Stage3 audit is relation-level and contains no direct h/r/t triples | Stage3 preceded Stage4 in the archived pipeline and audited relation candidate availability. | Stage3 artifact is the direct graph-triple input to Stage4. | Stage4 reads Stage2 shards directly; Stage3-to-Stage4 is partial by design. |
| P2_STAGE4 | Stage4 core graph | confirmed | `docs/reconstruction/30_stage3_to_B0_chain_verification.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage3_to_B0_chain_verification.json` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/core_graph_triples.jsonl`, SHA256 `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd`; 18,513 unique triples; 139 relations | Stage4 core graph is locally verified and is a subset of the Stage2 candidate shard pool. | Stage4 selection can be reproduced without the archived Stage2 shards and configs. | Full replay still needs wrapper/environment work. |
| P2_STAGE5 | Stage5 repair | confirmed | `docs/reconstruction/28_stage5_to_B0_chain_verification.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage5_to_B0_chain_verification.json` | `stage05_repair/repair_triples.jsonl` has zero rows; Stage5 summary reports zero repairs | Stage5 repair was a verified no-op relative to the Stage4/Stage6 graph chain. | A separate full Stage5 graph artifact exists and changes the graph. | No full Stage5 graph artifact was found; no-op is verified through empty delta and summaries. |
| P2_STAGE6 | Stage6 refinement | confirmed | `docs/reconstruction/27_stage6_to_B0_chain_verification.md`; `docs/reconstruction/28_stage5_to_B0_chain_verification.md` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/refined_graph_triples.jsonl`, SHA256 `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd`; byte-identical to Stage4 | Stage6 refinement was a verified no-op: zero accepted moves and unchanged objective. | Stage6 improved or changed the graph. | None for Stage6-to-B0; upstream replay remains partial. |
| P2_STAGE7 | Standalone eta-aware Stage7 | confirmed | `docs/reconstruction/31_stage7_implementation_provenance.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage7_implementation_provenance.json`; `docs/reconstruction/27_stage6_to_B0_chain_verification.md` | `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`, SHA256 `c7d5132bd0b20aa0da4a64ecbf183abf412c3effca38bef84105c7791126fb4b`; 17,965 unique triples | The B0 chain uses the standalone eta-aware Stage7 replacement, not only the monolithic pipeline's original Stage7. | Stage7 implementation status is unresolved. | Exact standalone script preservation is confirmed in evidence docs; full upstream replay still partial. |
| P2_STAGE11 | Stage11 connectivity repair | confirmed | `docs/reconstruction/26_stage7_to_B0_chain_verification.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage7_to_B0_chain_verification.json` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl`, SHA256 `73bc624bf9147b0bba4962ab286648bcfeeb931a94a1d1a727839f160b35ada5`; 24,670 unique triples; 6,705 added core triples | Stage11 output contains Stage7 plus added core triples and preserves 139 relations. | Stage11 is native to the original eight-stage Phase II design. | Historical repair is verified; design classification should remain post-pipeline/repair wording. |
| P2_STAGE12 | Stage12 path repair | confirmed | `docs/reconstruction/26_stage7_to_B0_chain_verification.md`; `artifacts/final_graph/selected_final_graph/rebuild/stage7_to_B0_chain_verification.json` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/graph_output.jsonl`, SHA256 `89ec9bf9c8932962fd3d966073b51f76345666eda5ed5d9beb18659d02e294b0`; 24,715 unique triples; 45 added path triples | Stage12 output contains Stage11 plus path-repair triples. | Stage12 alone is the selected final artifact. | Selected final is B0 largest component extracted from Stage12. |
| P2_B0 | B0 largest-component extraction/selection | confirmed | `artifacts/final_graph/selected_final_graph/rebuild/final_graph_manifest.rebuilt.json`; `artifacts/final_graph/selected_final_graph/rebuild/final_graph_metrics.rebuilt.json`; `docs/reconstruction/19_final_graph_selection_decision.md` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`, SHA256 `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`; 24,683 unique triples; 21,893 entities; 139 relations; one weak component | B0 is the selected final reported graph and Stage12 repaired largest component. | C1, C2, or C3 superseded B0. | None for final identity; upstream full rerun remains incomplete. |
| CANDIDATES | C1/C2/C3 candidate analyses | rejected | `docs/reconstruction/12_C2_result_interpretation.md`; `docs/reconstruction/17_C3_feasibility_probe_result.md`; `docs/reconstruction/18_final_graph_decision_state_after_C3_probe.md`; `docs/reconstruction/19_final_graph_selection_decision.md` | C1: surplus `6582`, deficit `2359`; C2: surplus `6675`, deficit `2019`, 27 accepted deletions; C3 probe: no graph generated, 0 of 473 connectivity-critical targets rescued | C1/C2/C3 are post hoc candidate analyses that did not supersede B0. | C3 was generated, or C2/C3 are final candidates. | Relation addition and better replacement-pool design remain future work. |
| FINAL_PACKAGE | Final graph manifest package | confirmed | `artifacts/final_graph/selected_final_graph/final_graph_manifest.json`; `artifacts/final_graph/selected_final_graph/final_graph_decision.md`; rebuild files under `artifacts/final_graph/selected_final_graph/rebuild/` | Selected graph hash `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`; allocation hash `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` | The final artifact package records selected graph identity, metrics, hashes, and nonselected candidates. | The final package proves full Phase I-to-final reproducibility. | Package is final-artifact registration, not complete end-to-end rerun proof. |

## 3. Verified Final B0 Chain

The strongest confirmed chain is:

`Stage4 core graph`
`-> Stage5 no-op repair`
`-> Stage6 no-op refinement`
`-> standalone eta-aware Stage7 replacement`
`-> Stage11 connectivity repair`
`-> Stage12 path repair`
`-> B0 largest component`
`-> final graph package`

Concrete checks:

- Stage4 core graph has 18,513 unique triples and SHA256 `54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd`.
- Stage5 repair is verified as an empty repair delta.
- Stage6 refined graph is byte-identical to Stage4.
- Stage7 filtered graph has 17,965 unique triples and SHA256 `c7d5132bd0b20aa0da4a64ecbf183abf412c3effca38bef84105c7791126fb4b`.
- Stage11 output has 24,670 unique triples; Stage11 minus Stage7 equals 6,705 added core triples.
- Stage12 output has 24,715 unique triples; Stage12 minus Stage11 equals 45 added path triples.
- B0 has 24,683 unique triples and is a subset of Stage12 graph output.

Stage1/Stage2 candidate collection and Stage4 selection are partially verified:

- Stage2 shard pool is frozen and contains 81,958 candidates across 139 relation shards.
- Stage4 core triples are a subset of the Stage2 shard pool.
- Stage2 used WDQS-backed collection, so exact rerun reproducibility is limited by endpoint/cache/environment provenance.

## 4. Phase I Status

- Dashboard empirical pattern logic is confirmed by `docs/reconstruction/37_dashboard_empirical_pattern_logic_audit.md`.
- Patched v3 support plus v3 compact composition output with Wilson disabled reproduces the final 5k allocation pattern relation sets:
  - symmetric = 18
  - anti_symmetric = 66
  - inverse = 44
  - composition = 26
- The 340k two-hop claim is unsupported by current evidence.
- The supported cached value is 56,278 summed valid second-hop relation entries from `data/processed/hop_discovery_from_json.jsonl`.
- Inverse LLM completion is not evidenced.
- Empirical inverse grouping is supported and distinct from inverse LLM verification.
- Composition LLM target filtering is artifact-confirmed: 615 plausible composition targets retained and 1,830 labelled `NO_WAY`.
- Exact composition LLM production provenance is incomplete: no raw LLM responses, production model metadata, or export manifest were found.
- Shortcut verification is confirmed by preserved v3 logs/stats/outputs and is the final evidence for composition grouping.

## 5. Final Graph Decision Status

B0 is the selected final graph.

| Candidate | Status | Decision evidence | Main result |
|---|---|---|---|
| B0 | selected final graph | `artifacts/final_graph/selected_final_graph/final_graph_decision.md` | 24,683 unique triples, 139 relations, one weak component, deficit 2,019, surplus 6,702 |
| C1 | not selected | `docs/reconstruction/19_final_graph_selection_decision.md`; `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json` | Lower surplus than B0 but higher deficit: surplus 6,582, deficit 2,359 |
| C2 | rejected | `docs/reconstruction/12_C2_result_interpretation.md`; `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json` | Failed surplus threshold: surplus 6,675; accepted only 27 deletions; 75,893 `would_disconnect_graph` rejections |
| C3_probe_v1 | evidence only | `docs/reconstruction/17_C3_feasibility_probe_result.md`; `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_report.json` | No graph generated; 0 of 473 tested connectivity-critical bridge-like target edges had feasible replacement under eligible pool v1 |

Relation addition and remove-and-replace graph generation remain future work. They are not part of the selected final graph.

## 6. Thesis-Safe Wording

### Phase I

The first phase constructs relation-level evidence from cached Wikidata-derived artifacts. It restricts the relation universe to wikibase-item properties, uses cached empirical two-hop discovery with 56,278 summed valid second-hop relation entries, estimates hop-support statistics, and identifies symmetric, anti-symmetric, and inverse relation groups empirically in the dashboard. Composition uses a stored LLM-derived relation-profile artifact only as an upstream high-recall pruning signal, followed by domain/range compatible target filtering and sampled shortcut verification. The final 5k allocation pattern relation sets are reproduced from patched v3 hop support and v3 compact composition-verification artifacts under canonical thresholds with Wilson filtering disabled, although the exact dashboard export session was not preserved.

### Phase II

The selected final graph is B0, the Stage12 repaired largest component. The strongest verified local chain begins at the archived Stage4 core graph, continues through no-op Stage5 repair and Stage6 refinement, then through the standalone eta-aware Stage7 replacement, Stage11 connectivity repair, Stage12 path repair, and B0 largest-component extraction. Stage1 genericity and Stage2 candidate collection are preserved as frozen evidence and Stage4 core triples are a subset of the Stage2 candidate shards, but exact Stage2 rerun reproducibility is limited by WDQS/cache/environment provenance.

### Final Graph Selection

B0 is selected as the final reported graph because it preserves weak connectivity, observes all 139 allocated relations, has zero allocated-relation absence, and has lower quota deficit than the remaining defensible graph candidates. C1 reduces surplus modestly but increases deficit, C2 fails the surplus threshold, and C3_probe_v1 is a feasibility probe rather than a graph candidate.

### Limitations and Reproducibility

The final graph identity and Stage4-to-B0 chain are hash-verified, but full end-to-end reproducibility from live Wikidata and LLM inputs is not established. Missing evidence includes the exact dashboard export session, exact LLM production run/raw responses, Stage2 WDQS/cache replay conditions, and same-run cryptographic linkage between allocation and support-matrix exports.

## 7. Remaining Gaps Ranked by Thesis Risk

### High Risk

| Gap | Why it matters | Required action |
|---|---|---|
| Exact dashboard export session missing | It prevents claiming the final 5k allocation was exactly replayed from saved Streamlit state. | Keep thesis wording as reconstruction from cached v3 inputs and matching relation sets, or locate saved dashboard state/export manifest. |
| Exact LLM production run/raw responses missing | It prevents claiming fully reproducible LLM target filtering. | Keep LLM wording as stored upstream pruning artifact, or locate raw responses/model metadata/export manifest. |
| Full Phase I-to-final end-to-end rerun not established | It prevents claiming full pipeline reproducibility from live inputs. | Build wrapper-only orchestration over frozen artifacts first; add environment locks and manifests before replay claims. |

### Medium Risk

| Gap | Why it matters | Required action |
|---|---|---|
| v3 domain/range enrichment command/log incomplete | It weakens exact provenance of compatible-target artifact production. | Locate execution command/log or keep cached-intermediate wording. |
| Stage2 WDQS exact rerun/cache incomplete | It limits exact reproduction of candidate shards. | Preserve Stage2 shards as frozen evidence; only claim exact rerun after endpoint/cache/environment capture. |
| Support matrix same-run linkage to allocation missing | It prevents proving both artifacts were exported from one dashboard session. | Keep code-compatible/relation-compatible wording or locate paired export manifest. |

### Low Risk

| Gap | Why it matters | Required action |
|---|---|---|
| Inverse LLM side branch incomplete | Final allocation does not depend on completed inverse LLM output according to current evidence. | Keep inverse LLM described as attempted but not completed/evidenced; rely on empirical dashboard inverse grouping. |

## 8. Refactor Readiness Assessment

Minimal refactor can start now, but only within a conservative boundary.

Safe scope:

- Create a clean wrapper/orchestration layer around the verified artifact chain.
- Parameterize canonical paths and hashes.
- Preserve old artifacts as frozen evidence.
- Add manifests, command capture, and validation checks.
- Keep historical folders intact until thesis artifacts and provenance are archived.

Unsafe scope:

- Rewriting historical scripts as if they are the original executed workflow.
- Moving, renaming, or deleting old provenance folders before archival.
- Replacing cached Phase I evidence with new live WDQS or LLM outputs without marking the run as new.
- Claiming full end-to-end reproducibility before dashboard, LLM, WDQS/cache, and environment gaps are closed.

## 9. Recommended Next Actions

1. Compile the thesis and inspect the patched methodology sections.
2. Run a thesis claim scan against `docs/latex/main_v05.tex`.
3. Commit reconstruction docs, rebuild manifests, and thesis wording patches together.
4. Create a wrapper-only reproducibility entrypoint that validates frozen inputs and rebuilds documentation/audit reports without regenerating graph artifacts.
5. Begin minimal code refactor only after the wrapper boundary is accepted: no historical artifact moves, no hidden graph regeneration, and no live WDQS/LLM calls unless explicitly tracked as a new experiment.
