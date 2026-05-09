# R2.11 Composition LLM / Relation-Profile Provenance Audit

This audit is read-only. It distinguishes three different evidence layers that are easy to conflate:

1. stored relation-profile LLM labels used for composition-target pruning;
2. domain/range compatible-target enrichment;
3. sampled composition shortcut verification, which is the final empirical evidence consumed by the dashboard composition group.

The main conclusion is that final composition group membership is supported by compact sampled shortcut-verification output, while the upstream relation-profile LLM provenance remains only partially evidenced.

## Executive Summary

| Question | Finding | Evidence | Status |
|---|---|---|---|
| What is `relation_profiles_afterLLM_SecondTime.json`? | A relation-profile export containing 2,445 property records with derived `llm_classification` labels and reasons. | `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` | Artifact confirmed |
| How many composition targets does it retain? | 615 records have `llm_classification.composition.composition_target = YES`; 1,830 have `NO_WAY`. | Profiled JSON artifact | Artifact confirmed |
| Does it preserve raw LLM provenance? | No model-name key, prompt key, raw-response key, or LLM run config was found in the artifact. It contains derived labels/reasons and timestamps. | Profiled JSON keys; `src/composition_verification/classify_relations_pipeline.py` | Provenance incomplete |
| Which script likely produced the LLM labels? | `src/composition_verification/classify_relations_pipeline.py` is code-compatible: it defines the prompt/schema, calls OpenAI, and writes `llm_classification` into MongoDB. | Script source lines `20-99`, `103-168`, `400-417`, `424-444`, `575-580` | Likely, not directly logged |
| Was a production LLM run log found for that profile artifact? | No direct production command, SLURM log, raw response archive, or export manifest was found. | Searches over `logs/`, `scripts/slurm/`, `src/`, and reconstruction docs | Not found |
| Which artifact represents domain/range compatible target filtering? | `data/processed/hop_support_v3/min8_hop_support_v3_pairs_with_compatible_targets_dom_rng_v1.jsonl` contains 63,992 pair rows with compatible target lists. | Artifact profile; `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py` | Artifact confirmed; direct run provenance partial |
| Which artifact was used by v3 shortcut verification? | `data/processed/hop_support_v3/new_pairs_composition_in_v3_only.jsonl`, 9,802 rows, was the input named in the v3 SLURM/log/stat files. | `scripts/slurm/composition_range_domain_improved_min8_jsonl.slurm`; `logs/composition_hop_support_v3_min8_jsonl_28197929.out`; stats JSON | Confirmed historical execution |
| Is v3 compact composition verification directly evidenced? | Yes. The v3 SLURM log, stderr progress, and stats file agree on 9,802 input/output docs, 9,799 success docs, 3 skipped empty-chain docs, 1,297 saved targets, 88,199 SPARQL posts, and exit code 0. | v3 log/stats/report/compact artifacts | Confirmed historical execution |
| Is final composition grouping reproducible from v3 compact output? | Yes, under canonical dashboard thresholds with Wilson filtering disabled, the compact output yields 13 accepted composition candidate rows and 26 unique composition relations, matching the canonical 5k allocation composition group. | `docs/reconstruction/37_dashboard_empirical_pattern_logic_audit.md`; compact JSONL; canonical allocation | Strong evidence-based inference |
| Is LLM target filtering final proof of composition? | No. It is upstream pruning/profiling evidence only. Final composition evidence comes from sampled shortcut verification and dashboard thresholds. | Script roles and R2.10b reproduction | Safe distinction |

## Evidence Classes

- **Confirmed:** Directly supported by preserved artifacts, script logic, logs, stats, or reproduced counts.
- **Partial:** Artifacts and compatible code exist, but no exact production command/log/export session was found.
- **Inference:** The evidence is consistent and reproducible from preserved artifacts, but exact dashboard/session provenance is missing.
- **Unsupported:** No preserved evidence found.

## 1. Relation-Profile Artifact

Canonical artifact:

`data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json`

