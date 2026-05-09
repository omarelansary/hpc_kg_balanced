# Stage1 -> Stage2 Candidate Collection Provenance

This document reconstructs the provenance of the archived Phase II Stage1 and Stage2 artifacts that fed the Stage4 core graph selected into the verified B0 chain.

Scope:

- Stage1 genericity scoring.
- Stage2 candidate shard collection.
- The relationship between Stage1 genericity, the canonical 5k allocation, live WDQS retrieval, and the Stage2 shard pool used by Stage4.

This is a read-only provenance investigation. No WDQS calls, LLM calls, graph generation, or graph artifact modifications were performed.

## Bottom Line

**Stage1 -> Stage2 provenance status: confirmed for artifact/code dependency, partial for exact rerun reproducibility.**

The archived monolithic Phase II pipeline script:

`archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py`

produced both:

- Stage1 genericity outputs under `archive/hetzner_version/runs/prod_refine_20260315_180520/stage01_genericity/`.
- Stage2 candidate shards/checkpoints under `archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/`.

Stage2 directly consumed Stage1 genericity output by reading:

`archive/hetzner_version/runs/prod_refine_20260315_180520/stage01_genericity/relation_genericity.jsonl`

and it consumed the same 5k allocation file later selected as the canonical final-graph allocation:

`archive/hetzner_version/src/kg_builder/input/bidirectional_allocation_results5k.json`

That allocation hash is:

`a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

which matches:

`src/Pruning graph/bidirectional_allocation_results5k.json`

The Stage2 shard pool is strong frozen local evidence: 139 JSONL shard files, 81,958 rows, 81,958 unique triples, and 139 unique relations. However, Stage2 candidate collection itself is not exactly reproducible from frozen inputs because the production run used live WDQS (`candidate_source_mode: wdqs`, `candidate_input_path: null`) and no complete WDQS response cache or exact shell command was found.

## Machine-Readable Evidence

Full per-shard and per-checkpoint hashes are recorded in:

`artifacts/final_graph/selected_final_graph/rebuild/stage1_stage2_candidate_collection_provenance.json`

That JSON includes:

- all Stage1 output hashes;
- all Stage2 shard hashes;
- all Stage2 checkpoint hashes;
- Stage2 profile counts;
- log evidence counts;
- config and input hashes;
- R2.5 Stage2 -> Stage4 subset evidence summary.

## Implementation Evidence

| Stage | Script/function | Evidence | Status |
|---|---|---|---|
| Stage1 genericity scoring | `relation_balanced_kg_pipeline.py::stage_score_genericity(ctx)` and `score_genericity(...)` | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py`; run manifest stage entry | Confirmed code path |
| Stage2 candidate collection | `relation_balanced_kg_pipeline.py::stage_collect_candidates(ctx)` | same script; run manifest stage entry; Stage2 output directories; production log | Confirmed code path |
| Candidate backend | `build_candidate_source(config)` -> `WDQSCandidateSource` | run config has `candidate_source_mode: wdqs` and `candidate_input_path: null`; logs and shard rows say `wdqs` | Confirmed live WDQS backend |
| Stage4 candidate input | `stage_construct_graph(ctx)` reads `ctx.run_dir/stage02_candidates/shards` | `docs/reconstruction/30_stage3_to_B0_chain_verification.md`; `stage3_to_B0_chain_verification.json` | Confirmed artifact relationship |

Relevant archived code facts:

- Stage1 loads `ctx.config.allocated_relations_path` and `ctx.config.support_matrix_path`.
- Stage1 writes `stage01_genericity/relation_genericity.jsonl` and `stage01_genericity/summary.json`.
- Stage2 loads `ctx.config.allocated_relations_path`.
- Stage2 reads `ctx.run_dir / "stage01_genericity" / "relation_genericity.jsonl"` into a `genericity_map`.
- Stage2 builds its source with `build_candidate_source(ctx.config)`.
- With `candidate_source_mode=wdqs` and `candidate_input_path=null`, the source is `WDQSCandidateSource`.
- `WDQSCandidateSource` sends paginated `SELECT DISTINCT ?h ?t` queries to WDQS with `LIMIT` and `OFFSET`.
- Stage2 writes one JSONL shard and one checkpoint per allocated relation.
- Stage4 reads `ctx.run_dir / "stage02_candidates" / "shards"` directly.

