# Reusable A-To-Z Pipeline Runner

## Purpose

This document describes the first non-interactive runner foundation for the KG construction pipeline. The runner is intended to let a new user list stages, inspect a manifest, run safe frozen validations, resume stateful runs, and understand which stages are frozen, replayable, live, expensive, or graph-generating.

This implementation does not rebuild the graph and does not rerun live evidence collection. It creates orchestration structure only.

## Files Added

- `src/kg_pipeline/orchestration/__init__.py`
- `src/kg_pipeline/orchestration/pipeline_manifest.py`
- `src/kg_pipeline/orchestration/pipeline_state.py`
- `src/kg_pipeline/orchestration/pipeline_runner.py`
- `scripts/pipeline/run_kg_pipeline.py`
- `configs/pipeline/kg_pipeline.default.json`

## Execution Classes

Each stage in `configs/pipeline/kg_pipeline.default.json` has one execution class:

| Execution class | Meaning | Default behavior |
| --- | --- | --- |
| `frozen_validation` | Read-only checks against committed metadata and restored frozen artifacts. | Can run in `validate-frozen`. |
| `deterministic_replay` | Local deterministic replay over frozen files, without live services. | Listed and allowed in `replay-frozen` when explicitly enabled by policy. |
| `driftable_live_wdqs` | Stages that may query live WDQS and can drift over time. | Blocked unless future live mode is explicitly enabled with `--allow-live`. |
| `driftable_live_llm` | Stages that may call an LLM or API and can drift over time. | Blocked unless future live mode is explicitly enabled with `--allow-live`. |
| `slurm_expensive` | Expensive batch stages historically run through SLURM. | Blocked unless future SLURM mode is explicitly enabled with `--allow-slurm`. |
| `graph_construction` | Stages that build, repair, prune, or emit candidate graphs. | Not implemented in this foundation runner. |
| `manual_ui_optional` | Optional manual UI stages such as Streamlit inspection dashboards. | Disabled by default and not part of non-interactive validation. |

## CLI

Runner entrypoint:

```bash
python scripts/pipeline/run_kg_pipeline.py --manifest configs/pipeline/kg_pipeline.default.json --list-stages
```

Supported modes and inspection flags:

```bash
python scripts/pipeline/run_kg_pipeline.py --list-stages
python scripts/pipeline/run_kg_pipeline.py --mode validate-frozen --dry-run
python scripts/pipeline/run_kg_pipeline.py --mode validate-frozen
python scripts/pipeline/run_kg_pipeline.py --status
python scripts/pipeline/run_kg_pipeline.py --mode replay-frozen --dry-run
python scripts/pipeline/run_kg_pipeline.py --mode live-rerun --dry-run
python scripts/pipeline/run_kg_pipeline.py --mode slurm-rerun --dry-run
python scripts/pipeline/run_kg_pipeline.py --mode construct-candidates --dry-run
```

`live-rerun` refuses execution unless `--allow-live` is provided. In this foundation implementation, live WDQS/LLM stages remain blocked even with `--allow-live`; the flag is reserved for a future audited implementation. The default manifest keeps live stages disabled because they are driftable and are not part of frozen validation.

`slurm-rerun` is accepted as a reserved mode and can inspect SLURM stages, but SLURM submission is blocked in this foundation implementation.

`construct-candidates` implements Level 1 packaging for existing frozen registered candidates. With `--candidate-id B0 --from-frozen` or `--candidate-id C1 --from-frozen`, it copies the existing registry graph into the pipeline run directory, verifies the graph hash, runs the standard evaluator, and writes a package manifest. It does not generate, prune, repair, or otherwise modify graph artifacts. The `--generate` flag remains blocked because graph generation is not implemented in Level 1.

The CLI runner is the canonical interface for non-interactive reproducibility. The Streamlit dashboard is represented only as an optional Phase I manual UI for inspecting evidence, selecting thresholds, and exporting allocation/config artifacts. Any Streamlit decision must be exported to a saved config or artifact before it becomes reproducible. Canonical pipeline runs consume saved configs and artifacts, not live UI state. HPC and SLURM stages should not depend on Streamlit.

## State And Logs

Each non-dry run writes a run directory under:

```text
outputs/pipeline_runs/<run_id>/
```

The run directory contains:

- `pipeline_state.json`
- `manifest.resolved.json`
- `logs/<stage_id>.log`
- `candidates/<candidate_id>/` for Level 1 frozen candidate packages

State is written before and after each stage, so an interrupted run can be inspected. `--resume` loads the latest state file under `outputs/pipeline_runs/` and skips previously passed stages unless a stage is named with `--force-stage`.

## Default Validate-Frozen Stages

The safe default mode runs only existing frozen validation checks:

1. `validate_required_artifacts`
2. `validate_frozen_reconstruction`
3. `validate_candidate_registry`
4. `validate_candidate_evaluation_compatibility`

The frozen reconstruction stage writes its runtime manifest into the pipeline run directory through `RECON_AUDIT_MANIFEST_OUT`, not into the committed rebuild directory.

## A-To-Z Coverage In The Manifest

The default manifest records the A-to-Z pipeline shape even when most stages are disabled by default:

- relation metadata and relation universe;
- hop discovery;
- hop support;
- symmetry, anti-symmetry, and inverse evidence;
- composition verification;
- LLM relation/profile classification;
- optional Streamlit dashboard for Phase I inspection and threshold/config export;
- Phase I allocation export;
- support/genericity matrix export;
- Stage1 genericity scoring;
- Stage2 candidate collection;
- Stage3 candidate audit;
- Stage4 core graph construction;
- Stage5 repair;
- Stage6 refinement;
- Stage7 eta-aware replacement;
- Stage11 connectivity repair;
- Stage12 path repair;
- B0 largest-component extraction;
- C1 Stage13 pruning candidate evidence.

The manifest is an orchestration contract. It does not claim all historical stages are currently reproducible from a fresh clone.

## Not Implemented Yet

This foundation intentionally does not:

- query WDQS;
- call LLMs;
- submit SLURM jobs;
- run Streamlit as part of canonical non-interactive execution;
- generate new graphs;
- modify graph/data artifacts;
- replace historical Phase II generator code;
- solve live reproducibility drift.

Future work can add guarded replay implementations stage by stage, but live and graph-construction paths should remain opt-in and auditable.
