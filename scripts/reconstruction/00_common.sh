#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${COMMON_DIR}/../.." && pwd)"

PYTHON_BIN="${PYTHON_BIN:-python}"
RECON_REBUILD_DIR="${RECON_REBUILD_DIR:-artifacts/final_graph/selected_final_graph/rebuild}"
RECON_STAGE11_DIR="${RECON_STAGE11_DIR:-src/Pruning graph/stage11_eta_aware_connectivity_repair_full}"
RECON_STAGE12_DIR="${RECON_STAGE12_DIR:-${RECON_STAGE11_DIR}/stage12_path_repair_prod}"
RECON_B0_GRAPH="${RECON_B0_GRAPH:-${RECON_STAGE12_DIR}/largest_component.csv}"
RECON_ALLOCATION="${RECON_ALLOCATION:-src/Pruning graph/bidirectional_allocation_results5k.json}"
RECON_HETZNER_RUN_DIR="${RECON_HETZNER_RUN_DIR:-archive/hetzner_version/runs/prod_refine_20260315_180520}"
RECON_EXPECTED_B0_SHA="${RECON_EXPECTED_B0_SHA:-c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9}"
RECON_EXPECTED_ALLOCATION_SHA="${RECON_EXPECTED_ALLOCATION_SHA:-a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb}"

readonly PYTHON_BIN
readonly RECON_REBUILD_DIR
readonly RECON_STAGE11_DIR
readonly RECON_STAGE12_DIR
readonly RECON_B0_GRAPH
readonly RECON_ALLOCATION
readonly RECON_HETZNER_RUN_DIR
readonly RECON_EXPECTED_B0_SHA
readonly RECON_EXPECTED_ALLOCATION_SHA

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

repo_root() {
  printf '%s\n' "${REPO_ROOT}"
}

timestamp_utc() {
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

require_file() {
  local path="$1"
  [[ -f "${path}" ]] || die "required file not found: ${path}"
}

require_files() {
  local path
  for path in "$@"; do
    require_file "${path}"
  done
}

require_dir() {
  local path="$1"
  [[ -d "${path}" ]] || die "required directory not found: ${path}"
}

safe_mkdir() {
  local path="$1"
  mkdir -p "${path}"
}

parse_force_only_args() {
  FORCE=0
  if [[ "$#" -gt 1 ]]; then
    die "usage: $0 [--force]"
  fi
  if [[ "$#" -eq 1 ]]; then
    [[ "$1" == "--force" ]] || die "usage: $0 [--force]"
    FORCE=1
  fi
}

refuse_overwrite_unless_force() {
  local force="$1"
  shift
  local path
  if [[ "${force}" -ne 1 ]]; then
    for path in "$@"; do
      [[ ! -e "${path}" ]] || die "refusing to overwrite ${path}; rerun with --force"
    done
  fi
}

sha256_file() {
  local path="$1"
  require_file "${path}"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${path}" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${path}" | awk '{print $1}'
  else
    die "no sha256sum or shasum command found"
  fi
}

assert_sha256() {
  local path="$1"
  local expected_hash="$2"
  local label="$3"
  local actual_hash
  actual_hash="$(sha256_file "${path}")"
  [[ "${actual_hash}" == "${expected_hash}" ]] || die "${label} SHA mismatch: ${actual_hash}"
  printf '%s\n' "${actual_hash}"
}

validate_json_file() {
  local path="$1"
  require_file "${path}"
  "${PYTHON_BIN}" -m json.tool "${path}" >/dev/null
}

validate_tsv_width() {
  local path="$1"
  local expected_columns="$2"
  require_file "${path}"
  "${PYTHON_BIN}" - "${path}" "${expected_columns}" <<'PY'
import csv
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_columns = int(sys.argv[2])
with path.open(encoding="utf-8", newline="") as handle:
    rows = list(csv.reader(handle, delimiter="\t"))
if not rows:
    raise SystemExit("empty TSV")
bad = [idx + 1 for idx, row in enumerate(rows) if len(row) != expected_columns]
if bad:
    raise SystemExit(f"bad TSV row widths at rows {bad[:10]}")
PY
}

print_section() {
  printf '\n== %s ==\n' "$*"
}

relpath_from_root() {
  local path="$1"
  "${PYTHON_BIN}" - "$REPO_ROOT" "$path" <<'PY'
import os
import sys
root, path = sys.argv[1], sys.argv[2]
print(os.path.relpath(os.path.abspath(path), os.path.abspath(root)))
PY
}
