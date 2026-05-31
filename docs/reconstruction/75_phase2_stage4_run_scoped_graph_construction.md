# Phase II Stage4 Run-Scoped Core Graph Construction

This document describes Level 2 Slice 4 in the reusable KG pipeline runner. The slice provides a guarded wrapper for executing only the historical Phase II Stage4 `construct-graph` subcommand after Stage1 and Stage3 have passed in the same run-scoped historical pipeline directory.

Stage4 is skipped by default because the historical implementation repeatedly rescans frozen candidate shards while selecting triples and can be long-running. Intentional Stage4 validation requires `--execute-stage4`.

## Verified Historical Entry Point

The historical script is:

```text
archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py
```

Its argparse command table maps `construct-graph` to `stage_construct_graph`. That function writes the Stage4 outputs under `stage04_core_graph/` in the supplied `--run-dir`.

## Command

```bash
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen --dry-run --execute-stage4 --state-root /tmp/kg_pipeline_runs_test
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen --execute-stage4 --state-root /tmp/kg_pipeline_runs_test
```

The Stage4 command executed by the runner has this shape:

```bash
python archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py \
  --config <run_dir>/phase2_replay/historical_relation_pipeline_run/config_snapshot.json \
  --run-dir <run_dir>/phase2_replay/historical_relation_pipeline_run \
  construct-graph
```

## Inputs

Stage4 consumes only run-scoped or frozen-local inputs:

- run-scoped Stage1 output under `stage01_genericity/`
- run-scoped Stage2 shard links under `stage02_candidates/shards/`
- run-scoped Stage3 output under `stage03_candidate_audit/`
- frozen archive allocation and support matrix paths recorded in `config_snapshot.json`

The historical archive run directory is never used as an output target.

## Outputs

The runner writes Stage4 reports under:

```text
<run_dir>/phase2_replay/
```

Required report outputs:

- `stage4_core_graph_execution_report.json`
- `stage4_core_graph_execution_summary.md`

The historical Stage4 command writes its graph outputs under:

```text
<run_dir>/phase2_replay/historical_relation_pipeline_run/stage04_core_graph/
```

Expected Stage4 outputs:

- `core_graph_triples.jsonl`
- `core_graph_selection_log.jsonl`
- `core_graph_relation_counts.json`
- `core_graph_component_report.json`

## Boundary

This slice does not run Stage5 repair, Stage6 refinement, Stage7 eta-aware replacement, Stage11/Stage12 repair, B0 largest-component extraction, or C1 Stage13. It does not submit SLURM jobs, query WDQS, call LLMs, or update `candidate_registry.v1.json`.

The Stage4 output is an intermediate run-scoped core graph. It is not B0, and B0 regeneration remains incomplete until the later graph-repair and endpoint-selection stages have separate guarded wrappers and validation.
