#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_common.sh"

MANIFEST_PATH="${RECON_REBUILD_DIR}/artifact_bundle_manifest.minimum.template.json"
RUN_VALIDATE_ONLY=0

usage() {
  cat <<'USAGE'
usage: scripts/reconstruction/check_required_artifacts.sh [--manifest PATH] [--run-validate-only]

Read-only checker for the frozen reconstruction artifact bundle contract.

Options:
  --manifest PATH       Artifact bundle manifest to check.
  --run-validate-only   Run the frozen-artifact validate-only audit after artifact checks pass.
USAGE
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --manifest)
      [[ "$#" -ge 2 ]] || die "--manifest requires a path"
      MANIFEST_PATH="$2"
      shift 2
      ;;
    --run-validate-only)
      RUN_VALIDATE_ONLY=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
done

cd "${REPO_ROOT}"
require_file "${MANIFEST_PATH}"
validate_json_file "${MANIFEST_PATH}"

print_section "Checking artifact bundle manifest"
printf 'Manifest: %s\n' "${MANIFEST_PATH}"

"${PYTHON_BIN}" - "${MANIFEST_PATH}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
artifacts = manifest.get("artifacts")
if not isinstance(artifacts, list):
    raise SystemExit("manifest artifacts field must be a list")

required_fields = {
    "path",
    "sha256",
    "size_bytes",
    "storage_class",
    "required_for_validate_only",
    "required_for_force_rebuild",
    "required_for_thesis_provenance",
    "role",
    "notes",
}

allowed_storage_classes = {
    "git",
    "external",
    "git_lfs",
    "runtime_generated",
    "external_optional",
}

missing = []
mismatched = []
schema_errors = []
passed = []

for index, row in enumerate(artifacts, start=1):
    if not isinstance(row, dict):
        schema_errors.append(f"artifact row {index} is not an object")
        continue
    absent_fields = sorted(required_fields - row.keys())
    if absent_fields:
        schema_errors.append(f"{row.get('path', f'row {index}')}: missing fields {absent_fields}")
        continue
    if row["storage_class"] not in allowed_storage_classes:
        schema_errors.append(f"{row['path']}: invalid storage_class {row['storage_class']!r}")
        continue
    path = Path(row["path"])
    if not path.is_file():
        missing.append(row["path"])
        print(f"MISSING\t{row['storage_class']}\t{row['path']}")
        continue
    size = path.stat().st_size
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    actual_hash = h.hexdigest()
    expected_hash = row["sha256"]
    expected_size = int(row["size_bytes"])
    if actual_hash != expected_hash or size != expected_size:
        mismatched.append(
            {
                "path": row["path"],
                "expected_sha256": expected_hash,
                "actual_sha256": actual_hash,
                "expected_size_bytes": expected_size,
                "actual_size_bytes": size,
            }
        )
        print(f"MISMATCH\t{row['storage_class']}\t{row['path']}\t{actual_hash}\t{size}")
    else:
        passed.append(row["path"])
        print(f"PASSED\t{row['storage_class']}\t{row['path']}\t{actual_hash}\t{size}")

print()
print(f"artifact_rows={len(artifacts)}")
print(f"passed={len(passed)}")
print(f"missing={len(missing)}")
print(f"mismatched={len(mismatched)}")
print(f"schema_errors={len(schema_errors)}")

if schema_errors:
    print()
    print("Schema errors:")
    for error in schema_errors:
        print(f"- {error}")
if mismatched:
    print()
    print("Hash or size mismatches:")
    for row in mismatched:
        print(
            "- {path}: expected {expected_sha256}/{expected_size_bytes}, "
            "actual {actual_sha256}/{actual_size_bytes}".format(**row)
        )
if missing:
    print()
    print("Missing artifacts:")
    for path in missing:
        print(f"- {path}")

if schema_errors or missing or mismatched:
    raise SystemExit(1)
PY

if [[ "${RUN_VALIDATE_ONLY}" -eq 1 ]]; then
  print_section "Running frozen-artifact validate-only audit"
  bash scripts/reconstruction/run_frozen_artifact_reconstruction_audit.sh --validate-only
fi