| Property | Value |
|---|---:|
| SHA256 | `a30635f0edc66c46b8aafe66fa01e047a65c2c8d01091be8f02926af8d952258` |
| Size bytes | 3,107,956 |
| JSON root type | list |
| Records | 2,445 |
| Records with `llm_classification` | 2,445 |
| Records with `metadata.datatype == wikibase-item` | 1,703 |
| Records with `metadata.datatype == quantity` | 675 |
| Records with `metadata.datatype == time` | 67 |

Top-level fields:

- `_id`
- `property_id`
- `llm_classification`
- `metadata`
- `rule_verification`
- `updated_at`
- `verification_error` for 742 records

Nested LLM classification fields:

- `llm_classification.relation_id`
- `llm_classification.logic.symmetry.decision`
- `llm_classification.logic.symmetry.reason`
- `llm_classification.logic.anti_symmetry.decision`
- `llm_classification.logic.anti_symmetry.reason`
- `llm_classification.logic.inverse.decision`
- `llm_classification.logic.inverse.reason`
- `llm_classification.composition.composition_target`
- `llm_classification.composition.composition_reason`

## 2. LLM Label Counts in the Relation-Profile Artifact

### Composition Target Labels

| `composition_target` | Records |
|---|---:|
| `YES` | 615 |
| `NO_WAY` | 1,830 |

This supports the statement that the stored LLM-derived profile artifact reduced possible composition targets to 615 retained target relations. It does not prove the LLM run is exactly reproducible.

### Logic Triage Labels

| Label | Records |
|---|---:|
| `symmetry:TEST` | 73 |
| `symmetry:LOW_PRIORITY` | 28 |
| `symmetry:NO_WAY` | 2,344 |
| `anti_symmetry:TEST` | 853 |
| `anti_symmetry:LOW_PRIORITY` | 768 |
| `anti_symmetry:NO_WAY` | 824 |
| `inverse:TEST` | 242 |
| `inverse:LOW_PRIORITY` | 1,322 |
| `inverse:NO_WAY` | 881 |

These auxiliary logic labels exist in the artifact, but R2.10b shows that the final symmetric, anti-symmetric, and inverse groups are reconstructed empirically from hop-support dashboard rules, not from completed LLM verification.

### Verification Error Fields

| `verification_error` | Records |
|---|---:|
| `AntiSymmetryNeedsTypedDomainRange` | 741 |
| `ConflictSymmetryVsAntiSymmetry` | 1 |

This is consistent with the script's defensive validation/guard logic, but does not itself provide a production run log.

## 3. What Provenance Is Missing from the LLM Profile Artifact?

The artifact does not contain preserved keys for:

- model name;
- OpenAI API version or provider metadata;
- raw LLM responses;
- exact prompt text or prompt file reference;
- LLM batch IDs;
- temperature;
- retry counts;
- response schema version;
- command line;
- environment or package lock.

The artifact does contain `updated_at`, `metadata.updated_at`, and `metadata.datatype_updated_at` timestamps. These timestamps are useful for rough chronology, but not sufficient LLM provenance.

Timestamp profile:

| Field | Observation |
|---|---|
| `updated_at` | 2 unique values; 2,444 records have `2026-01-10T03:40:04.794847`, 1 record has `2026-01-10T03:32:36.991905` |
| `metadata.updated_at` | same distribution as `updated_at` |
| `metadata.datatype_updated_at` | 49 unique values |

## 4. Likely Producer and Consumer Scripts

### Likely Producer: `classify_relations_pipeline.py`

Path:

`src/composition_verification/classify_relations_pipeline.py`

SHA256:

`1f3c81c92a17e40a343702580489cd73568e6bf51c5ec24fa4b36b330fcd803f`

Evidence:

- The script imports `OpenAI` and defines a relation-classification prompt.
- The prompt explicitly states that the job is triage, not proof.
- The response schema contains `logic` labels for symmetry, anti-symmetry, and inverse, plus `composition.composition_target`.
- CLI defaults include `--model gpt-4.1-mini`, `--batch_size 20`, and MongoDB collection inputs.
- The script writes `llm_classification` back into MongoDB records.

Relevant source locations:

