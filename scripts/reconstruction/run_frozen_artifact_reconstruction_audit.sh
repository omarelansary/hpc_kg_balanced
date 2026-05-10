#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_common.sh"

FORCE=0
DRY_RUN=0
VALIDATE_ONLY=0

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
    --validate-only)
      VALIDATE_ONLY=1
      shift
      ;;
    -h|--help)
      cat <<'USAGE'
usage: scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh [--force] [--dry-run] [--validate-only]

Wrapper-only reconstruction audit over frozen historical artifacts.

Options:
  --force          Pass --force to child reconstruction wrappers so rebuild outputs may be overwritten.
  --dry-run        Print planned behavior only; do not run wrappers and do not write the run manifest.
  --validate-only  Do not run child wrappers; validate existing rebuild outputs and write a runtime manifest.
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

if [[ "${FORCE}" -eq 1 && "${VALIDATE_ONLY}" -eq 1 ]]; then
  die "--force and --validate-only are mutually exclusive"
fi

cd "${REPO_ROOT}"

REBUILD_DIR="${RECON_REBUILD_DIR}"
if [[ -n "${RECON_AUDIT_RUN_ID:-}" ]]; then
  RUN_ID="${RECON_AUDIT_RUN_ID}"
else
  RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
fi
MANIFEST_OUT="${RECON_AUDIT_MANIFEST_OUT:-${REBUILD_DIR}/runs/${RUN_ID}_frozen_artifact_reconstruction_audit_manifest.json}"
CAPTURE_GIT_STATUS="${RECON_CAPTURE_GIT_STATUS:-0}"

if [[ "${CAPTURE_GIT_STATUS}" != "0" && "${CAPTURE_GIT_STATUS}" != "1" ]]; then
  die "RECON_CAPTURE_GIT_STATUS must be 0 or 1"
fi

EXPECTED_B0_SHA="${RECON_EXPECTED_B0_SHA}"
EXPECTED_ALLOCATION_SHA="${RECON_EXPECTED_ALLOCATION_SHA}"

B0_GRAPH="${RECON_B0_GRAPH}"
ALLOCATION="${RECON_ALLOCATION}"
STAGE11_GRAPH="${RECON_STAGE11_DIR}/graph_output.jsonl"
STAGE12_GRAPH="${RECON_STAGE12_DIR}/graph_output.jsonl"

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
  "${REBUILD_DIR}/B0_reaudit.report.json"
  "${REBUILD_DIR}/final_graph_manifest.rebuilt.json"
  "${REBUILD_DIR}/final_graph_metrics.rebuilt.json"
  "${REBUILD_DIR}/path_translation_manifest.json"
  "${REBUILD_DIR}/stage7_to_B0_chain_verification.json"
  "${REBUILD_DIR}/stage6_to_B0_chain_verification.json"
  "${REBUILD_DIR}/stage5_to_B0_chain_verification.json"
  "${REBUILD_DIR}/stage3_to_B0_chain_verification.json"
)

EXPECTED_MARKDOWN_OUTPUTS=(
  "${REBUILD_DIR}/B0_reaudit.summary.md"
)

EXPECTED_TSV_OUTPUTS=(
  "${REBUILD_DIR}/final_graph_hashes.rebuilt.tsv"
)

require_files "${CHILD_SCRIPTS[@]}" "${B0_GRAPH}" "${ALLOCATION}" "${STAGE11_GRAPH}" "${STAGE12_GRAPH}"

if [[ "${DRY_RUN}" -eq 1 ]]; then
  printf 'Repository root: %s\n' "${REPO_ROOT}"
  printf 'Run ID: %s\n' "${RUN_ID}"
  printf 'Dry run: no wrappers will be executed and no manifest will be written.\n'
  if [[ "${VALIDATE_ONLY}" -eq 1 ]]; then
    printf 'Mode: validate-only\n'
    printf 'Child wrappers: skipped/not_executed\n'
    printf 'Required existing JSON outputs:\n'
    printf '  %s\n' "${EXPECTED_JSON_OUTPUTS[@]}"
    printf 'Required existing Markdown outputs:\n'
    printf '  %s\n' "${EXPECTED_MARKDOWN_OUTPUTS[@]}"
    printf 'Required existing TSV outputs:\n'
    printf '  %s\n' "${EXPECTED_TSV_OUTPUTS[@]}"
  else
    for script in "${CHILD_SCRIPTS[@]}"; do
      if [[ "${FORCE}" -eq 1 ]]; then
        printf 'bash %q --force\n' "${script}"
      else
        printf 'bash %q\n' "${script}"
      fi
    done
  fi
  printf 'Runtime manifest on real run: %s\n' "${MANIFEST_OUT}"
  exit 0