## Run Manifest Evidence

Run manifest:

`archive/hetzner_version/runs/prod_refine_20260315_180520/manifest.json`

Important fields:

| Field | Value |
|---|---|
| `created_at` | `2026-03-15T17:05:20.750217+00:00` |
| `python_version` | `3.12.3 ... [GCC 13.3.0]` |
| `seed` | `7` |
| `config.allocated_relations_path` | `src/kg_builder/input/bidirectional_allocation_results5k.json` |
| `config.support_matrix_path` | `src/kg_builder/input/genericity_support_matrix.adjacency_support.json` |
| `config.candidate_source_mode` | `wdqs` |
| `config.candidate_input_path` | `null` |
| `config.wdqs_endpoint` | `https://query.wikidata.org/sparql` |
| `config.wdqs_page_size` | `200` |
| `config.wdqs_order_results` | `false` |
| `config.wdqs_require_entity_targets` | `true` |
| `config.max_workers` | `1` |

Manifest stage entries:

| Stage | Manifest evidence |
|---|---|
| `stage01_genericity` | completed at `2026-03-15T17:05:20.775341+00:00`; count `139`; bucket counts `high=3`, `medium=12`, `low=124`; high-genericity relations `P31`, `P279`, `P131` |
| `stage02_candidates` | completed at `2026-03-15T17:16:57.997028+00:00`; completed relations `139` |
| `stage03_candidate_audit` | completed at `2026-03-15T17:16:58.682885+00:00`; relation count `139`; zero candidate relations `0` |
| `stage04_core_graph` | completed at `2026-03-18T04:07:08.590320+00:00`; core triple count `18,513`; realized relations `139` |

## Config Evidence

Primary config files:

| Path | SHA256 |
|---|---|
| `archive/hetzner_version/src/kg_builder/config.yaml` | `5dd43af7ad0c1a1c8c75ae4e0487818fd48ae805d47320dab1bed7918ec0f1eb` |
| `archive/hetzner_version/src/kg_builder/config.runtime.json` | `e49e20dd29d17ca0879b9c4c649d07c25370544ddeedf8cad3a30876f4fcf4ad` |

The config explicitly states that production candidate collection used the live WDQS backend, not a local frozen candidate universe:

- `candidate_input_path: null`
- `candidate_source_mode: wdqs`
- `wdqs_endpoint: https://query.wikidata.org/sparql`
- `wdqs_user_agent: relation_balanced_kg_pipeline/1.0 (production)`
- `wdqs_page_size: 200`
- `wdqs_order_results: false`
- `wdqs_overfetch_factor: 3.0`
- `wdqs_max_raw_candidates_per_relation: 15000`
- `wdqs_pause_between_pages_sec: 0.25`

This is important: the current shard files are frozen local evidence, but regenerating them exactly would require the historical WDQS state and request behavior.

## Stage1 Outputs

Stage1 directory:

`archive/hetzner_version/runs/prod_refine_20260315_180520/stage01_genericity/`

| Output | SHA256 | Size | Count / role |
|---|---|---:|---|
| `relation_genericity.jsonl` | `d7b47683ecd08574f1d8fc8e97a213a0fd8f1b096b5f1bf7d71956df8387ca32` | 34,935 bytes | 139 JSONL rows |
| `summary.json` | `9fe7b86ac4550b38f23fb5d4693ffab7cbaa88040e661a70c4b9f97b6c33f8d8` | 164 bytes | bucket summary |

Stage1 row fields:

`candidate_volume_score`, `coverage_score`, `genericity_bucket`, `genericity_score`, `manual_structural_risk`, `relation`, `support_mass_score`

