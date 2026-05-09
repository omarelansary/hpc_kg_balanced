# Stage7 Implementation Provenance

This document investigates which code produced the Stage7 graph that feeds the selected B0 final graph chain.

## Conclusion

**Status: confirmed, with one bounded caveat.**

The Stage7 artifact used in the B0 chain was produced by the standalone archived script:

`archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py`

It was not the original `stage07_filtering` step executed inside `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py`. The monolithic pipeline produced an earlier non-eta-aware Stage7 output under `stage07_filtering/`, but that output was superseded by the standalone eta-aware replacement under `stage07_filtering_eta_aware_prod/`.

The caveat is that no shell script or SLURM submission script containing the exact command line was found in the copied workspace. The command can be reconstructed from the Stage7 manifest arguments and production log, but the literal shell invocation remains incomplete provenance.

## Evidence Summary

| Question | Answer | Evidence | Confidence |
|---|---|---|---|
| Which script most likely produced Stage7? | `archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py` | Stage7 manifest records script `/home/kg_benchmark/src/kg_builder/eta_aware_component_filter.py`; local archived source exists at `archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py`; production log is `archive/hetzner_version/logs/eta_aware_component_filter_prod.out` | High |
| Was it part of `relation_balanced_kg_pipeline.py`? | The final B0-chain Stage7 was a separate later script, not the monolithic pipeline Stage7 output. | Source docstring says "Standalone eta-aware replacement for stage07 component filtering"; Stage7 manifest writes `stage07_filtering_eta_aware_prod`; run-level monolithic manifest contains earlier `stage07_filtering` with different counts | High |
| What command/log evidence exists? | Dedicated log confirms a production run from 2026-03-19 17:26:20+01:00 to 17:26:32+01:00. Exact shell command file not found. | `archive/hetzner_version/logs/eta_aware_component_filter_prod.out`; `stage07_filtering_eta_aware_prod/manifest.json` | Medium-high |
| What input did Stage7 consume? | Stage6 refined graph and 5k allocation. | Summary says `prefilter_source=stage06_refine_graph`, `input_triples=18513`; log says loaded 18,513 rows from `/home/kg_benchmark/runs/prod_refine_20260315_180520/stage06_refine_graph/refined_graph_triples.jsonl`; allocation path is `src/kg_builder/input/bidirectional_allocation_results5k.json` | High |
| What output did Stage7 produce? | `stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`, 17,965 rows/unique triples, 139 relations. | `stage07_filtering_eta_aware_prod/summary.json`; `docs/reconstruction/27_stage6_to_B0_chain_verification.md`; `stage6_to_B0_chain_verification.json` | High |
| Are counts consistent with R2.3? | Yes. | R2.3 verified 18,513 Stage6 triples, 17,965 Stage7 triples, and 548 removed triples. Stage7 summary/progress/log record the same transition. | High |
| Does this change the verified Stage4 -> B0 chain? | No. It clarifies implementation provenance only. | Existing R2.3/R2.4/R2.5 verification files remain consistent with this Stage7 path. | High |

## Script Evidence

The archived standalone script begins with a direct provenance statement:

`archive/hetzner_version/src/kg_builder/eta_aware_component_filter.py`

- Script SHA256: `bfbc2958e4ae650b1cd93533415665a3930908b1520ca43b7feab24aa2643261`
- The source header describes it as a "Standalone eta-aware replacement for stage07 component filtering".
- The header says it is designed to run on an existing pipeline run directory before patching `relation_balanced_kg_pipeline.py`.
- The CLI parser description is `Standalone eta-aware stage07 replacement filter.`
- The default output directory is `<run_dir>/stage07_filtering_eta_aware`.
- The actual production run used `stage07_filtering_eta_aware_prod`.

Relevant implementation behavior:

- `combine_prefilter_rows()` first looks for `stage06_refine_graph/refined_graph_triples.jsonl`.
- If Stage6 is absent, it falls back to `stage04_core_graph/core_graph_triples.jsonl` plus `stage05_repair/repair_triples.jsonl`.
- `resolve_allocation_path()` reads `allocated_relations_path` from the run manifest unless an override is provided.
- `existing_stage07_summary()` compares against the earlier monolithic `stage07_filtering/filtered_graph_triples.jsonl` if it exists.
- `write_outputs()` writes `filtered_graph_triples.jsonl`, `component_filter_report.json`, `summary.json`, `comparison_to_existing_stage07.json`, and `relation_retention_report.csv`.

## Manifest Evidence

Production Stage7 manifest:

`archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/manifest.json`

Hash:

`dda38ff4990088601ce4efb317ade1cbecda2da0baf1519dcc818c93f28baa7e`

Recorded fields:

| Field | Value |
|---|---|
| `script` | `/home/kg_benchmark/src/kg_builder/eta_aware_component_filter.py` |
| `status` | `completed` |
| `started_at` | `2026-03-19T16:26:20.429148+00:00` |
| `completed_at` | `2026-03-19T16:26:32.492786+00:00` |
| `run_dir` | `/home/kg_benchmark/runs/prod_refine_20260315_180520` |
| `out_dir` | `runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod` |
| `args.run_dir` | `runs/prod_refine_20260315_180520` |
| `args.out_dir` | `runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod` |
| `args.eta_keep_ratio` | `0.95` |
| `args.weak_component_min_triples` | `3` |
| `args.weak_component_min_entities` | `3` |
| `args.progress_every` | `1` |
| `args.verbose` | `true` |
| `args.input_graph_path` | `null` |
| `args.allocation_path` | `null` |
| `args.force` | `false` |

Because `input_graph_path` and `allocation_path` are null, the script resolved both from the existing run directory and run manifest.

## Log Evidence

Production log:

`archive/hetzner_version/logs/eta_aware_component_filter_prod.out`

Hash:

`74889ae5711647c249692e45c26e931c1b008f242f249d998f08080f934c35d9`

Important log facts:

- Run starts with `START eta_aware_component_filter production run`.
- It loaded 139 positive-eta allocations from `src/kg_builder/input/bidirectional_allocation_results5k.json`.
- It loaded 18,513 pre-filter rows from `/home/kg_benchmark/runs/prod_refine_20260315_180520/stage06_refine_graph/refined_graph_triples.jsonl`.
- It built 6,524 weak components.
- It completed with 6,021 kept components, 503 removed components, 17,965 kept triples, and 548 removed triples.
- It wrote output artifacts to `runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod`.
- Run ended with `DONE eta_aware_component_filter production run`.

The log does not include the literal shell command line. The manifest argument block is therefore the strongest command reconstruction evidence.

## Output Evidence

Primary final-chain Stage7 output:

`archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`

Hash:

`c7d5132bd0b20aa0da4a64ecbf183abf412c3effca38bef84105c7791126fb4b`

Counts:

| Metric | Value | Evidence |
|---|---:|---|
| Input triples | 18,513 | Stage7 summary/log; `docs/reconstruction/27_stage6_to_B0_chain_verification.md` |
| Kept triples | 17,965 | Stage7 summary/progress/log; R2.3 verification |
| Removed triples | 548 | Stage7 summary/progress/log; R2.3 verification |
| Input components | 6,524 | Stage7 summary/log |
| Kept components | 6,021 | Stage7 summary/progress/log |
| Removed components | 503 | Stage7 summary/progress/log |
| Realized relations before | 139 | Stage7 summary |
| Realized relations after | 139 | Stage7 summary |
| Total postfilter deficit | 2,035 | Stage7 summary |

Additional output artifacts:

- `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/component_filter_report.json`
- `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/relation_retention_report.csv`
- `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/comparison_to_existing_stage07.json`
- `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/progress.json`
- `archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/eta_analysis/summary.json`

## Contrast With Monolithic Pipeline Stage7

The archived monolithic pipeline contains its own `stage_filter_components()` implementation:

`archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py`

Hash:

`a1fec8c08783b3816ebc28e16f39499fb6be2f2a4d587948a00fa4fb9082a5e7`

Its `run-all` sequence includes:

`stage01_genericity -> stage02_candidates -> stage03_candidate_audit -> stage04_core_graph -> stage05_repair -> stage06_refine_graph -> stage07_filtering -> stage08_final_audit`

The run-level manifest shows that this original `stage07_filtering` completed earlier:

`archive/hetzner_version/runs/prod_refine_20260315_180520/manifest.json`

Hash:

`918546ec1c0f5e02e99f6b09d9dc8d8a6d3caa16ccd1cb31f3ab26d6cd3eaff9`

Recorded original Stage7 values:

| Original monolithic Stage7 metric | Value |
|---|---:|
| `stage07_filtering.kept_triples` | 10,779 |
| `stage07_filtering.removed_components` | 5,847 |
| `stage08_final_audit.realized_allocated_relations` | 136 |
| `stage08_final_audit.unrealized_allocated_relations` | 3 |

The standalone eta-aware script explicitly compared against this older output. Its `comparison_to_existing_stage07.json` records:

| Existing original Stage7 comparison metric | Value |
|---|---:|
| `existing_stage07_triples` | 10,779 |
| `existing_stage07_realized_relations` | 136 |
| `existing_stage07_total_deficit` | 9,221 |

This supports the interpretation that the standalone eta-aware Stage7 was a later corrective replacement for the monolithic component filter.

## Downstream Link to Stage11 and B0

Stage11 manifest:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/manifest.json`

Hash:

`2e4ad9130fc41c25a99c22d44aa0c992c0dc24cc9254188af05774c68ac64c85`

It records:

`/home/kg_benchmark/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`

as `inputs.input_triples` and `cli_args.input_triples`.

That stale server path is resolved locally to:

`archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`

by:

- `docs/reconstruction/25_pre_stage11_input_mapping_hetzner_resolution.md`
- `artifacts/final_graph/selected_final_graph/rebuild/path_translation_manifest.v3.json`
- `docs/reconstruction/26_stage7_to_B0_chain_verification.md`

Therefore, the selected B0 chain uses:

`Stage6 refined graph -> standalone eta-aware Stage7 -> Stage11 connectivity repair -> Stage12 path repair -> B0 largest component`

not:

`Stage6 refined graph -> monolithic pipeline stage07_filtering -> B0`

## Reconstructed Command

No exact shell script or SLURM script for this run was found in the copied workspace. Based on the manifest arguments and the local archived script path, the command was equivalent to:

```bash
python src/kg_builder/eta_aware_component_filter.py \
  --run_dir runs/prod_refine_20260315_180520 \
  --out_dir runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod \
  --eta_keep_ratio 0.95 \
  --weak_component_min_triples 3 \
  --weak_component_min_entities 3 \
  --progress_every 1 \
  --verbose
```

This command should be treated as evidence-based reconstruction, not as the recovered literal shell command.

## Answer to User Memory Check

The evidence **supports** the memory that the workflow deviated from the monolithic pipeline to create a new Stage7 and then returned to the downstream repair/output chain.

Evidence:

- The standalone script describes itself as a replacement for Stage7.
- It writes to `stage07_filtering_eta_aware_prod`, not the monolithic `stage07_filtering`.
- It compares itself to the existing monolithic `stage07_filtering`.
- Its output preserves 139 realized relations, while the monolithic `stage07_filtering` preserved only 136.
- Stage11 consumes the eta-aware output path, not the original monolithic Stage7 path.

## Effect on Existing Reconstruction

This investigation does not invalidate the verified Stage4 -> B0 chain. It narrows one provenance point:

- Stage4/Stage5/Stage6 remain verified as before.
- Stage7 is now confirmed as a later standalone eta-aware replacement script.
- Stage11/Stage12/B0 continue to link to that Stage7 output through manifests and hash verification.

Remaining upstream gaps are unchanged:

- Stage2 candidate collection still used `candidate_source_mode: wdqs` and therefore is not proven reproducible from frozen local inputs.
- Exact Stage7 shell submission file is missing.
- Full environment lock remains incomplete.
- Full Phase I-to-Phase II allocation export provenance remains incomplete.