- Prompt: `src/composition_verification/classify_relations_pipeline.py:20-99`
- Response schema: `src/composition_verification/classify_relations_pipeline.py:103-168`
- OpenAI call: `src/composition_verification/classify_relations_pipeline.py:400-417`
- CLI/model defaults: `src/composition_verification/classify_relations_pipeline.py:424-444`
- MongoDB update of `llm_classification`: `src/composition_verification/classify_relations_pipeline.py:575-580` and `612-617`

Producer status:

**Likely but not confirmed by production run log.** The script is code-compatible with the artifact schema, but no exact production log, SLURM file, command history, or raw response archive was found for producing `relation_profiles_afterLLM_SecondTime.json`.

### Consumers

| Consumer | Evidence | Role |
|---|---|---|
| `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py` | `load_target_property_ids()` keeps records where `llm_classification.composition.composition_target != NO_WAY` | Uses LLM-derived profile artifact to select composition target candidates for domain/range filtering |
| `scripts/slurm/hop_discovery_json.slurm` / `src/archive/hop_discovery.py` | R2.9/R2.11 prior docs and log evidence | Consumes relation profiles for wikibase-item relation universe / hop discovery |
| `src/inverse_verification_legacy/build_inverse_alias_topk.py` | CLI default relation profiles path | Uses relation-profile metadata for inverse alias candidate construction |
| `src/inverse_verification_legacy/llm_classification_inv.py` | CLI default relation profiles path | Uses relation-profile metadata for inverse LLM classification attempt |

## 5. Domain/Range Compatible Target Filtering

Main v3 compatible-target artifact:

`data/processed/hop_support_v3/min8_hop_support_v3_pairs_with_compatible_targets_dom_rng_v1.jsonl`

| Property | Value |
|---|---:|
| SHA256 | `6f9bc2b6c2d0ec344a6603137f464436eb3bb541f8aba66a200d4698f4b75ec9` |
| Size bytes | 1,043,849,440 |
| JSONL records | 63,992 |
| Bad JSON rows | 0 |
| Rows with `targets` | 63,992 |
| Total stored target entries | 13,732,052 |
| Target count range per row | 113 to 615 |
| Unique `r1` values | 1,481 |
| Unique target relations | 615 |

Schema fields:

- `r1`
- `r2`
- `support`
- `source_mode`
- `input_status`
- `target_count`
- `targets_truncated`
- `targets`

Each target entry has:

- `t`
- `dom_reason`
- `rng_reason`

Likely producer script:

`src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py`

Evidence:

- It loads target relations where `llm_classification.composition.composition_target != NO_WAY`.
- It loads property constraints from `valid_subject_type_ids` and `valid_object_type_ids`.
- It treats `ANY` or missing constraints as permissive.
- It writes JSONL records with `r1`, `r2`, `support`, `source_mode`, `input_status`, `target_count`, `targets_truncated`, and optional `targets`.

Relevant source locations:

- Goal and compatibility semantics: `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py:1-24`
- Target selection from LLM profile: `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py:98-110`
- Constraint loading: `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py:113-133`
- Output record construction: `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py:303-340`
- Commented example command using `relation_profiles_afterLLM_SecondTime.json`: `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py:376-377`

Domain/range filtering status:

**Artifact confirmed; direct production run evidence partial.** The JSONL artifact and code path are clear, but no exact v3 SLURM/log command was found for producing this compatible-target file.

Relevant metadata input:

`data/raw/wikidata_ontology.properties.json`

| Property | Value |
|---|---:|
| SHA256 | `daac555483634bfcb608c5fc04f9a2f14678772381edd91440822606db3a0380` |
| Size bytes | 644,751 |
| Records | 2,445 |
| Records with `valid_subject_type_ids` | 2,445 |
| Records with `valid_object_type_ids` | 2,445 |

## 6. V3 Shortcut Verification Input and Outputs

The direct v3 composition-verifier input named in the preserved SLURM/log/stats evidence is:

`data/processed/hop_support_v3/new_pairs_composition_in_v3_only.jsonl`

| Property | Value |
|---|---:|
| SHA256 | `f9a16ed6e584ce1e587ea2869187ebc84f71beed7481ed38e9e2e84841013399` |
| Size bytes | 165,350,236 |
| JSONL records | 9,802 |
| Bad JSON rows | 0 |
| Rows with `targets` | 9,802 |
| Total stored target entries | 2,169,051 |
| Target count range per row | 113 to 615 |

