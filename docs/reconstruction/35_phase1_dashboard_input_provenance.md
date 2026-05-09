# R2.9 Phase I Dashboard Input Provenance

## Executive Summary

This report reconstructs the Phase I artifact chain that most likely fed the dashboard allocation/export step for the canonical 5k allocation used by the selected B0 final graph.

Canonical allocation:

`src/Pruning graph/bidirectional_allocation_results5k.json`

SHA256:

`a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

Status: **partial provenance**.

Confirmed:

- `src/statistics/hop_pattern_analysis_dashboard.py` has default inputs pointing to v2 hop-support and v2 composition artifacts.
- Local files matching those checked-in defaults exist.
- The canonical 5k allocation is the downstream allocation used by the selected B0 final graph chain.
- The cached two-hop discovery artifact supports **56,278** summed `valid_r2` entries.

Evidence-based inference:

- The canonical 5k allocation most closely matches the patched v3 input family:
  - `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl`
  - `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl`
- This match requires Wilson filtering to be **disabled** for the final allocation selection.

Not proven:

- No dashboard export log, saved Streamlit session, widget-state capture, or manifest was found that cryptographically links the exact input files to `bidirectional_allocation_results5k.json`.
- The approximately 340,000 observed two-hop pair claim remains unsupported by the current local evidence.

## Dashboard Defaults

The checked-in dashboard defaults point to v2 artifacts:

| Role | Default / matching local path | Evidence |
|---|---|---|
| Hop-support input | `data/archived/hop_support_v2_w_failed_statuses.wikibase_item_only_before_target_enrichment.jsonl` | `src/statistics/hop_pattern_analysis_dashboard.py` |
| Composition input | `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl` | `src/statistics/hop_pattern_analysis_dashboard.py` |
| Relation metadata | `data/raw/wikidata_ontology.properties.json` | `src/statistics/hop_pattern_analysis_dashboard.py` |

These defaults are confirmed as code defaults, but they are **not** the best-supported inputs for the final 5k allocation because they do not reproduce the canonical allocation relation universe.

## Candidate Dashboard Input Files

| Role | Path | Evidence status | Notes |
|---|---|---|---|
| Relation profile / LLM-classified relation metadata | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` | Partial | Artifact exists; LLM prompt/model/raw-response provenance remains incomplete. |
| Relation metadata | `data/raw/wikidata_ontology.properties.json` | Confirmed dashboard metadata input | Local file matches dashboard metadata default. |
| Two-hop discovery cache | `data/processed/hop_discovery_from_json.jsonl` | Confirmed cached evidence | Supports 1,703 first-hop relation records and 56,278 summed `valid_r2` entries. |
| V2 hop support default | `data/archived/hop_support_v2_w_failed_statuses.wikibase_item_only_before_target_enrichment.jsonl` | Confirmed dashboard default | Checked-in default, but not final-allocation match. |
| V2 composition default | `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl` | Confirmed dashboard default | Checked-in default, but not final-allocation match. |
| Patched v3 hop support | `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl` | Strong inference as final allocation input | Reproduces canonical relation universe and pattern groups when paired with v3 compact composition and Wilson disabled. |
| V3 composition compact | `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl` | Strong inference as final allocation input | Reproduces canonical relation universe and pattern groups when paired with patched v3 hop support and Wilson disabled. |
| Genericity support matrix | `archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json` | Confirmed downstream Phase II input; export provenance partial | R2.8 established Stage1 consumption and relation-set compatibility, but no same-run dashboard export manifest. |

## Allocation Input-Family Finding

The final 5k allocation records these relevant thresholds in its JSON config:

- `base_min_total=50`
- `sym_min_support=50`, `sym_min_conf=0.6`
- `anti_min_support=50`, `anti_min_conf=0.99`
- `inv_min_support=50`, `inv_min_conf=0.6`
- `comp_min_support=50`, `comp_min_conf=0.6`
- `matrix_min_support=50`
- `matrix_mode=log1p_balanced_norm`
- `integerize=true`