fi

safe_mkdir "${REBUILD_DIR}"
safe_mkdir "$(dirname "${MANIFEST_OUT}")"

pre_b0_sha="$(assert_sha256 "${B0_GRAPH}" "${EXPECTED_B0_SHA}" "B0")"
pre_allocation_sha="$(assert_sha256 "${ALLOCATION}" "${EXPECTED_ALLOCATION_SHA}" "allocation")"
pre_stage11_sha="$(sha256_file "${STAGE11_GRAPH}")"
pre_stage12_sha="$(sha256_file "${STAGE12_GRAPH}")"

RUN_STATUS_FILE="$(mktemp)"
VALIDATION_STATUS_FILE="$(mktemp)"
trap 'rm -f "${RUN_STATUS_FILE}" "${VALIDATION_STATUS_FILE}"' EXIT

overall_status="passed"
if [[ "${VALIDATE_ONLY}" -ne 1 ]]; then
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
fi

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
    validate_json_file "${path}"
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
    validate_tsv_width "${path}" 3
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

  if [[ "${VALIDATE_ONLY}" -eq 1 ]]; then
    for path in "${EXPECTED_MARKDOWN_OUTPUTS[@]}"; do
      if [[ -f "${path}" ]]; then
        printf 'markdown\t%s\tpresent\n' "${path}" >> "${VALIDATION_STATUS_FILE}"
      else
        printf 'markdown\t%s\tmissing\n' "${path}" >> "${VALIDATION_STATUS_FILE}"
        validation_status="failed"
        overall_status="failed"
      fi
    done
  fi
fi

post_b0_sha="$(sha256_file "${B0_GRAPH}")"
post_allocation_sha="$(sha256_file "${ALLOCATION}")"
post_stage11_sha="$(sha256_file "${STAGE11_GRAPH}")"
post_stage12_sha="$(sha256_file "${STAGE12_GRAPH}")"

[[ "${post_b0_sha}" == "${EXPECTED_B0_SHA}" ]] || overall_status="failed"
[[ "${post_allocation_sha}" == "${EXPECTED_ALLOCATION_SHA}" ]] || overall_status="failed"
if [[ "${VALIDATE_ONLY}" -eq 1 ]]; then
  [[ "${pre_b0_sha}" == "${post_b0_sha}" ]] || overall_status="failed"
  [[ "${pre_allocation_sha}" == "${post_allocation_sha}" ]] || overall_status="failed"
  [[ "${pre_stage11_sha}" == "${post_stage11_sha}" ]] || overall_status="failed"
  [[ "${pre_stage12_sha}" == "${post_stage12_sha}" ]] || overall_status="failed"
fi

"${PYTHON_BIN}" - \
  "${MANIFEST_OUT}" \
  "${RUN_STATUS_FILE}" \
  "${VALIDATION_STATUS_FILE}" \
  "${overall_status}" \
  "${validation_status}" \
  "${FORCE}" \
  "${VALIDATE_ONLY}" \
  "${RUN_ID}" \
  "${CAPTURE_GIT_STATUS}" \
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
    validate_only,
    run_id,
    capture_git_status,
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
if validate_only == "1":
    for script in scripts:
        run_rows.append({
            "script": script,
            "command": "not_executed",
            "exit_code": None,
            "status": "skipped",
            "reason": "validate_only",
        })
else:
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
rebuild_dir = str(Path(manifest_out).parent)
stage11_dir = str(Path(stage11_graph).parent)
runtime_git_status = "not_captured"
if capture_git_status == "1":
    git_status_summary = run_text([
        "git",
        "status",
        "--short",
        "--",
        "scripts/reconstruction",
        "docs/reconstruction",
        rebuild_dir,
        stage11_dir,
        allocation,
    ])
    runtime_git_status = git_status_summary.splitlines() if git_status_summary else []

manifest = {
    "schema_version": "reconstruction-audit-runtime-manifest-v3",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "created_by": "scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh",
    "entrypoint": "scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh",
    "run_id": run_id,
    "manifest_out": manifest_out,
    "mode": "validate-only" if validate_only == "1" else "force" if force == "1" else "default",
    "git_commit": git_commit,
    "runtime_git_status": runtime_git_status,
    "scripts_run": run_rows,
    "expected_output_files": outputs,
    "output_files_present_after_run": output_files,
    "inputs": {
        "b0_graph": b0_graph,
        "allocation": allocation,
        "stage11_graph_output": stage11_graph,
        "stage12_graph_output": stage12_graph,
    },
    "outputs": {
        "expected": outputs,
        "present_after_run": output_files,
    },
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
    ] + (
        ["No child wrappers were executed in validate-only mode."]
        if validate_only == "1"
        else []
    ),
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