The v3 composition-verification outputs are:

| Artifact | SHA256 | Size bytes | Records / role |
|---|---:|---:|---|
| `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.jsonl` | `884a445788c9a0c200cc79d91bb91c28facd744fed5c5594142d508233b9f1ec` | 173,827,779 | Full JSONL output; 9,802 rows |
| `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl` | `8fbc1db6847b7676c1f144521218b444e2768cb06345d1a6288afd58177df54e` | 10,021,946 | Compact JSONL output; 9,802 rows |
| `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition.report.jsonl` | `8ad3e98ef57a1168905f79cb563a195f33f54e8495d83abc2f63252e8944efa3` | 305,980 | Report JSONL; 1,297 saved target rows and 3 skips |
| `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition.stats.json` | `da9ce624ed266122f4f2c274de9985493115d269272181b2ea9dae30b7e718f9` | 1,279 | Run statistics |
| `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition.checkpoint.json` | `5bb2d33257619667c80e1a9dda9e6288cef1290c75b07846a586f73a8f0408db` | 59 | Checkpoint at line 9,802 |

Compact output schema:

- `r1`
- `r2`
- `support`
- `source_mode`
- `input_status`
- `target_count`
- `targets_truncated`
- `rule_verification`

Nested `rule_verification` fields:

- `composition_discovery_found`
- `composition`
- `composition_updated_at`
- `composition_chain_pairs_examined`
- `composition_notes`
- `composition_sparql_posts_used`
- `composition_sparql_posts_total`
- `composition_run`

## 7. V3 Shortcut Verification Log Evidence

Runner:

`scripts/slurm/composition_range_domain_improved_min8_jsonl.slurm`

SHA256:

`5fb5d35fe04ee9371e855a53d3dd065c04e77e8a32e6a4de9c1225c391a07e00`

The SLURM script sets:

- `INPUT_JSONL` to `data/processed/hop_support_v3/new_pairs_composition_in_v3_only.jsonl`
- `OUTPUT_JSONL` to the v3 full composition-verified JSONL
- `OUTPUT_COMPACT_JSONL` to the v3 compact JSONL
- `STATS_JSON` to the v3 stats JSON
- `REPORT_JSONL` to the v3 report JSONL
- `ENDPOINT` to `https://query.wikidata.org/sparql`
- `SAMPLE_N=300`
- `USE_DETERMINISTIC_SAMPLE=true`
- `USE_EXCLUDE_SELF_LOOPS=true`

Evidence locations:

- `scripts/slurm/composition_range_domain_improved_min8_jsonl.slurm:29-34`
- `scripts/slurm/composition_range_domain_improved_min8_jsonl.slurm:39-63`
- `scripts/slurm/composition_range_domain_improved_min8_jsonl.slurm:105-128`

Log files:

| Path | SHA256 | Evidence |
|---|---:|---|
| `logs/composition_hop_support_v3_min8_jsonl_28197929.out` | `3f28af34696c35d4bbe71b049163e800d00afd2626b5b5b0650b1f695048ef16` | Start/end, paths, exit code 0 |
| `logs/composition_hop_support_v3_min8_jsonl_28197929.err` | `37796f9aa283693e5b04d16c1df9cfd0fcb5f7f05453ab5a67b9eedb64f08010` | Progress, saved targets, SPARQL post count, stats write |

Run evidence from stdout:

- Job started: `Tue Mar 10 21:32:53 CET 2026`
- Job finished: `Wed Mar 11 13:06:00 CET 2026`
- Exit code: `0`

Run evidence from stderr/stats:

| Metric | Value |
|---|---:|
| `lines_seen` | 9,802 |
| `nonempty_lines_seen` | 9,802 |
| `output_docs_written` | 9,802 |
| `output_compact_docs_written` | 9,802 |
| `success_docs` | 9,799 |
| `skipped_docs` | 3 |
| `error_docs` | 0 |
| `skip_reasons.empty_chain_sample` | 3 |
| `saved_targets` | 1,297 |
| `sparql_posts_total` | 88,199 |
| `stopped_on_transient` | `false` |
| `final_checkpoint_line` | 9,802 |

