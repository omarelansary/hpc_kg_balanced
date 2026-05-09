# R2.10 Inverse Verification Completion Audit

This audit is read-only. It separates inverse alias generation from inverse LLM classification, because the available evidence supports these two steps at different confidence levels.

## Executive Summary

| Question | Finding | Evidence | Status |
|---|---|---|---|
| Were inverse alias candidates generated? | Yes. A SLURM job generated `data/processed/wikidata_ontology.inverse_mode_aliases_topk.json` with 1,703 rows. | `logs/build_inverse_alias_topk_27543764.out`; `scripts/slurm/build_inverse_alias_topk.slurm`; `data/processed/wikidata_ontology.inverse_mode_aliases_topk.json` | Confirmed |
| Was inverse LLM classification attempted? | Yes, but only shard 7 has log evidence in this copied workspace. The log records quota/rate-limit failures and many `ERROR` decisions. | `logs/llm_classification_inv_27548189.out`; `logs/llm_classification_inv_27548189.err`; `scripts/slurm/llm_classification_inv.slurm` | Partial |
| Are inverse LLM shard outputs preserved locally? | No local `*.inv_llm.shard*.jsonl` or `*.inv_llm.report.shard*.json` files were found. | File search over `data/processed`, `data/archived`, `logs`, and inverse-related script folders | Not found |
| Was a merge step completed? | No merged inverse LLM output or merge log was found. A merge script exists, but script existence alone does not prove execution. | `src/inverse_verification_legacy/merge_llm_classification_inv_shards.py`; no matching merged output found | Not evidenced |
| Can full inverse LLM verification be claimed as completed? | No. The available evidence supports alias generation and a failed/partial sharded LLM attempt, not completed inverse LLM verification. | Shard 7 log summary and missing shard/merge artifacts | Unsafe claim |
| What inverse evidence fed the final allocation? | The final allocation is best treated as driven by empirical hop-support/dashboard threshold logic. No evidence was found that a completed inverse LLM artifact fed the canonical 5k allocation. | `src/statistics/hop_pattern_analysis_dashboard.py`; `docs/reconstruction/35_phase1_dashboard_input_provenance.md`; missing inverse LLM output artifacts | Evidence-based inference |

## Evidence Classes

- **Verified fact:** Directly supported by a preserved artifact, script, log, count, or hash.
- **Evidence-based inference:** Supported by compatible code paths and artifacts, but without a preserved exact command/session.
- **Unsupported:** No direct artifact/log/manifest evidence found.

## 1. Inverse Alias Candidate Generation

### Producer Script

The alias-generation producer is:

`src/inverse_verification_legacy/build_inverse_alias_topk.py`

The script docstring states that it builds inverse-mode top-k aliases for wikibase-item properties. Its CLI accepts relation profiles, property aliases, label embeddings, and writes one output object per property.

Relevant supporting files:

| Path | SHA256 | Role |
|---|---:|---|
| `src/inverse_verification_legacy/build_inverse_alias_topk.py` | `83413db36466f895548975cd34d7d0ce88275a92fb44c3e769630bed1cf532aa` | Alias candidate producer script |
| `scripts/slurm/build_inverse_alias_topk.slurm` | `3da7e33496b71c08b72bc74240d91b7bdea80e9625fba86965074bd2c0ed8537` | Historical SLURM runner |
| `logs/build_inverse_alias_topk_27543764.out` | `74ac4e6e099f99ca29f7e7214face1f491b644767149f5202daebd12b13814e4` | Successful run log |
| `logs/build_inverse_alias_topk_27543764.err` | `57c2b1e0d2650130f6d66b0c3e2e04d27e77cd247015929fe8bc8c6815573679` | Stderr log |

### Alias Output Artifact

| Path | SHA256 | Size bytes | Rows | Unique `pid` values |
|---|---:|---:|---:|---:|
| `data/processed/wikidata_ontology.inverse_mode_aliases_topk.json` | `2436e644e8b824583046885f702dd9b3141ccc3c4c887a24179e27dca4c6f8cf` | 615,388 | 1,703 | 1,703 |

Schema fields observed:

`datatype`, `description`, `inverse_links`, `inverse_mode_aliases_labels_topk`, `label`, `pid`

Alias-count distribution:

| Alias count | Relation rows |
|---:|---:|
| 0 | 205 |
| 1 | 530 |
| 2 | 329 |
| 3 | 193 |
| 4 | 129 |
| 5 | 317 |

The artifact also contains 208 `inverse_links` across 206 rows. This is metadata evidence, not evidence of completed LLM verification.

### Run Evidence

`logs/build_inverse_alias_topk_27543764.out` records:

- Job started: `Sun Feb 15 22:10:16 CET 2026`
- Output path in the original workspace: `/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced/data/processed/wikidata_ontology.inverse_mode_aliases_topk.json`
- `Wrote 1703 rows`
- Job finished: `Sun Feb 15 23:26:07 CET 2026`
- Exit code: `0`

The SLURM runner uses stale original-workspace paths under `/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced`, not the current copied refactor workspace. The produced alias artifact is present in the copied workspace.

**Alias generation status:** confirmed.

## 2. Inverse LLM Classification Attempt

### Producer Script

The LLM classifier script is:

`src/inverse_verification_legacy/llm_classification_inv.py`

The script defines a sharded inverse-candidate classification workflow with `NO_WAY`, `TEST`, and `ERROR` decisions. It writes `inv_llm_output`, configuration metadata, and reports when output/report paths are supplied. The script records API errors as `ERROR` decisions; therefore, process exit code alone is not sufficient evidence of semantic completion.

Relevant supporting files:

| Path | SHA256 | Role |
|---|---:|---|
| `src/inverse_verification_legacy/llm_classification_inv.py` | `e4b870415252fb65a19e630ffcd2889de93564432e4118558e555fce0d3c20f6` | Inverse LLM classifier script |
| `scripts/slurm/llm_classification_inv.slurm` | `32fe432ba44f9bf46863e72380638e282c11be51b03eed68b974c6341c3ae839` | Historical sharded SLURM runner |
| `logs/llm_classification_inv_27548189.out` | `2a4aeb9428dc664d1e08e50493840de5d7f48d7f8a836555b80f7837bfb9d88c` | Shard 7 stdout log |
| `logs/llm_classification_inv_27548189.err` | `01302ebb861946a7acb51763de83be89c517a2c127c33dcbcf838ee6af8f7c5c` | Shard 7 stderr log with API/quota failures |

### SLURM Configuration Evidence

`scripts/slurm/llm_classification_inv.slurm` defines an array job:

- Array range: `0-7`
- Model: `gpt-4.1`
- Candidate source: `union`
- Batch size: `15`
- Input: `data/processed/hop_support.wikibase_item_only.jsonl`
- Inverse aliases: `data/processed/wikidata_ontology.inverse_mode_aliases_topk.json`
- Output basename: `data/processed/hop_support.wikibase_item_only.inv_llm.jsonl`
- Report basename: `data/processed/hop_support.wikibase_item_only.inv_llm.report.json`

The runner again uses stale original-workspace paths under `/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced`.

### Input Candidate Universe

The input file for the inverse LLM job is present locally:

| Path | SHA256 | Size bytes | Rows |
|---|---:|---:|---:|
| `data/processed/hop_support.wikibase_item_only.jsonl` | `aff3440a327d15a5cdfb036a3effc4edf29654b0367818f70422d16a8b815cf7` | 2,379,967 | 1,703 |

Observed input status counts:

| Status | Rows |
|---|---:|
| `SUCCESS` | 1,645 |
| `PARTIAL_SUCCESS` | 27 |
| `ERROR` | 31 |

Using the classifier's `candidate_source=union` policy, the local input implies 63,994 candidate `(r1, r2)` decisions across 1,703 `r1` rows. This is the candidate universe implied by preserved input and script configuration; it is not evidence that all candidates were successfully classified.

### Shard Evidence

Only shard 7 has log evidence in this workspace.

| Shard | Evidence found | Output artifact found locally | Report artifact found locally | Completion status |
|---:|---|---|---|---|
| 0 | None found | No | No | Not evidenced |
| 1 | None found | No | No | Not evidenced |
| 2 | None found | No | No | Not evidenced |
| 3 | None found | No | No | Not evidenced |
| 4 | None found | No | No | Not evidenced |
| 5 | None found | No | No | Not evidenced |
| 6 | None found | No | No | Not evidenced |
| 7 | `logs/llm_classification_inv_27548189.out`; `logs/llm_classification_inv_27548189.err` | No | No | Attempted, but semantically incomplete/failed-heavy |

`logs/llm_classification_inv_27548189.out` records:

- Job started: `Mon Feb 16 00:52:40 CET 2026`
- `num_shards=8 shard_index=7`
- Output path in original workspace: `data/processed/hop_support.wikibase_item_only.inv_llm.shard7.jsonl`
- Report path in original workspace: `data/processed/hop_support.wikibase_item_only.inv_llm.report.shard7.json`
- Job finished: `Mon Feb 16 02:48:09 CET 2026`
- Exit code: `0`

The output and report named by the log are not present in this copied workspace.

### Error and Quota Evidence

The shard 7 stderr log contains heavy API failure evidence:

| Error marker | Count in `logs/llm_classification_inv_27548189.err` |
|---|---:|
| `429` | 5,577 |
| `insufficient_quota` | 2,250 |
| `rate_limit_exceeded` | 115 |

The shard 7 run summary records:

| Metric | Value |
|---|---:|
| `input_records_seen` | 1,703 |
| `written_records` | 218 |
| `candidate_total` | 8,608 |
| `NO_WAY` decisions | 887 |
| `TEST` decisions | 12 |
| `ERROR` decisions | 7,709 |
| `llm_batches` | 663 |
| `llm_batch_errors` | 591 |
| `shard_skipped` | 1,485 |

The large `ERROR` decision count means the shard did not provide completed classification evidence, even though the process exited with code 0.

**LLM inverse classification status:** attempted for at least shard 7, but completion is not established.

## 3. Merge Step Evidence

A merge script exists:

| Path | SHA256 | Role |
|---|---:|---|
| `src/inverse_verification_legacy/merge_llm_classification_inv_shards.py` | `58669c95516336da06a85b91030e3561c04979a4a3558bd0054efda64731ef1e` | Merges shard outputs in original input order |

No local merged inverse LLM output was found. No merge log was found. No local shard files were found for the merge script to consume.

**Merge status:** not evidenced.

## 4. Dashboard and Allocation Linkage

The final 5k allocation provenance from R2.9 remains:

- Canonical allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- The allocation is most consistent with patched v3 hop-support and v3 compact composition-verification inputs, with Wilson filtering disabled.
- The exact dashboard export session was not preserved.

No preserved inverse LLM shard output or merged inverse LLM artifact was found that could be shown to feed the canonical allocation. The dashboard code derives inverse-pattern evidence from empirical hop-support pair counts and thresholds, rather than requiring a completed `inv_llm` merged file.

**Safe linkage claim:** The final allocation's inverse-related grouping can be discussed as empirical/dashboard threshold evidence. Do not describe it as the result of completed inverse LLM verification unless a complete merged inverse LLM artifact and export linkage are found.

## 5. Completion Assessment

| Component | Completion status | Evidence strength | Notes |
|---|---|---|---|
| Alias candidate construction | Completed | Confirmed | Alias job log records 1,703 rows and exit code 0. |
| LLM inverse classification shard execution | Partially attempted | Partial | Only shard 7 has log evidence; output/report files are not locally preserved. |
| LLM inverse classification semantic success | Not completed from available evidence | Contradicted by errors | Shard 7 had 7,709 `ERROR` decisions out of 8,608 candidates. |
| Shards 0-6 | Unknown/not evidenced | Missing | No logs, outputs, or reports found. |
| Shard merge | Not evidenced | Missing | Merge script exists, but no merge output/log found. |
| Dashboard/allocation consumption of inverse LLM output | Not evidenced | Missing | No completed inverse LLM artifact linkage found. |

## 6. Safe Thesis Wording

Safe wording:

> Inverse-mode alias candidates were generated for 1,703 wikibase-item relations using relation profiles, property aliases, and label embeddings. A sharded LLM-based inverse classification workflow was prepared and at least one shard was attempted, but the preserved evidence does not establish successful completion of the inverse LLM verification stage. The final allocation should therefore be described as relying on the preserved empirical hop-support and dashboard threshold evidence, not on a completed inverse LLM verification artifact.

Shorter safe wording:

> Inverse aliases were generated and inverse LLM classification was attempted, but completed inverse LLM verification is not evidenced in the preserved artifacts.

## 7. Unsafe Thesis Wording

Do not claim:

- “Inverse verification was fully completed.”
- “All inverse LLM shards completed successfully.”
- “The inverse LLM classifier verified all candidate inverse pairs.”
- “A merged inverse LLM output fed the final 5k allocation.”
- “The final allocation is reproducible from completed inverse LLM verification outputs.”

These claims require missing evidence: all shard outputs/reports, a successful merge artifact, an execution log for the merge, and linkage from the merged output to the dashboard allocation export.

## 8. Remaining Gaps

1. Locate shard outputs:
   - `data/processed/hop_support.wikibase_item_only.inv_llm.shard*.jsonl`
   - `data/processed/hop_support.wikibase_item_only.inv_llm.report.shard*.json`

2. Locate logs for shards 0-6, if they exist.

3. Locate a merged inverse LLM output, if one exists.

4. Locate a merge command or SLURM log for `merge_llm_classification_inv_shards.py`.

5. Determine whether any complete inverse LLM artifact was used in a dashboard session or allocation export.

6. If no such evidence exists, keep inverse LLM verification as an attempted but incomplete side branch in the thesis methodology.

