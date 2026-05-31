# balanced_kg_benchmark

Clean project layout and placement rules.

## Reusable KG Pipeline Quickstart

The primary reproducible interface is the non-interactive CLI runner, not Streamlit. Streamlit remains optional for Phase I inspection, manual threshold selection, and config/allocation export. Any Streamlit decision must be saved into a config or artifact before it becomes part of a reproducible run.

List the pipeline stages:

```bash
python scripts/pipeline/run_kg_pipeline.py --list-stages
```

Dry-run the safe frozen validation path:

```bash
python scripts/pipeline/run_kg_pipeline.py --mode validate-frozen --dry-run
```

Run frozen validation:

```bash
python scripts/pipeline/run_kg_pipeline.py --mode validate-frozen
```

Run the current Level 2 replay slices. This materializes Phase I allocation and genericity matrix exports under the run directory, then validates Phase II Stage1/Stage3 replay readiness without executing historical graph construction:

```bash
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen --dry-run
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen
```

Show the latest run status:

```bash
python scripts/pipeline/run_kg_pipeline.py --status
```

Level 1 candidate construction packages existing frozen registered candidates only; it does not generate graphs:

```bash
python scripts/pipeline/run_kg_pipeline.py --mode construct-candidates --candidate-id B0 --from-frozen
python scripts/pipeline/run_kg_pipeline.py --mode construct-candidates --candidate-id C1 --from-frozen
```

Live and SLURM modes parse cleanly but remain blocked in this foundation:

```bash
python scripts/pipeline/run_kg_pipeline.py --mode live-rerun --allow-live
python scripts/pipeline/run_kg_pipeline.py --mode slurm-rerun --allow-slurm
```

State, resolved manifests, and per-stage logs are written under:

```text
outputs/pipeline_runs/<run_id>/
```

Use `--state-root PATH` or `KG_PIPELINE_STATE_ROOT=PATH` to send run state and logs to another root when the default output directory is unavailable in a restricted execution context. This only changes pipeline-run bookkeeping; it does not change canonical graph/data artifact paths.

Execution classes in `configs/pipeline/kg_pipeline.default.json`:

- `frozen_validation` — read-only checks against committed metadata and restored frozen artifacts.
- `deterministic_replay` — local replay over frozen files, without live services.
- `driftable_live_wdqs` — stages that may query live WDQS and can drift.
- `driftable_live_llm` — stages that may call an LLM/API and can drift.
- `slurm_expensive` — expensive batch stages historically run through SLURM.
- `graph_construction` — stages that build, repair, prune, or emit graph candidates.
- `manual_ui_optional` — optional UI stages such as the Phase I Streamlit dashboard.

In the current foundation, live WDQS/LLM execution, SLURM submission, and new graph generation are blocked. `replay-frozen` enables the safe Phase I run-scoped replay/export slice plus Phase II Stage1/Stage3 readiness validation. It writes `phase1_replay/allocation.replayed.json`, `phase1_replay/genericity_support_matrix.replayed.json`, `phase1_replay/phase1_replay_report.json`, and `phase2_replay/stage1_stage3_replay_readiness_report.json` under `outputs/pipeline_runs/<run_id>/`; canonical Phase I artifacts and historical Stage2 shards are read for comparison/readiness only. `construct-candidates --from-frozen` can package existing registered frozen candidates into a pipeline run directory for inspection and evaluation. The manifest records blocked stages so users can inspect the A-to-Z workflow without accidentally rerunning driftable or expensive stages.

Detailed runner documentation: `docs/reconstruction/70_reusable_A_to_Z_pipeline_runner.md`

B0 is the current provisional connected baseline, not a final balanced KG. See:

- `docs/reconstruction/68_final_endpoint_and_branch_synthesis.md`
- `docs/reconstruction/69_B0_provisional_baseline_status_audit.md`

## Folder structure

- `src/` — main Python code.
- `src/archive/` — old/backup scripts kept for reference only.
- `scripts/slurm/` — SLURM job scripts.
- `data/raw/` — input datasets (source JSON/JSONL).
- `data/processed/` — generated outputs/checkpoints.
- `docs/` — documentation and conventions.

## What to put where

- New production Python files: `src/`
- Experimental one-off scripts: `src/archive/` (or promote to `src/` later)
- New SLURM scripts: `scripts/slurm/`
- Input files from external sources: `data/raw/`
- Results from runs (`*.jsonl`, checkpoints): `data/processed/`

## Current key files

- Main job script: `scripts/slurm/hop_support.slurm`
- Main program: `src/hop_support.py`
- Example raw input: `data/raw/wikidata_ontology.hop_discovery_run2.json`

## Run (SLURM)

```bash
sbatch --export=ALL,USER_AGENT='hop_support/1.0 (mailto:you@example.com)' scripts/slurm/hop_support.slurm
```

You can override paths with env vars, for example:

```bash
sbatch --export=ALL,INPUT_PATH=data/raw/your_input.jsonl,OUTPUT_JSONL=data/processed/your_run.jsonl,CHECKPOINT_PATH=data/processed/your_run_checkpoint.json,USER_AGENT='hop_support/1.0 (mailto:you@example.com)' scripts/slurm/hop_support.slurm
```
