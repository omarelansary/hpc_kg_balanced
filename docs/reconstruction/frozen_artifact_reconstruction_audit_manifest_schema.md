# Frozen-Artifact Reconstruction Audit Manifest Schema

This document describes the runtime manifest written by:

`scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh`

Default runtime manifest path:

`artifacts/final_graph/selected_final_graph/rebuild/runs/${RUN_ID}_frozen_artifact_reconstruction_audit_manifest.json`

The older fixed-path manifest remains historical evidence:

`artifacts/final_graph/selected_final_graph/rebuild/frozen_artifact_reconstruction_audit_manifest.json`

New runs should not write to the fixed historical path unless `RECON_AUDIT_MANIFEST_OUT` is explicitly set to that path.

## Stable Fields

These fields describe the schema and audit contract and should remain stable across runs unless the entrypoint behavior changes:

| Field | Meaning |
|---|---|
| `schema_version` | Runtime manifest schema identifier. Current value: `reconstruction-audit-runtime-manifest-v2`. |
| `created_by` | Entrypoint script that wrote the manifest. |
| `entrypoint` | Entrypoint script path. |
| `mode` | `default` or `force`. |
| `inputs` | Paths for B0 graph, allocation, Stage11 graph output, and Stage12 graph output. |
| `outputs.expected` | Expected child-wrapper output paths. |
| `scripts_run` | Child wrappers invoked by the entrypoint and their exit codes. |
| `validation_results` | JSON/TSV validation records for expected outputs. |
| `validation_status` | Aggregate validation status. |
| `key_hashes` | Pre-run and post-run hashes for B0, allocation, Stage11 graph output, and Stage12 graph output. |
| `overall_status` | Aggregate audit result. |
| `explicit_notes` | Boundary notes: frozen-artifact validation only, no graph generation, no WDQS, no LLM, not full end-to-end reproduction. |

## Volatile Fields

These fields are expected to change across runs and should not be used as stable provenance identifiers:

| Field | Why it is volatile |
|---|---|
| `timestamp` | Current UTC run time. |
| `run_id` | Defaults to current UTC timestamp; may be overridden by `RECON_AUDIT_RUN_ID`. |
| `manifest_out` | Depends on run ID or `RECON_AUDIT_MANIFEST_OUT`. |
| `git_commit` | Changes when repository history advances. |
| `runtime_git_status` | Disabled by default; when enabled, can include dirtiness caused by runtime outputs. |
| `output_files_present_after_run` | Depends on which child outputs exist and whether child wrappers ran successfully. |
| `scripts_run[].exit_code` | Depends on default versus force mode and existing outputs. |
| `scripts_run[].status` | Depends on child wrapper execution. |
| `validation_status` | Depends on child wrapper execution and output presence. |

## Environment Controls

| Variable | Default | Purpose |
|---|---|---|
| `RECON_AUDIT_RUN_ID` | UTC timestamp `YYYYMMDDTHHMMSSZ` | Sets runtime manifest run ID. |
| `RECON_AUDIT_MANIFEST_OUT` | `${RECON_REBUILD_DIR}/runs/${RUN_ID}_frozen_artifact_reconstruction_audit_manifest.json` | Redirects runtime manifest path. |
| `RECON_CAPTURE_GIT_STATUS` | `0` | When `0`, records `runtime_git_status: "not_captured"`; when `1`, records relevant `git status --short` lines. |

## Interpretation

A passing runtime manifest means the frozen-artifact wrappers completed, key hashes matched, graph outputs did not change during the audit, and expected JSON/TSV outputs validated.

It does not mean the thesis pipeline is fully reproducible from live WDQS or LLM inputs. It validates the frozen historical artifacts and rebuild/audit metadata only.
