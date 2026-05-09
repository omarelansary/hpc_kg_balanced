# Reconstruction Wrappers R2

This document records the documentation-first wrapper layer created for the confirmed final B0 chain. The wrappers are intentionally narrow: they re-audit and re-register the selected Stage12 repaired largest component without changing historical pipeline code or graph artifacts.

## Scope

The wrappers cover only the final selected B0 artifact chain:

- Selected graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Canonical allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Duplicate-safe evaluator: `tools/graph_candidate_evaluation/evaluate_graph_candidate.py`
- Final artifact package: `artifacts/final_graph/selected_final_graph/`

They do not reconstruct Phase I end to end, rerun Wikidata queries, call an LLM, generate a new graph, or prove full upstream reproducibility.

## Created Wrappers

| Wrapper | Purpose | Writes |
|---|---|---|
| `scripts/reconstruction/00_common.sh` | Shared strict bash mode, repository-root detection, SHA256, file checks, safe directory creation, and timestamp helpers. | No standalone outputs. |
| `scripts/reconstruction/01_audit_B0_final_graph.sh` | Re-runs the duplicate-safe graph evaluator on B0 and the canonical allocation, after checking the expected graph and allocation hashes. | `artifacts/final_graph/selected_final_graph/rebuild/B0_reaudit.report.json`; `artifacts/final_graph/selected_final_graph/rebuild/B0_reaudit.summary.md` |
| `scripts/reconstruction/02_register_B0_final_manifest.sh` | Builds documentation-only manifest, metrics, and hash files from the existing B0 graph, allocation, final decision files, and B0 reaudit report. | `artifacts/final_graph/selected_final_graph/rebuild/final_graph_manifest.rebuilt.json`; `artifacts/final_graph/selected_final_graph/rebuild/final_graph_metrics.rebuilt.json`; `artifacts/final_graph/selected_final_graph/rebuild/final_graph_hashes.rebuilt.tsv` |
| `scripts/reconstruction/03_path_translation_manifest.sh` | Records stale absolute paths from Stage11/Stage12 manifests and maps the canonical allocation to the local workspace path. It searches for a local equivalent of the stale pre-Stage11 input graph by exact filename. | `artifacts/final_graph/selected_final_graph/rebuild/path_translation_manifest.json` |

All wrappers refuse to overwrite existing outputs unless `--force` is passed.

## Run Order

```bash
bash scripts/reconstruction/01_audit_B0_final_graph.sh
bash scripts/reconstruction/02_register_B0_final_manifest.sh
bash scripts/reconstruction/03_path_translation_manifest.sh
```

The first wrapper must run before the second because `02_register_B0_final_manifest.sh` requires `B0_reaudit.report.json`.

## Hash Guardrails

The B0 graph wrapper verifies:

- B0 graph SHA256: `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`
- Canonical allocation SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

These checks make the R2 wrapper outputs comparable to the selected final graph package without modifying the selected graph or allocation.

## What This Solves

- Provides a repeatable local audit of the selected B0 graph metrics.
- Rebuilds documentation-only final graph manifest files under a separate `rebuild/` directory.
- Captures stale Stage11/Stage12 absolute path translation evidence without editing historical manifests.
- Makes the final selected B0 chain easier to verify after future documentation edits.

## What Remains Unresolved

The wrappers do not resolve these upstream reconstruction gaps:

- LLM provenance for relation-profile and composition target filtering artifacts.
- Inverse verification shard completion.
- Exact allocation export command.
- Support matrix linkage into the canonical 5k allocation.
- Exact B0 largest-component extraction command.
- Stale pre-Stage11 input graph mapping, unless `03_path_translation_manifest.sh` finds a unique local equivalent by exact filename.
- Full end-to-end environment lock and frozen-input reproducibility.

## Evidence Boundaries

These scripts are audit and registration wrappers for the final B0 chain. They should be cited as reconstruction support for the selected graph artifact, not as evidence that the entire original pipeline is rerunnable from scratch.
