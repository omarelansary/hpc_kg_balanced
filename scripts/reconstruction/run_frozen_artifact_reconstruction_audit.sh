#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_common.sh"

FORCE=0
DRY_RUN=0

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --force)
      FORCE=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
usage: scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh [--force] [--dry-run]

Wrapper-only reconstruction audit over frozen historical artifacts.

Options:
  --force    Pass --force to child reconstruction wrappers so rebuild outputs may be overwritten.
  --dry-run  Print child commands only; do not run wrappers and do not write the run manifest.
USAGE
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

if [[ "${FORCE}" -eq 1 && "${DRY_RUN}" -eq 1 ]]; then
  die "--force and --dry-run are mutually exclusive"
fi

cd "${REPO_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
REBUILD_DIR="artifacts/final_graph/selected_final_graph/rebuild"
MANIFEST_OUT="${REBUILD_DIR}/frozen_artifact_reconstruction_audit_manifest.json"

EXPECTED_B0_SHA="c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9"
EXPECTED_ALLOCATION_SHA="a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb"

B0_GRAPH="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv"
ALLOCATION="src/Pruning graph/bidirectional_allocation_results5k.json"
STAGE11_GRAPH="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl"
STAGE12_GRAPH="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/graph_output.jsonl"

CHILD_SCRIPTS=(
  "scripts/reconstruction/01_audit_B0_final_graph.sh"
  "scripts/reconstruction/02_register_B0_final_manifest.sh"
  "scripts/reconstruction/03_path_translation_manifest.sh"
  "scripts/reconstruction/04_verify_stage7_to_B0_chain.sh"
  "scripts/reconstruction/05_verify_stage6_to_B0_chain.sh"
  "scripts/reconstruction/06_verify_stage5_to_B0_chain.sh"
  "scripts/reconstruction/07_verify_stage3_to_B0_chain.sh"
)

EXPECTED_JSON_OUTPUTS=(
  "artifacts/final_graph/selected_final_graph/rebuild/B0_reaudit.report.json"
  "artifacts/final_graph/selected_final_graph/rebuild/final_graph_manifest.rebuilt.json"
  "artifacts/final_graph/selected_final_graph/rebuild/final_graph_metrics.rebuilt.json"
  "artifacts/final_graph/selected_final_graph/rebuild/path_translation_manifest.json"
  "artifacts/final_graph/selected_final_graph/rebuild/stage7_to_B0_chain_verification.json"
  "artifacts/final_graph/selected_final_graph/rebuild/stage6_to_B0_chain_verification.json"
  "artifacts/final_graph/selected_final_graph/rebuild/stage5_to_B0_chain_verification.json"
  "artifacts/final_graph/selected_final_graph/rebuild/stage3_to_B0_chain_verification.json"
)

EXPECTED_MARKDOWN_OUTPUTS=(
  "artifacts/final_graph/selected_final_graph/rebuild/B0_reaudit.summary.md"
)

EXPECTED_TSV_OUTPUTS=(
  "artifacts/final_graph/selected_final_graph/rebuild/final_graph_hashes.rebuilt.tsv"
)

for path in "${CHILD_SCRIPTS[@]}" "${B0_GRAPH}" "${ALLOCATION}" "${STAGE11_GRAPH}" "${STAGE12_GRAPH}"; do
  require_file "${path}"
done

if [[ "${DRY_RUN}" -eq 1 ]]; then
  printf 'Repository root: %s\n' "${REPO_ROOT}"
  printf 'Dry run: no wrappers will be executed and no manifest will be written.\n'
  for script in "${CHILD_SCRIPTS[@]}"; do
    if [[ "${FORCE}" -eq 1 ]]; then
      printf 'bash %q --force\n' "${script}"
    else
      printf 'bash %q\n' "${script}"
    fi
  done
  printf 'Manifest on real run: %s\n' "${MANIFEST_OUT}"
  exit 0
fi

safe_mkdir "${REBUILD_DIR}"

pre_b0_sha="$(sha256_file "${B0_GRAPH}")"
pre_allocation_sha="$(sha256_file "${ALLOCATION}")"
pre_stage11_sha="$(sha256_file "${STAGE11_GRAPH}")"
pre_stage12_sha="$(sha256_file "${STAGE12_GRAPH}")"

[[ "${pre_b0_sha}" == "${EXPECTED_B0_SHA}" ]] || die "B0 SHA mismatch before audit: ${pre_b0_sha}"
[[ "${pre_allocation_sha}" == "${EXPECTED_ALLOCATION_SHA}" ]] || die "allocation SHA mismatch before audit: ${pre_allocation_sha}"

