# Phase II Stage1/Stage3 Run-Scoped Replay Readiness

This document describes Level 2 Slice 2 in the reusable KG pipeline runner. The slice is a readiness check for historical Phase II Stage1 and Stage3 replay. It does not run graph construction, submit SLURM jobs, query WDQS, call LLMs, or write into historical run directories.

## Command

```bash
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen --dry-run
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen
```

If the default run root is unavailable in a restricted execution context, the same replay can be directed to an alternate state root:

```bash
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen --state-root /tmp/kg_pipeline_runs_test
```

The state-root override affects only pipeline state, logs, and run-scoped replay outputs. It does not redirect canonical inputs or historical graph/data artifacts.

## Enabled Readiness Stages

The runner now includes these Phase II readiness stages in `replay-frozen` mode:

- `phase2_stage1_genericity_scoring`
- `phase2_stage3_candidate_audit`

Both stages are validation-only in this slice. The runner writes one shared readiness report under:

```text
outputs/pipeline_runs/<run_id>/phase2_replay/
```

Required outputs are:

- `stage1_stage3_replay_readiness_report.json`
- `stage1_stage3_replay_readiness_summary.md`

## What Stage1 Readiness Checks

Stage1 readiness verifies that the historical relation-balanced pipeline script, historical manifest/config snapshot, allocation file, canonical allocation file, and support matrix file exist. It also verifies that the archive allocation hash matches the canonical allocation hash:

```text
a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb
```

The readiness report records the corrected future command shape:

```bash
python archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py \
  --config outputs/pipeline_runs/<run_id>/phase2_replay/historical_relation_pipeline_run/config_snapshot.yaml \
  --run-dir outputs/pipeline_runs/<run_id>/phase2_replay/historical_relation_pipeline_run \
  score-genericity
```

The command is recorded only. It is not executed in this slice.

## What Stage3 Readiness Checks

Stage3 readiness verifies that frozen Stage2 candidate shards are present under:

```text
archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards/
```

The report counts shard files, non-empty shard files, and candidate rows. It records the corrected future command shape:

```bash
python archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py \
  --config outputs/pipeline_runs/<run_id>/phase2_replay/historical_relation_pipeline_run/config_snapshot.yaml \
  --run-dir outputs/pipeline_runs/<run_id>/phase2_replay/historical_relation_pipeline_run \
  audit-candidates
```

The command is recorded only. It is not executed in this slice.

## Historical Command Correction

The manifest previously represented historical Phase II stages with pseudo `--stage` arguments. The historical script does not expose that interface. It requires `--config`, `--run-dir` or `--run-name`, and a subcommand such as `score-genericity` or `audit-candidates`.

This slice corrects that mapping in the runner contract without enabling execution. A future replay implementation must create a fresh run directory under `outputs/pipeline_runs/<run_id>/phase2_replay/`, prepare a run-scoped config snapshot, and make Stage2 shards available under the run-scoped layout before executing the historical subcommands.

## Boundary

Stage1 and Stage3 are prepared for future run-scoped replay, but B0 regeneration is still blocked. Stage4 graph construction, Stage5 repair, Stage6 refinement, Stage7 eta-aware replacement, Stage11/Stage12 repair, and C1 Stage13 remain disabled.

This slice modifies no graph/data artifacts outside `outputs/pipeline_runs/`.
