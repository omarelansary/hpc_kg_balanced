# Phase I Run-Scoped Replay

This document describes the first Level 2 replay slice in the reusable KG pipeline runner. The slice is intentionally limited to deterministic Phase I evidence replay and export. It does not run graph construction, submit SLURM jobs, query WDQS, call LLMs, or modify historical artifacts.

## Command

```bash
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen --dry-run
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen
```

## Enabled Stages

The runner enables these Phase I replay stages in `replay-frozen` mode:

- `phase1_symmetry_inverse_evidence` validates extracted Phase I logic against frozen hop-support and composition inputs.
- `phase1_allocation_export` materializes the replayed allocation under the pipeline run directory and compares it to the canonical allocation artifact.
- `phase1_support_genericity_matrix_export` validates the replayed support/genericity matrix against the canonical matrix artifact.

Frozen validation stages also run in `replay-frozen`; graph construction, live WDQS/LLM stages, SLURM stages, and historical Phase II generation remain skipped or blocked.

## Run-Scoped Outputs

Each run writes Phase I replay outputs under:

```text
outputs/pipeline_runs/<run_id>/phase1_replay/
```

Required outputs are:

- `allocation.replayed.json`
- `genericity_support_matrix.replayed.json`
- `phase1_replay_report.json`
- `phase1_replay_summary.md`

The canonical comparison inputs are read-only:

- `src/Pruning graph/bidirectional_allocation_results5k.json`
- `archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json`

If replayed output differs from the canonical artifact, the report records the mismatch and the pipeline stage fails. The runner does not overwrite canonical files.

## Expected Counts

The replay keeps the Phase I golden-master pattern group counts:

| Pattern | Count |
| --- | ---: |
| symmetric | 18 |
| anti_symmetric | 66 |
| inverse | 44 |
| composition | 26 |

## Boundary

This slice is not B0 or C1 regeneration. It only confirms that the extracted Phase I logic can replay the allocation and genericity matrix exports into a run directory. Historical Phase II graph construction still needs run-directory wrappers, live-source guards, and SLURM job-state tracking before it can be enabled.