RUN_STATUS_FILE="$(mktemp)"
VALIDATION_STATUS_FILE="$(mktemp)"
trap 'rm -f "${RUN_STATUS_FILE}" "${VALIDATION_STATUS_FILE}"' EXIT

overall_status="passed"
for script in "${CHILD_SCRIPTS[@]}"; do
  if [[ "${FORCE}" -eq 1 ]]; then
    command_display="bash ${script} --force"
    set +e
    bash "${script}" --force
    status=$?
    set -e
  else
    command_display="bash ${script}"
    set +e
    bash "${script}"
    status=$?
    set -e
  fi
  printf '%s\t%s\t%s\n' "${script}" "${command_display}" "${status}" >> "${RUN_STATUS_FILE}"
  if [[ "${status}" -ne 0 ]]; then
    overall_status="failed"
    break
  fi
done

validation_status="passed"
if [[ "${overall_status}" == "passed" ]]; then
  for path in "${EXPECTED_JSON_OUTPUTS[@]}"; do
    if [[ ! -f "${path}" ]]; then
      printf 'json\t%s\tmissing\n' "${path}" >> "${VALIDATION_STATUS_FILE}"
      validation_status="failed"
      overall_status="failed"
      continue
    fi
    set +e
    "${PYTHON_BIN}" -m json.tool "${path}" >/dev/null
    status=$?
    set -e
    if [[ "${status}" -eq 0 ]]; then
      printf 'json\t%s\tvalid\n' "${path}" >> "${VALIDATION_STATUS_FILE}"
    else
      printf 'json\t%s\tinvalid\n' "${path}" >> "${VALIDATION_STATUS_FILE}"
      validation_status="failed"
      overall_status="failed"
    fi
  done

  for path in "${EXPECTED_TSV_OUTPUTS[@]}"; do
    if [[ ! -f "${path}" ]]; then
      printf 'tsv\t%s\tmissing\n' "${path}" >> "${VALIDATION_STATUS_FILE}"
      validation_status="failed"
      overall_status="failed"
      continue
    fi
    set +e
    "${PYTHON_BIN}" - "${path}" <<'PY' >/dev/null
import csv
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open(encoding="utf-8", newline="") as handle:
    rows = list(csv.reader(handle, delimiter="\t"))
if not rows:
    raise SystemExit("empty TSV")
width = len(rows[0])
bad = [idx + 1 for idx, row in enumerate(rows) if len(row) != width]
if bad:
    raise SystemExit(f"bad TSV row widths at rows {bad[:10]}")
PY
    status=$?
    set -e
    if [[ "${status}" -eq 0 ]]; then
      printf 'tsv\t%s\tvalid\n' "${path}" >> "${VALIDATION_STATUS_FILE}"
    else
      printf 'tsv\t%s\tinvalid\n' "${path}" >> "${VALIDATION_STATUS_FILE}"
      validation_status="failed"
      overall_status="failed"
    fi
  done
fi

post_b0_sha="$(sha256_file "${B0_GRAPH}")"
post_allocation_sha="$(sha256_file "${ALLOCATION}")"
post_stage11_sha="$(sha256_file "${STAGE11_GRAPH}")"
post_stage12_sha="$(sha256_file "${STAGE12_GRAPH}")"

[[ "${post_b0_sha}" == "${EXPECTED_B0_SHA}" ]] || overall_status="failed"
[[ "${post_allocation_sha}" == "${EXPECTED_ALLOCATION_SHA}" ]] || overall_status="failed"

"${PYTHON_BIN}" - \
  "${MANIFEST_OUT}" \
  "${RUN_STATUS_FILE}" \
  "${VALIDATION_STATUS_FILE}" \
  "${overall_status}" \
  "${validation_status}" \
  "${FORCE}" \
  "${pre_b0_sha}" \
  "${post_b0_sha}" \
  "${pre_allocation_sha}" \
  "${post_allocation_sha}" \
  "${pre_stage11_sha}" \
  "${post_stage11_sha}" \
  "${pre_stage12_sha}" \
  "${post_stage12_sha}" \
  "${EXPECTED_B0_SHA}" \
  "${EXPECTED_ALLOCATION_SHA}" \
  "${B0_GRAPH}" \
  "${ALLOCATION}" \
  "${STAGE11_GRAPH}" \
  "${STAGE12_GRAPH}" \
  "${CHILD_SCRIPTS[@]}" \
  -- \
  "${EXPECTED_JSON_OUTPUTS[@]}" \
  "${EXPECTED_MARKDOWN_OUTPUTS[@]}" \
  "${EXPECTED_TSV_OUTPUTS[@]}" <<'PY'
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

