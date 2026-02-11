# balanced_kg_benchmark

Clean project layout and placement rules.

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
