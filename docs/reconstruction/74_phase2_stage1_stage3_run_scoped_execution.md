# Phase II Stage1/Stage3 Run-Scoped Execution

This document describes Level 2 Slice 3 in the reusable KG pipeline runner. The slice executes only the historical Phase II Stage1 `score-genericity` and Stage3 `audit-candidates` subcommands in a fresh pipeline run directory.

## Command

```bash
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen --dry-run
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen
```

When the default run root is unavailable in a restricted execution context, use:

```bash
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen --state-root /tmp/kg_pipeline_runs_test
```

## Run-Scoped Directory

The historical subcommands run with `--run-dir` pointing to:

```text
<run_dir>/phase2_replay/historical_relation_pipeline_run/
```

The runner writes a run-scoped `config_snapshot.json` in that directory. The config is generated from the historical config snapshot and changes only the fields needed to keep execution local and frozen:

- `run_root` points under the pipeline run directory.
- `allocated_relations_path` points to the frozen archive allocation file.
- `support_matrix_path` points to the frozen archive support matrix file.
- `candidate_source_mode` is set to `local` to prevent WDQS fallback.
- `candidate_input_path` points to run-scoped Stage2 shard links.

Frozen Stage2 candidate shards are materialized under:

```text
<run_dir>/phase2_replay/historical_relation_pipeline_run/stage02_candidates/shards/
```

The runner prefers symlinks to the frozen historical shards. Original shards are not modified.

## Executed Commands

Only these commands are executed:

```bash
python archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py \
  --config <run_dir>/phase2_replay/historical_relation_pipeline_run/config_snapshot.json \
  --run-dir <run_dir>/phase2_replay/historical_relation_pipeline_run \
  score-genericity

python archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py \
  --config <run_dir>/phase2_replay/historical_relation_pipeline_run/config_snapshot.json \
  --run-dir <run_dir>/phase2_replay/historical_relation_pipeline_run \
  audit-candidates
```

## Outputs

The execution slice writes:

- `phase2_replay/stage1_stage3_replay_readiness_report.json`
- `phase2_replay/stage1_stage3_replay_readiness_summary.md`
- `phase2_replay/stage1_stage3_execution_report.json`
- `phase2_replay/stage1_stage3_execution_summary.md`
- `phase2_replay/historical_relation_pipeline_run/stage01_genericity/relation_genericity.jsonl`
- `phase2_replay/historical_relation_pipeline_run/stage01_genericity/summary.json`
- `phase2_replay/historical_relation_pipeline_run/stage03_candidate_audit/candidate_relation_audit.jsonl`
- `phase2_replay/historical_relation_pipeline_run/stage03_candidate_audit/summary.json`

## Boundary

This slice does not run Stage2 candidate collection, Stage5 repair, Stage6 refinement, Stage7 eta-aware replacement, Stage11/Stage12 repair, or C1 Stage13. It does not submit SLURM jobs, query WDQS, call LLMs, update the candidate registry, or regenerate B0.

Level 2 Slice 4 adds a separate run-scoped wrapper for Stage4 `construct-graph`; because that historical stage is long-running, it is guarded by `--execute-stage4`. B0 regeneration is still not safe through the runner after Stage4 because Stage5/6/7, Stage11/12, largest-component extraction, and final endpoint validation remain disabled.