Comparison result:

| Input family | Wilson filtering | Derived relation universe | Canonical allocation universe | Pattern groups match canonical 5k allocation? | Status |
|---|---:|---:|---:|---|---|
| Checked-in dashboard v2 defaults | Disabled | 1,148 | 1,467 | No | Contradicted as final input family |
| Checked-in dashboard v2 defaults | Enabled | 1,148 | 1,467 | No | Contradicted as final input family |
| Patched v3 support + v3 compact composition | Disabled | 1,467 | 1,467 | Yes | Strongest inferred final input family |
| Patched v3 support + v3 compact composition | Enabled | 1,467 | 1,467 | No; composition group shrinks | Wilson not supported for final 5k export |
| Normalized v3 support + v3 compact composition | Disabled | 1,468 | 1,467 | No | Alternative artifact, not exact final match |

Conclusion:

The canonical 5k allocation most likely came from patched v3 hop support plus v3 compact composition verification, with Wilson filtering disabled. This remains an inference because no dashboard export log or saved dashboard state was found.

## Phase I Chain Mapping

| Intended Phase I component | Best-supported evidence | Status | Notes |
|---|---|---|---|
| Relation universe / wikibase-item filtering | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json`; `logs/hop_discovery_json_27530562.out`; `data/processed/hop_discovery_from_json.jsonl` | Confirmed cached execution | Hop-discovery log reports 1,703 wikibase-item candidate relations from relation-profile input. |
| Empirical two-hop discovery | `data/processed/hop_discovery_from_json.jsonl`; `logs/hop_discovery_json_27530562.out` | Confirmed cached execution | Cached artifact supports 56,278 summed `valid_r2` entries. |
| Hop-support estimation | v2/v3 support artifacts; `logs/hop_support_v2_27520503.out`; `logs/normalized_hop_support_v3_rerun28049486.out` | Confirmed execution for support artifacts; final input family inferred | Patched v3 support best matches final allocation. |
| Symmetry and anti-symmetry evidence | Dashboard support parser and canonical allocation groups | Partial to confirmed | Groups are reproducible from patched v3 support under canonical thresholds. |
| Inverse evidence | `data/processed/wikidata_ontology.inverse_mode_aliases_topk.json`; `logs/build_inverse_alias_topk_27543764.out`; `logs/llm_classification_inv_27548189.out`; `logs/llm_classification_inv_27548189.err` | Partial | Alias construction is evidenced; inverse LLM completion remains unresolved because error logs include quota failures. |
| Composition LLM target filtering | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json`; `src/composition_verification/classify_relations_pipeline.py` | Partial | Classification artifact exists, but prompt/model/raw-response provenance is incomplete. |
| Domain/range filtering | `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.jsonl`; `data/processed/hop_support_v3/min8_hop_support_v3_pairs_with_compatible_targets_dom_rng_v1.jsonl` | Partial | Artifacts exist; direct run provenance remains weaker than composition verification. |
| Composition shortcut verification | `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition_verified.*`; `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.*`; composition logs | Confirmed historical execution | V2 and v3 composition verifier logs and stats exist. |
| Dashboard allocation export | Dashboard source; `src/Pruning graph/bidirectional_allocation_results5k.json`; support matrix | Partial | Export artifacts exist and downstream use is confirmed; exact dashboard export session is missing. |

## 340k Versus 56,278 Two-Hop Claim

The thesis claim of approximately 340,000 observed two-hop pairs is **unsupported** by the current local evidence.

Supported cached value:

| Metric | Value | Evidence |
|---|---:|---|
| First-hop relation records | 1,703 | `data/processed/hop_discovery_from_json.jsonl` |
| Summed `valid_r2` entries | 56,278 | `data/processed/hop_discovery_from_json.jsonl` |
| Successful discovery records | 1,140 | `data/processed/hop_discovery_from_json.jsonl`; `logs/hop_discovery_json_27530562.out` |
| Error records | 512 | `data/processed/hop_discovery_from_json.jsonl`; `logs/hop_discovery_json_27530562.out` |
| Not-found records | 51 | `data/processed/hop_discovery_from_json.jsonl`; `logs/hop_discovery_json_27530562.out` |

Other counts found in the workspace do not support 340,000:

| Artifact | Count | Interpretation |
|---|---:|---|
| `data/processed/hop_support_v2_valid_r2_profile_check_summary.json` | `valid_r2_total=74,714`; `wikibase_item_total=61,158` | Support/profile check count, not 340k |
| `data/processed/hop_support_valid_r2_profile_check_summary.json` | `valid_r2_total=78,003`; `wikibase_item_total=63,994` | Support/profile check count, not 340k |
| `data/processed/output_hop_support_v3_triplets_from_hop_discovery_from_json_and_support_v2_rerun.normalized.jsonl` | 62,565 rows | V3 support-row derivative, not 340k |

Safe wording:

> The cached two-hop discovery artifact contains 1,703 candidate first-hop relation records and 56,278 summed valid second-hop relation entries.

Unsafe wording unless new evidence is found:

> Approximately 340,000 observed two-hop pairs were discovered.

## Claim Safety

| Claim | Status | Evidence | Recommended wording |
|---|---|---|---|
| The discovery relation universe was restricted to wikibase-item properties. | Safe | `logs/hop_discovery_json_27530562.out`; `data/processed/hop_discovery_from_json.jsonl` | State the cached discovery run used 1,703 wikibase-item candidate relations. |
| Empirical two-hop discovery was performed. | Safe | `logs/hop_discovery_json_27530562.out`; `data/processed/hop_discovery_from_json.jsonl` | Use exact cached counts, including 56,278 summed `valid_r2` entries. |
| Hop-support estimation was performed. | Safe with live-WDQS caveat | Hop-support artifacts and logs | State support was estimated historically and cached; exact reruns may drift with WDQS. |
| Composition verification used sampled shortcut checks. | Safe | Composition verifier outputs, logs, and stats | State v2/v3 composition verification artifacts exist with logs. |
| Wilson lower bound was part of final verifier output or final 5k allocation. | Unsupported | Dashboard code only; final allocation match fails with Wilson enabled | Say Wilson filtering was implemented in the dashboard but is not supported as final 5k selection evidence. |
| Final 5k allocation came from checked-in dashboard defaults. | Contradicted | Input-family comparison | Say checked-in defaults exist, but final 5k most closely matches patched v3 inputs. |
| Final 5k allocation came from patched v3 support and v3 compact composition. | Evidence-based inference | Exact universe/group match | Say "most likely" or "most consistent with"; do not state as confirmed export provenance. |
| Full inverse LLM verification completed successfully. | Unsupported | Inverse logs include failures; shard completion unresolved | Say inverse alias construction is evidenced and inverse LLM verification is partial/incomplete. |
| Full dashboard export reproducibility is established. | Unsupported | No saved dashboard session/export manifest found | Say the final artifact is hashable and downstream use is confirmed, but exact export reproducibility remains incomplete. |

## Remaining Gaps

1. Locate a dashboard export log, saved Streamlit state, or run manifest linking patched v3 support, v3 composition compact, thresholds, allocation JSON, and support matrix.
2. Audit inverse LLM shard outputs and reports for completion and failed decision counts.
3. Locate LLM target-filtering prompt/model/raw-response provenance for `relation_profiles_afterLLM_SecondTime.json`.
4. Strengthen direct provenance for domain/range enrichment artifacts.
5. Replace or justify the unsupported approximately 340,000 two-hop-pair thesis claim.
6. Preserve the distinction between checked-in dashboard defaults and the final 5k allocation's inferred patched-v3 input family.