Computed Stage1 profile:

| Metric | Value |
|---|---:|
| Total rows | 139 |
| High bucket | 3 |
| Medium bucket | 12 |
| Low bucket | 124 |
| High-genericity relations | `P31`, `P279`, `P131` |

Top genericity scores from the artifact:

| Relation | Bucket | Score |
|---|---|---:|
| `P31` | high | 0.782310 |
| `P279` | high | 0.479407 |
| `P131` | high | 0.438425 |
| `P527` | medium | 0.433509 |
| `P361` | low | 0.303177 |

## Stage2 Outputs

Stage2 directory:

`archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/`

Main outputs:

| Output | Evidence | Profile |
|---|---|---|
| `shards/*.jsonl` | 139 per-relation JSONL files | 81,958 rows; 81,958 unique triples; 139 unique relations |
| `checkpoints/*.json` | 139 per-relation JSON checkpoints | 139 completed checkpoints |
| `reports/summary.json` | SHA256 `d9c6cd6124cb3c938b2045bf25c4bbdf8b6364c3002709547c6b45a98df8626d` | relation count `139`; total written candidates `81,958` |

Directory aggregate hashes from the generated provenance JSON:

| Directory | Aggregate SHA256 manifest |
|---|---|
| `stage02_candidates/shards/` | `25b8cacc69bad54d97526f6dfe7d5c43a85856a295a1d1663303fe6c68c84f0d` |
| `stage02_candidates/checkpoints/` | recorded in `stage1_stage2_candidate_collection_provenance.json` |

The shard aggregate hash matches the R2.5 Stage2 candidate-pool profile already recorded in:

`artifacts/final_graph/selected_final_graph/rebuild/stage3_to_B0_chain_verification.json`

Stage2 shard row fields:

`chunk_id`, `collection_mode`, `genericity_bucket`, `genericity_score`, `h`, `hub_penalty`, `ontology_ok`, `quality_score`, `query_id`, `query_limit`, `query_offset`, `r`, `retrieved_at`, `run_id`, `self_loop_flag`, `shortcut_risk`, `source_backend`, `source_stage`, `t`, `triple_id`

Stage2 computed profile:

| Metric | Value |
|---|---:|
| Shard files | 139 |
| Checkpoint files | 139 |
| Total shard rows | 81,958 |
| Unique triples | 81,958 |
| Unique relations | 139 |
| Invalid JSONL lines | 0 |
| Row-level `source_backend=wdqs` | 81,958 |
| Checkpoint-level `source_backend=wdqs` | 139 |
| Total checkpoint `accepted_candidates` | 191,855 |
| Total checkpoint `written_candidates` | 81,958 |
| Total checkpoint `source_raw_limit` | 301,230 |
| `retrieved_at` range | `2026-03-15T17:05:30.636555+00:00` to `2026-03-15T17:16:57.982976+00:00` |

Collection modes:

| Mode | Checkpoints | Rows |
|---|---:|---:|
| `graph_anchored` | 3 | 900 |
| `normal` | 115 | 77,198 |
| `small_full` | 21 | 3,860 |

Largest shard row counts:

| Relation | Rows |
|---|---:|
| `P2743` | 2,360 |
| `P13177` | 2,165 |
| `P461` | 1,870 |
| `P793` | 1,700 |
| `P399` | 1,635 |
| `P16` | 1,490 |
| `P1268` | 1,375 |
| `P1639` | 1,265 |
| `P3032` | 1,235 |
| `P3403` | 1,200 |

Smallest shard row counts:

| Relation | Rows |
|---|---:|
| `P514` | 39 |
| `P2152` | 54 |
| `P4545` | 61 |
| `P10374` | 98 |
| `P12994` | 106 |
| `P8865` | 129 |
| `P7209` | 138 |
| `P8308` | 171 |
| `P8571` | 178 |
| `P9059` | 194 |

## Did Stage2 Consume Stage1 Directly?

**Verified fact: yes, by code path.**

The Stage2 function `stage_collect_candidates(ctx)` reads:

`ctx.run_dir / "stage01_genericity" / "relation_genericity.jsonl"`

into `genericity_rows`, then constructs `genericity_map`. That map is passed into `annotate_relation_candidates(...)`, which writes candidate records with `genericity_score` and `genericity_bucket`.

Artifact-level support:

- Stage1 has 139 genericity rows.
- Stage2 has 139 checkpoints/shards.
- Stage2 shard rows include `genericity_score` and `genericity_bucket`.
- Stage2 summary bucket counts match Stage1 summary bucket counts: high `3`, medium `12`, low `124`.

## Did Stage2 Consume the Canonical 5k Allocation?

**Verified fact: yes.**

Evidence:

- Run manifest `config.allocated_relations_path` is `src/kg_builder/input/bidirectional_allocation_results5k.json`.
- `stage_score_genericity(ctx)` loads `ctx.config.allocated_relations_path`.
- `stage_collect_candidates(ctx)` also loads `ctx.config.allocated_relations_path`.
- Archived allocation hash is `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`.
- Local selected final-graph allocation at `src/Pruning graph/bidirectional_allocation_results5k.json` has the same hash.

## Did Stage2 Query WDQS, Read Local Cache, or Both?

**Verified fact: Stage2 queried live WDQS for candidate collection.**

Evidence:

- Run manifest and config have `candidate_source_mode: wdqs`.
- Run manifest and config have `candidate_input_path: null`.
- Code path `build_candidate_source(config)` returns `WDQSCandidateSource` under this configuration.
- Production log `archive/hetzner_version/logs/relation_balanced_kg_pipeline.out` includes `Stage stage02_candidates using candidate source backend: wdqs`.
- The same log has 139 `Collecting candidates for relation=... source=wdqs` lines and 139 `Finished relation=... source=wdqs` lines.
- The same log has 1,137 successful WDQS POST lines to `query.wikidata.org`.
- All 81,958 Stage2 shard rows have `source_backend: wdqs`.
- All 139 Stage2 checkpoints have `source_backend: wdqs`.

**Evidence-based inference:** Stage2 did not read a local candidate cache as its primary source in this production run. It wrote local frozen shards and checkpoints after WDQS retrieval. The code supports local candidate input mode, but the production config did not use it.

## Command and Log Evidence

Main Stage1/Stage2 production log:

`archive/hetzner_version/logs/relation_balanced_kg_pipeline.out`

SHA256:

`117214de34d71b759c58ac3b6188e85db648f63697a9a089c45b6b197a5230ea`

Log evidence:

| Evidence | Count / value |
|---|---:|
| `Stage stage02_candidates using candidate source backend: wdqs` | 1 |
| `Collecting candidates for relation=` | 139 |
| `Finished relation=` | 139 |
| successful WDQS POST lines | 1,137 |
| `WDQS 429` lines | 0 |
| final printed run dir | `runs/prod_refine_20260315_180520` |

The log does **not** include the literal shell command. No exact shell or SLURM command line for this production `run-all` execution was found in the copied archive. The command is therefore only reconstructable from:

- `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py`
- `archive/hetzner_version/src/kg_builder/config.yaml`
- `archive/hetzner_version/runs/prod_refine_20260315_180520/manifest.json`
- `archive/hetzner_version/logs/relation_balanced_kg_pipeline.out`

## Consistency With R2.5

R2.5 verified that Stage4 core graph construction used the Stage2 shard pool, not the Stage3 relation audit as a direct h/r/t graph input.

Evidence:

`artifacts/final_graph/selected_final_graph/rebuild/stage3_to_B0_chain_verification.json`

Relevant facts from R2.5:

- `overall_pass=true`
- `stage3_to_stage4_status=partial`
- `stage02_candidate_pool_profile.row_count=81958`
- `stage02_candidate_pool_profile.unique_triple_count=81958`
- `stage02_candidate_pool_profile.unique_relation_count=139`
- `stage02_candidate_pool_profile.stage4_core_triples_subset=true`
- `stage02_candidate_pool_profile.stage4_overlap_count=18513`
- Stage4 core triples are a subset of the combined Stage2 shard triple set.

