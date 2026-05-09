# R2.10b Dashboard Empirical Pattern-Logic Audit

This audit explains how the Streamlit dashboard empirically identifies relation pattern groups for allocation: symmetric, anti-symmetric, inverse, and composition. It separates those dashboard rules from the incomplete inverse LLM classification branch documented in R2.10.

## Executive Summary

| Question | Finding | Evidence | Status |
|---|---|---|---|
| Does the dashboard implement empirical symmetric scoring? | Yes. It filters `r1 == r2` rows using `conf_loop = loop / total`. | `src/statistics/hop_pattern_analysis_dashboard.py:108-180`, `src/statistics/hop_pattern_analysis_dashboard.py:1052-1055` | Confirmed |
| Does the dashboard implement empirical anti-symmetric scoring? | Yes. It filters `r1 == r2` rows using `conf_nonloop = nonloop / total`, then removes any overlap with symmetric relations. | `src/statistics/hop_pattern_analysis_dashboard.py:1056-1058`, `src/statistics/hop_pattern_analysis_dashboard.py:547-550` | Confirmed |
| Does the dashboard implement empirical inverse scoring? | Yes. It uses hop-support `conf_loop` in both directions and filters on `min(total(r1,r2), total(r2,r1))` and `min(conf(r1,r2), conf(r2,r1))`. | `src/statistics/hop_pattern_analysis_dashboard.py:298-323`, `src/statistics/hop_pattern_analysis_dashboard.py:1060-1064` | Confirmed |
| Does the dashboard implement empirical composition scoring? | Yes. It loads compact composition-verification output and filters sampled shortcut evidence using support, examined-chain count, shortcut hits, and sample confidence. | `src/statistics/hop_pattern_analysis_dashboard.py:353-473`, `src/statistics/hop_pattern_analysis_dashboard.py:1202-1227` | Confirmed |
| Do patched v3 inputs reproduce the canonical 5k pattern groups? | Yes, by relation set and count, when Wilson filtering is disabled. | `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl`; `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl`; `src/Pruning graph/bidirectional_allocation_results5k.json`; `docs/reconstruction/35_phase1_dashboard_input_provenance.md` | Strong evidence-based inference |
| Does the dashboard require completed inverse LLM output for the final inverse group? | No evidence found. The inspected dashboard/allocation code does not reference `inv_llm`, inverse alias outputs, OpenAI, or LLM inverse classifications for pattern grouping. | `src/statistics/hop_pattern_analysis_dashboard.py`; `src/statistics/hop_support_dashboard.py`; `src/kg_building/bidirectional_triple_allocation.py`; `docs/reconstruction/36_inverse_verification_completion_audit.md` | Confirmed absence in inspected code |
| Can completed inverse LLM verification be claimed? | No. R2.10 found alias generation, but not completed inverse LLM shard classification or merge output. | `docs/reconstruction/36_inverse_verification_completion_audit.md` | Unsupported |

## Evidence Classes

- **Confirmed:** Directly supported by source code, preserved artifacts, logs, or reproduced counts.
- **Strong evidence-based inference:** Reproduction matches preserved final artifacts, but exact dashboard export session is missing.
- **Unsupported:** No preserved artifact/log/code evidence found.

## 1. Inputs Used by Pattern Type

The canonical 5k allocation is:

`src/Pruning graph/bidirectional_allocation_results5k.json`

SHA256:

`a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

The allocation JSON records canonical dashboard thresholds:

| Parameter | Value |
|---|---:|
| `base_min_total` | 50 |
| `base_max_total` | 3,253,580 |
| `sym_min_support` | 50 |
| `sym_min_conf` | 0.6 |
| `anti_min_support` | 50 |
| `anti_min_conf` | 0.99 |
| `inv_min_support` | 50 |
| `inv_min_conf` | 0.6 |
| `comp_min_support` | 50 |
| `comp_min_conf` | 0.6 |
| `matrix_min_support` | 50 |
| `matrix_mode` | `log1p_balanced_norm` |
| `temperature` | 1.0 |
| `epsilon` | 0.0 |
| `integerize` | `true` |

The best-supported final input family remains the R2.9 patched-v3 family:

| Role | Path | SHA256 |
|---|---|---:|
| Hop-support input for symmetric, anti-symmetric, inverse, and adjacency matrix logic | `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl` | `9ff74a945575ccdbf3db45810da5970f01b18d499f304729d8edfb255acb23cf` |
| Composition-verification input for composition grouping | `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl` | `8fbc1db6847b7676c1f144521218b444e2768cb06345d1a6288afd58177df54e` |
| Pattern/allocation source code | `src/statistics/hop_pattern_analysis_dashboard.py` | `bb76aa0f43fbfb14cb3f5c3c18767c31a97fc4e767389c0f2201c8e7f944fe85` |
| Allocation algorithm | `src/kg_building/bidirectional_triple_allocation.py` | `5eeed6098e280fc2bb4d136ad8dd9090a4d4aead8baa56c8ded40241b4223eb3` |

R2.9 found that checked-in dashboard defaults point to v2 artifacts, but those defaults do not reproduce the canonical 5k allocation. The patched-v3 input family reproduces the canonical relation universe and all four pattern-group relation sets with Wilson filtering disabled. The exact Streamlit dashboard export session remains missing.

## 2. Symmetric Pattern Logic

The dashboard loader aggregates hop-support counts into one row per `(r1, r2)` and computes:

- `conf_loop = loop / total`
- `conf_nonloop = nonloop / total`

Evidence:

- `src/statistics/hop_pattern_analysis_dashboard.py:108-180`

The symmetric group is built from rows where:

- `r1 == r2`
- `total >= sym_min_support`
- `conf_loop >= sym_min_conf`

Evidence:

- `src/statistics/hop_pattern_analysis_dashboard.py:1052-1055`

Under canonical thresholds and patched v3 support:

| Metric | Value |
|---|---:|
| Symmetric candidate rows | 18 |
| Derived symmetric relation count | 18 |
| Canonical allocation symmetric relation count | 18 |
| Relation-set match with canonical allocation | Yes |

## 3. Anti-Symmetric Pattern Logic

The anti-symmetric group is built from self-pair rows where:

- `r1 == r2`
- `total >= anti_min_support`
- `conf_nonloop >= anti_min_conf`

Evidence:

- `src/statistics/hop_pattern_analysis_dashboard.py:1056-1058`

The group builder then removes symmetric/anti-symmetric overlap by keeping overlapping relations in `symmetric` and removing them from `anti_symmetric`.

Evidence:

- `src/statistics/hop_pattern_analysis_dashboard.py:547-550`

Under canonical thresholds and patched v3 support:

| Metric | Value |
|---|---:|
| Anti-symmetric candidate rows before overlap removal | 66 |
| Symmetric/anti-symmetric overlap | 0 |
| Derived anti-symmetric relation count | 66 |
| Canonical allocation anti-symmetric relation count | 66 |
| Relation-set match with canonical allocation | Yes |

## 4. Empirical Inverse Pattern Logic

The dashboard inverse logic is empirical and hop-support based. It does not require inverse LLM output.

The `prepare_inverse_table` function:

1. Keeps non-self pairs, `r1 != r2`.
2. Uses forward `conf_loop(r1,r2)`.
3. Joins the reverse pair `(r2,r1)`.
4. Computes:
   - `reverse_conf_loop = conf_loop(r2,r1)`
   - `reverse_total = total(r2,r1)`
   - `bidirectional_conf_min = min(conf_loop, reverse_conf_loop)`
   - `bidirectional_conf_mean = mean(conf_loop, reverse_conf_loop)`

Evidence:

- `src/statistics/hop_pattern_analysis_dashboard.py:298-323`

The inverse filter then requires:

- `two_way_support_min = min(total(r1,r2), total(r2,r1)) >= inv_min_support`
- `bidirectional_conf_min >= inv_min_conf`

Evidence:

- `src/statistics/hop_pattern_analysis_dashboard.py:1060-1064`

The inverse relation group is relation-level: it is the unique relation-ID set from both `r1` and `r2` across accepted inverse candidate rows.

Evidence:

- `src/statistics/hop_pattern_analysis_dashboard.py:552-555`

Under canonical thresholds and patched v3 support:

| Metric | Value |
|---|---:|
| Inverse candidate rows | 44 |
| Derived inverse relation count | 44 |
| Canonical allocation inverse relation count | 44 |
| Relation-set match with canonical allocation | Yes |

This is the dashboard inverse evidence that can be cited for the final allocation. It is separate from the incomplete inverse LLM branch in R2.10.

## 5. Composition Pattern Logic

The dashboard composition loader reads compact verifier output from `*.composition_verified.compact.jsonl`. For each source row, it reads:

- `r1`
- `r2`
- `support` as `base_support`
- `rule_verification.composition`
- per-target `r3`
- `chain_pairs_examined`
- `chain_pairs_with_shortcut`
- `chain_pairs_missing_shortcut`
- `sample_confidence`

Evidence:

- `src/statistics/hop_pattern_analysis_dashboard.py:353-473`

The dashboard filters composition rows by:

- `base_support >= comp_min_support`
- `chain_pairs_examined >= comp_min_examined`
- `chain_pairs_with_shortcut >= comp_min_shortcuts`
- `conf_composition_sample >= comp_min_conf`

Evidence:

- `src/statistics/hop_pattern_analysis_dashboard.py:1202-1207`

Wilson filtering is implemented as an optional dashboard filter:

- computes `wilson_lower_bound`
- if enabled, keeps rows with `wilson_lower_bound >= comp_min_conf`

Evidence:

- `src/statistics/hop_pattern_analysis_dashboard.py:1209-1227`

Under canonical thresholds and v3 compact composition:

| Composition condition | Candidate rows | Relation group size | Canonical composition group size | Match |
|---|---:|---:|---:|---|
| Wilson disabled | 13 | 26 | 26 | Yes |
| Wilson enabled at 95% | 12 | 24 | 26 | No |

Therefore, the final 5k allocation is most consistent with Wilson filtering disabled.

## 6. Relation-Level Group Construction

The dashboard converts candidate-level pattern rows to relation-level groups:

- `symmetric`: unique `r1`
- `anti_symmetric`: unique `r1`, after removing relations already in `symmetric`
- `inverse`: unique values from `r1` and `r2`
- `composition`: unique values from `r1`, `r2`, and `r3`

Evidence:

- `src/statistics/hop_pattern_analysis_dashboard.py:528-566`

The allocation JSON stores:

| Pattern group | Canonical relation count |
|---|---:|
| `symmetric` | 18 |
| `anti_symmetric` | 66 |
| `inverse` | 44 |
| `composition` | 26 |

The allocation rows contain 154 relation allocations:

| Pattern | Allocation rows |
|---|---:|
| `symmetric` | 18 |
| `anti_symmetric` | 66 |
| `inverse` | 44 |
| `composition` | 26 |

The canonical allocation relation universe contains 1,467 relations.

## 7. Reproduction Check Against Canonical 5k Allocation

Using:

- `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl`
- `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl`
- thresholds recorded in `src/Pruning graph/bidirectional_allocation_results5k.json`
- Wilson filtering disabled

the reproduced pattern relation sets match the canonical allocation relation sets for all four groups.

| Pattern | Reproduced group size | Canonical group size | Relation-set match |
|---|---:|---:|---|
| `symmetric` | 18 | 18 | Yes |
| `anti_symmetric` | 66 | 66 | Yes |
| `inverse` | 44 | 44 | Yes |
| `composition` | 26 | 26 | Yes |

This is strong evidence that the final allocation was exported from the empirical dashboard logic using patched v3 support and v3 compact composition inputs. It is still an inference rather than a confirmed exact export session because no saved Streamlit state, dashboard export log, or manifest was found.

## 8. Relationship to Inverse LLM Classification

R2.10 found:

- inverse alias generation was completed;
- inverse LLM classification was attempted for at least shard 7;
- no local shard outputs or reports were found;
- no merged inverse LLM output was found;
- shard 7 had heavy quota/rate-limit failures and many `ERROR` decisions.

Evidence:

- `docs/reconstruction/36_inverse_verification_completion_audit.md`
- `artifacts/final_graph/selected_final_graph/rebuild/inverse_verification_completion_audit.json`

The inspected dashboard/allocation files do not reference:

- `inv_llm`
- inverse LLM shard outputs
- merged inverse LLM output
- inverse alias output
- OpenAI or GPT model calls

Files inspected:

- `src/statistics/hop_pattern_analysis_dashboard.py`
- `src/statistics/hop_support_dashboard.py`
- `src/kg_building/bidirectional_triple_allocation.py`

Therefore, completed inverse LLM verification is **not needed** for the final allocation claim. The final inverse group can be described as an empirical dashboard inverse group computed from bidirectional hop-support confidence. It must not be described as a completed LLM-verified inverse group.

## 9. Safe Thesis Wording

Safe wording:

> Symmetric, anti-symmetric, and inverse candidate relation groups were identified empirically from hop-support counts in the dashboard. Symmetric and anti-symmetric candidates used self-pair loop and non-loop proportions, while inverse candidates used bidirectional loop-confidence thresholds over both `(r_1,r_2)` and `(r_2,r_1)`. Composition candidates were derived from compact sampled shortcut-verification outputs. The canonical 5k allocation is most consistent with patched v3 hop-support and v3 compact composition-verification inputs under the recorded thresholds, with Wilson filtering disabled.

Safe caveat:

> The exact Streamlit export session was not preserved, so the allocation export is reconstructed by matching preserved inputs, threshold configuration, and resulting pattern relation sets.

Safe inverse caveat:

> This empirical inverse grouping is distinct from the inverse LLM verification branch. The preserved evidence does not establish completed inverse LLM shard classification or a merged inverse LLM output.

## 10. Unsafe Thesis Wording

Do not claim:

- “The inverse group was produced by completed inverse LLM verification.”
- “The inverse LLM classifier verified all final inverse relations.”
- “All inverse LLM shards completed successfully.”
- “Wilson lower-bound filtering was used for the final 5k allocation.”
- “The checked-in dashboard v2 defaults produced the final 5k allocation.”
- “The exact dashboard export session is fully reproducible from preserved Streamlit state.”

## 11. Remaining Gaps

1. Locate a saved dashboard export session, widget-state capture, or command log for the exact 5k allocation export.
2. Locate a same-run manifest cryptographically linking the patched v3 hop-support input, v3 compact composition input, exported allocation, and exported genericity support matrix.
3. Locate complete inverse LLM shard outputs and a merge output, if they exist, but keep them separate from the empirical dashboard inverse grouping unless direct allocation linkage is found.
4. Preserve the current thesis wording distinction between empirical pattern grouping and incomplete LLM inverse verification.

