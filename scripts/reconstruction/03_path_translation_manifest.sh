#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_common.sh"

parse_force_only_args "$@"

cd "${REPO_ROOT}"

REBUILD_DIR="${RECON_REBUILD_DIR}"
OUT="${REBUILD_DIR}/path_translation_manifest.json"

STAGE11_MANIFEST="${RECON_STAGE11_DIR}/manifest.json"
STAGE12_MANIFEST="${RECON_STAGE12_DIR}/manifest.json"
LOCAL_ALLOCATION="${RECON_ALLOCATION}"

STALE_PRE_STAGE11_GRAPH="/home/kg_benchmark/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl"
STALE_ALLOCATION="/home/kg_benchmark/src/kg_builder/input/bidirectional_allocation_results5k.json"

require_files "${STAGE11_MANIFEST}" "${STAGE12_MANIFEST}" "${LOCAL_ALLOCATION}"

refuse_overwrite_unless_force "${FORCE}" "${OUT}"

safe_mkdir "${REBUILD_DIR}"

"${PYTHON_BIN}" - \
  "${OUT}" \
  "${STAGE11_MANIFEST}" \
  "${STAGE12_MANIFEST}" \
  "${LOCAL_ALLOCATION}" \
  "${STALE_PRE_STAGE11_GRAPH}" \
  "${STALE_ALLOCATION}" <<'PY'
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    out_path,
    stage11_manifest,
    stage12_manifest,
    local_allocation,
    stale_pre_stage11_graph,
    stale_allocation,
) = [Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5], sys.argv[6]]

repo_root = Path.cwd()

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def rel(path: Path) -> str:
    return os.path.relpath(path.resolve(), repo_root.resolve())

def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)

def exact_filename_matches(filename: str) -> list[Path]:
    skipped_dirs = {".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "venv", "node_modules"}
    matches: list[Path] = []
    for root, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in skipped_dirs]
        if filename in filenames:
            matches.append(Path(root) / filename)
    return sorted(matches, key=lambda p: rel(p))

stage11_data = load_json(stage11_manifest)
stage12_data = load_json(stage12_manifest)

pre_stage11_filename = Path(stale_pre_stage11_graph).name
pre_stage11_matches = exact_filename_matches(pre_stage11_filename)
if len(pre_stage11_matches) == 1:
    pre_stage11_status = "resolved_by_exact_filename_search"
    pre_stage11_local = rel(pre_stage11_matches[0])
    pre_stage11_sha = sha256(pre_stage11_matches[0])
elif len(pre_stage11_matches) == 0:
    pre_stage11_status = "unresolved_no_exact_filename_match"
    pre_stage11_local = None
    pre_stage11_sha = None
else:
    pre_stage11_status = "unresolved_ambiguous_exact_filename_matches"
    pre_stage11_local = None
    pre_stage11_sha = None

manifest = {
    "created_on": datetime.now(timezone.utc).isoformat(),
    "created_by": "scripts/reconstruction/03_path_translation_manifest.sh",
    "purpose": "Document stale absolute paths in Stage11/Stage12 manifests and map only resolved local equivalents.",
    "stage_manifests": [
        {
            "role": "stage11_connectivity_repair_manifest",
            "path": rel(stage11_manifest),
            "sha256": sha256(stage11_manifest),
            "created_at": stage11_data.get("created_at"),
            "output_dir_recorded_in_manifest": stage11_data.get("output_dir"),
            "inputs": stage11_data.get("inputs"),
            "cli_args": stage11_data.get("cli_args"),
        },
        {
            "role": "stage12_path_repair_manifest",
            "path": rel(stage12_manifest),
            "sha256": sha256(stage12_manifest),
            "created_at": stage12_data.get("created_at"),
            "output_dir_recorded_in_manifest": stage12_data.get("output_dir"),
            "inputs": stage12_data.get("inputs"),
            "cli_args": stage12_data.get("cli_args"),
        },
    ],
    "translations": [
        {
            "role": "pre_stage11_input_graph",
            "stale_path": stale_pre_stage11_graph,
            "local_equivalent": pre_stage11_local,
            "local_sha256": pre_stage11_sha,
            "resolution_status": pre_stage11_status,
            "search_policy": "Exact basename search from repository root; historical manifests were not modified.",
            "candidate_matches": [
                {"path": rel(match), "sha256": sha256(match)}
                for match in pre_stage11_matches[:20]
            ],
            "candidate_match_count": len(pre_stage11_matches),
            "notes": [
                "This path is recorded as a stale absolute path from the historical Stage11/Stage12 run context.",
                "If unresolved or ambiguous, the pre-Stage11 graph input remains a reproducibility gap.",
            ],
        },
        {
            "role": "relation_scope_manifest_or_allocation",
            "stale_path": stale_allocation,
            "local_equivalent": rel(local_allocation),
            "local_sha256": sha256(local_allocation),
            "resolution_status": "resolved_manual_path_mapping",
            "search_policy": "Mapped to the canonical B0 allocation selected in final graph registration.",
            "candidate_matches": [
                {"path": rel(local_allocation), "sha256": sha256(local_allocation)}
            ],
            "candidate_match_count": 1,
            "notes": [
                "The local allocation path is the canonical allocation recorded for the selected B0 graph.",
                "This mapping is documentation-only and does not rewrite historical manifests.",
            ],
        },
    ],
    "explicit_notes": [
        "No Stage11 or Stage12 manifest was modified.",
        "No graph artifact was copied or generated.",
        "No WDQS or LLM call is made by this wrapper.",
        "Only stale absolute path translation evidence for the final B0 chain is recorded here.",
    ],
}

out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"path_translation_manifest={out_path}")
print(f"pre_stage11_resolution_status={pre_stage11_status}")
print(f"allocation_resolution_status=resolved_manual_path_mapping")
PY