Shortcut verification status:

**Confirmed historical execution.** Rerunning would still depend on live WDQS unless responses are frozen, but the preserved output/log/stats evidence is strong.

## 8. Role in Final Dashboard Composition Group

R2.10b established that the final 5k allocation composition group is reproduced from:

- patched v3 hop-support input for the dashboard base support matrix;
- v3 compact composition-verification output for composition candidates;
- canonical thresholds recorded in `src/Pruning graph/bidirectional_allocation_results5k.json`;
- Wilson filtering disabled.

Under those conditions, the compact composition output yields:

| Metric | Value |
|---|---:|
| Accepted composition candidate rows | 13 |
| Unique composition relations | 26 |
| Canonical 5k composition group size | 26 |
| Relation-set match | Yes |

This means the final composition group is supported by sampled shortcut verification. LLM target filtering is upstream pruning/profiling evidence; it is not the final proof that a composition rule holds.

The exact Streamlit dashboard export session remains missing, so the final allocation input family is still an evidence-based reconstruction rather than a saved-session replay.

## 9. Provenance Status by Component

| Component | Status | Reason |
|---|---|---|
| Relation-profile JSON artifact | Confirmed artifact | File exists, hashes, schema, counts recorded. |
| LLM target-filter labels inside relation profiles | Confirmed artifact content | 615 YES / 1,830 NO_WAY records. |
| Production LLM run provenance | Partial/incomplete | Code-compatible script exists, but no exact run log, prompt snapshot, raw response archive, or export manifest was found. |
| Domain/range compatible-target artifact | Confirmed artifact; production run partial | Large v3 JSONL exists and schema matches enrichment script, but exact v3 production command/log was not found. |
| V3 shortcut verification | Confirmed historical execution | SLURM runner, stdout/stderr logs, stats, full output, compact output, report, and checkpoint align. |
| Final dashboard composition grouping | Strong evidence-based inference | Compact output reproduces canonical composition group under recorded thresholds with Wilson disabled; exact dashboard export session missing. |

## 10. Safe Thesis Wording

Safe wording:

> The LLM-based relation-profile artifact was used as an upstream high-recall pruning signal for composition target selection. In the stored profile artifact, 615 relations were retained as plausible composition targets and 1,830 were labelled `NO_WAY`. These labels were not treated as proof of composition. Candidate targets were subsequently filtered by domain/range compatibility and then evaluated through sampled shortcut verification. The final composition group in the 5k allocation is reproduced from the v3 compact composition-verification output under the canonical dashboard thresholds with Wilson filtering disabled.

Safe caveat:

> The exact production LLM run that generated `relation_profiles_afterLLM_SecondTime.json` is not fully preserved: the artifact contains derived labels and reasons, but not raw responses, model/run metadata, or a saved prompt reference. Therefore the LLM target-filtering step should be described as a stored upstream pruning artifact, not as a fully reproducible LLM run.

## 11. Unsafe Thesis Wording

Do not claim:

- “The composition LLM labels prove composition.”
- “The exact LLM classification run is fully reproducible from preserved prompts, raw responses, and model metadata.”
- “The final composition group was selected directly by the LLM.”
- “Wilson lower-bound filtering was used for the final 5k allocation.”
- “The exact Streamlit export session is preserved.”
- “Domain/range filtering has complete production command/log provenance,” unless a v3 run log for the enrichment step is found.

## 12. Remaining Gaps

1. Locate the production command/log for `src/composition_verification/classify_relations_pipeline.py`.
2. Locate any raw OpenAI request/response archive or payload log for the relation-profile classification.
3. Locate an export manifest or command that produced `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` from MongoDB.
4. Locate the exact v3 domain/range enrichment command/log for `min8_hop_support_v3_pairs_with_compatible_targets_dom_rng_v1.jsonl`.
5. Locate a same-run dashboard export session linking patched v3 support, v3 compact composition output, the canonical 5k allocation, and the genericity support matrix.