args = sys.argv[1:]
separator = args.index("--")
fixed = args[:separator]
outputs = args[separator + 1 :]
(
    manifest_out,
    run_status_file,
    validation_status_file,
    overall_status,
    validation_status,
    force,
    pre_b0_sha,
    post_b0_sha,
    pre_allocation_sha,
    post_allocation_sha,
    pre_stage11_sha,
    post_stage11_sha,
    pre_stage12_sha,
    post_stage12_sha,
    expected_b0_sha,
    expected_allocation_sha,
    b0_graph,
    allocation,
    stage11_graph,
    stage12_graph,
    *scripts,
) = fixed

def run_text(cmd):
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
    except Exception:
        return None

run_rows = []
for line in Path(run_status_file).read_text(encoding="utf-8").splitlines():
    script, command, status = line.split("\t")
    run_rows.append({
        "script": script,
        "command": command,
        "exit_code": int(status),
        "status": "passed" if status == "0" else "failed",
    })

validation_rows = []
if Path(validation_status_file).exists():
    for line in Path(validation_status_file).read_text(encoding="utf-8").splitlines():
        kind, path, status = line.split("\t")
        validation_rows.append({"type": kind, "path": path, "status": status})

output_files = []
for path_text in outputs:
    path = Path(path_text)
    output_files.append({
        "path": path_text,
        "present_after_run": path.exists(),
    })

git_commit = run_text(["git", "rev-parse", "HEAD"])
git_status_summary = run_text([
    "git",
    "status",
    "--short",
    "--",
    "scripts/reconstruction",
    "docs/reconstruction",
    "artifacts/final_graph/selected_final_graph/rebuild",
    "src/Pruning graph/stage11_eta_aware_connectivity_repair_full",
    "src/Pruning graph/bidirectional_allocation_results5k.json",
])

manifest = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "entrypoint": "scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh",
    "mode": "force" if force == "1" else "default",
    "git_commit": git_commit,
    "git_status_summary_relevant_paths": git_status_summary.splitlines() if git_status_summary else [],
    "scripts_run": run_rows,
    "expected_output_files": outputs,
    "output_files_present_after_run": output_files,
    "validation_status": validation_status,
    "validation_results": validation_rows,
    "key_hashes": {
        "b0_graph": {
            "path": b0_graph,
            "expected_sha256": expected_b0_sha,
            "pre_run_sha256": pre_b0_sha,
            "post_run_sha256": post_b0_sha,
            "matched_expected": post_b0_sha == expected_b0_sha,
            "changed_during_run": pre_b0_sha != post_b0_sha,
        },
        "allocation": {
            "path": allocation,
            "expected_sha256": expected_allocation_sha,
            "pre_run_sha256": pre_allocation_sha,
            "post_run_sha256": post_allocation_sha,
            "matched_expected": post_allocation_sha == expected_allocation_sha,
            "changed_during_run": pre_allocation_sha != post_allocation_sha,
        },
        "stage11_graph_output": {
            "path": stage11_graph,
            "pre_run_sha256": pre_stage11_sha,
            "post_run_sha256": post_stage11_sha,
            "changed_during_run": pre_stage11_sha != post_stage11_sha,
        },
        "stage12_graph_output": {
            "path": stage12_graph,
            "pre_run_sha256": pre_stage12_sha,
            "post_run_sha256": post_stage12_sha,
            "changed_during_run": pre_stage12_sha != post_stage12_sha,
        },
    },
    "overall_status": overall_status,
    "explicit_notes": [
        "This is wrapper-only frozen-artifact validation.",
        "No graph data is generated by this entrypoint.",
        "No WDQS or LLM calls are made by this entrypoint.",
        "This does not establish full end-to-end reproducibility from live upstream inputs.",
    ],
}

Path(manifest_out).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"manifest={manifest_out}")
print(f"overall_status={overall_status}")
print(f"validation_status={validation_status}")
PY

"${PYTHON_BIN}" -m json.tool "${MANIFEST_OUT}" >/dev/null

if [[ "${overall_status}" != "passed" ]]; then
  die "frozen artifact reconstruction audit failed; see ${MANIFEST_OUT}"
fi

printf 'Frozen artifact reconstruction audit passed.\n'
printf 'Manifest: %s\n' "${MANIFEST_OUT}"
