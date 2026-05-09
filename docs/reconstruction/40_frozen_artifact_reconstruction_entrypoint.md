# Frozen-Artifact Reconstruction Entrypoint

Entrypoint:

`scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh`

Run manifest:

`artifacts/final_graph/selected_final_graph/rebuild/frozen_artifact_reconstruction_audit_manifest.json`

## What It Does

This wrapper runs the existing reconstruction wrappers in a fixed order over frozen local artifacts:

1. `scripts/reconstruction/01_audit_B0_final_graph.sh`
2. `scripts/reconstruction/02_register_B0_final_manifest.sh`
3. `scripts/reconstruction/03_path_translation_manifest.sh`
4. `scripts/reconstruction/04_verify_stage7_to_B0_chain.sh`
5. `scripts/reconstruction/05_verify_stage6_to_B0_chain.sh`
6. `scripts/reconstruction/06_verify_stage5_to_B0_chain.sh`
7. `scripts/reconstruction/07_verify_stage3_to_B0_chain.sh`

It validates that the selected B0 graph and canonical allocation hashes match the registered values:

- B0 graph SHA256: `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`
- Canonical allocation SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

It also validates generated JSON files with `python -m json.tool`, validates generated TSV row shape, records child-wrapper exit status, and writes a machine-readable run manifest.

## What It Does Not Do

This is not full end-to-end reproduction.

It does not:

- query WDQS,
- call an LLM,
- generate a graph,
- run pruning,
- refactor code,
- move or rewrite historical artifacts,
- replay the missing Streamlit dashboard export session,
- replay the missing exact LLM production run,
- prove exact Stage2 WDQS rerun reproducibility.

It validates frozen historical artifacts and rebuilds audit/manifest outputs only.

## Required Assumptions

- The repository contains the Hetzner archive evidence used in R2.2-R2.7.
- The selected final graph remains B0:
  `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- The canonical allocation remains:
  `src/Pruning graph/bidirectional_allocation_results5k.json`
- Existing child wrappers remain wrapper-only and do not generate graph data.
- Existing rebuild outputs may already exist. In that case, normal mode will fail when child wrappers refuse overwrite; use `--force` to rebuild audit outputs.

## Commands

Dry run:

```bash
bash scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh --dry-run
```

Default mode:

```bash
bash scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh
```

Force mode:

```bash
bash scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh --force
```

## Interpretation of Success

Success means:

- all child reconstruction wrappers completed,
- B0 and allocation hashes matched expected values before and after the audit,
- key graph-output hashes were unchanged during the audit,
- generated JSON reports parsed successfully,
- generated TSV files had consistent row width,
- the run manifest was written and parsed successfully.

Success does not mean the full thesis pipeline can be rerun from live upstream sources. It means the frozen-artifact evidence chain and documentation rebuild checks are internally consistent.

## Remaining Reproducibility Gaps

The entrypoint preserves the status from `docs/reconstruction/39_final_reconstruction_status_summary.md`:

- exact dashboard export session missing,
- exact LLM production run/raw responses missing,
- full Phase I-to-final end-to-end rerun not established,
- v3 domain/range enrichment command/log incomplete,
- Stage2 WDQS exact rerun/cache incomplete,
- support matrix same-run linkage to allocation missing,
- inverse LLM side branch incomplete.

## Why This Is The Safe Boundary Before Refactor

This wrapper is the conservative boundary because it validates the frozen evidence chain without changing historical artifacts or regenerating scientific outputs. It provides a stable audit command that can be run before and after future code changes to confirm that the selected B0 graph, canonical allocation, and Stage4-to-B0 reconstruction evidence still match their registered hashes.

Code refactor should start only around this boundary:

- add clean orchestration,
- parameterize canonical paths,
- preserve old artifacts as frozen evidence,
- add manifests and command capture,
- avoid moving or renaming historical provenance folders until after archival.
