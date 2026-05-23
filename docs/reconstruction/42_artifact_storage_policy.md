# Artifact Storage Policy For Frozen Reconstruction Evidence

## Purpose

The reconstruction wrapper layer validates frozen historical evidence for the selected B0 final graph. It does not regenerate graph data, query WDQS, call LLMs, or reproduce the full thesis pipeline end to end.

A fresh Git clone contains the stable code, documentation, and small metadata needed to run the reconstruction wrappers, but it does not contain every frozen evidence artifact required by `--validate-only`. Those evidence artifacts must be restored from a repo-relative external artifact bundle before validation.

## Storage Policy

Git should store small, stable, reviewable files:

- reconstruction wrappers under `scripts/reconstruction/`
- reconstruction documentation under `docs/reconstruction/`
- small final-graph metadata and verification JSON/TSV files under `artifacts/final_graph/selected_final_graph/rebuild/`
- the canonical allocation file `src/Pruning graph/bidirectional_allocation_results5k.json`

Large frozen evidence should stay outside normal Git, either in external storage or Git LFS if that is later adopted:

- Stage11/Stage12 graph outputs and event/state directories
- Hetzner archive evidence under `archive/hetzner_version/`
- large `data/processed/` and `data/raw/` provenance artifacts
- frozen candidate pools
- historical experiment outputs and visualizations

Runtime manifests remain generated outputs and must stay untracked:

- `artifacts/final_graph/selected_final_graph/rebuild/runs/*`

## Minimum Bundle Required For `--validate-only`

The validate-only guardrail requires the following external or local evidence files in addition to tracked Git files:

| Path | Storage class | Required role | SHA256 |
|---|---|---|---|
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl` | external | Stage11 graph output hash/input validation | `73bc624bf9147b0bba4962ab286648bcfeeb931a94a1d1a727839f160b35ada5` |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/graph_output.jsonl` | external | Stage12 graph output hash/input validation | `89ec9bf9c8932962fd3d966073b51f76345666eda5ed5d9beb18659d02e294b0` |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` | external | selected B0 graph | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` |
| `artifacts/final_graph/selected_final_graph/rebuild/B0_reaudit.report.json` | external | validate-only required rebuilt evaluator report | `a0ef6d5d5a0359e2888a422164cc7ab3e14f582e35bbd1a1728b53365988aea5` |
| `src/Pruning graph/bidirectional_allocation_results5k.json` | git | canonical allocation | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` |

The template manifest for this minimum set is:

`artifacts/final_graph/selected_final_graph/rebuild/artifact_bundle_manifest.minimum.template.json`

The checker is:

```bash
bash scripts/reconstruction/check_required_artifacts.sh
```

After the artifact checks pass, the checker can also run the frozen-artifact validate-only audit:

```bash
bash scripts/reconstruction/check_required_artifacts.sh --run-validate-only
```

## Larger Thesis Provenance Bundle

The minimum bundle is only enough to run `--validate-only`. A larger evidence bundle is needed to support the full reconstruction documentation and thesis provenance claims. It should preserve repo-relative paths and include, at minimum:

- `archive/hetzner_version/`
- `data/processed/hop_discovery_from_json.jsonl`
- patched v3 hop-support and composition-verification artifacts under `data/processed/hop_support_v3/`
- relation-profile and Wikidata ontology artifacts under `data/raw/`
- complete Stage11/Stage12 directories under `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/`
- candidate-pool and graph-candidate experiment evidence if C2/C3 analyses need to be re-audited

This larger bundle is thesis evidence, not a claim of full reproduction.

## Recommended Bundle Layout

Use a repo-relative overlay so restoration does not require path rewriting:

```text
kg_reconstruction_artifacts_YYYYMMDD/
  artifact_manifest.json
  README.md
  repo_overlay/
    src/Pruning graph/...
    artifacts/final_graph/selected_final_graph/rebuild/B0_reaudit.report.json
  full_provenance_optional/
    archive/hetzner_version/...
    data/processed/...
    data/raw/...
    artifacts/frozen_candidate_pools/...
```

The future restore script should copy from `repo_overlay/` into the repository root, refuse overwrites unless explicitly forced, verify every SHA256 hash, and then run:

```bash
bash scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh --validate-only
```

## What This Does Not Claim

This storage policy does not claim full end-to-end reproducibility. The reconstruction remains bounded by known gaps:

- the exact dashboard export session for the canonical 5k allocation was not preserved
- exact LLM production provenance and raw responses are incomplete
- WDQS-dependent candidate collection is not exactly rerunnable from frozen endpoint state
- full Phase I-to-final graph rerun reproducibility is not established

The policy supports controlled restoration and validation of frozen evidence artifacts, not regeneration of the thesis pipeline.