This R2.6 investigation is consistent with R2.5.

## Reproducibility Assessment

| Claim | Status | Evidence |
|---|---|---|
| Stage1 artifacts exist locally and are hashable. | Safe | Stage1 `relation_genericity.jsonl` and `summary.json` with hashes above |
| Stage2 candidate shards exist locally and are hashable. | Safe | 139 shard files; full per-file hashes in generated JSON |
| Stage2 consumed Stage1 genericity output. | Safe | code path reads `stage01_genericity/relation_genericity.jsonl`; Stage2 rows carry genericity fields |
| Stage2 consumed the canonical 5k allocation. | Safe | manifest/config path plus matching allocation hash |
| Stage2 used live WDQS. | Safe | config, code path, log, shard rows, checkpoints |
| Stage2 can be rerun exactly from frozen local inputs. | Unsafe | no WDQS response cache; live endpoint drift; no exact command; no full environment lock |
| Stage2 shard pool can be treated as frozen local evidence for Stage4. | Safe | local JSONL shards; R2.5 subset verification |

## Remaining Gaps

- No exact shell/SLURM command for the production monolithic `run-all` execution was found.
- No WDQS response cache was found for replaying Stage2 without live network access.
- Stage2 depends on historical WDQS endpoint state and retrieval order; exact rerun is not established.
- The production log records relation-level collection and HTTP POST status, but not full SPARQL text for every request.
- Environment/package provenance remains incomplete beyond archived source, config, manifest `python_version`, and logs.

## Final Answer to the R2.6 Questions

1. **Which script/function produced Stage1 genericity outputs?**  
   `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py::stage_score_genericity(ctx)`.

2. **Which script/function produced Stage2 candidate shards?**  
   `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py::stage_collect_candidates(ctx)`, using `WDQSCandidateSource`.

3. **What were the exact Stage1 outputs and hashes?**  
   `relation_genericity.jsonl` hash `d7b47683ecd08574f1d8fc8e97a213a0fd8f1b096b5f1bf7d71956df8387ca32`; `summary.json` hash `9fe7b86ac4550b38f23fb5d4693ffab7cbaa88040e661a70c4b9f97b6c33f8d8`.

4. **What were the exact Stage2 outputs and hashes/profile?**  
   Stage2 produced 139 JSONL shards and 139 checkpoints. Shards contain 81,958 unique h/r/t triples across 139 relations. Full per-file hashes are in `stage1_stage2_candidate_collection_provenance.json`; summary hash is `d9c6cd6124cb3c938b2045bf25c4bbdf8b6364c3002709547c6b45a98df8626d`.

5. **Did Stage2 consume Stage1 genericity output directly?**  
   Yes, by code path and by genericity fields embedded in Stage2 rows.

6. **Did Stage2 consume the canonical 5k allocation file?**  
   Yes. The archived allocation hash equals the selected final graph allocation hash.

7. **Did Stage2 query WDQS, read local cache, or both?**  
   Stage2 queried live WDQS and then wrote local frozen shards/checkpoints. No local candidate input cache was configured.

8. **Is there command/log evidence for Stage1 and Stage2 execution?**  
   Partial. The run manifest and production log confirm execution and WDQS collection. The exact shell command was not found.

9. **Are Stage2 shard counts consistent with R2.5?**  
   Yes: 81,958 rows/unique triples, 139 relations, and Stage4 core triples subset of Stage2 shards.

10. **What remains unreproducible because of live WDQS or missing environment/cache?**  
    Exact Stage2 candidate collection rerun, because the historical WDQS state and response order are not frozen and no complete response cache or environment lock was found.

11. **Is Stage1 -> Stage2 evidence confirmed, partial, ambiguous, or unresolved?**  
    Confirmed for local artifacts, code-path dependency, and manifest/log execution. Partial for exact rerun reproducibility.
