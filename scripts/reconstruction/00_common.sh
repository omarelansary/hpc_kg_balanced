#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${COMMON_DIR}/../.." && pwd)"

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

safe_mkdir() {
  local path="$1"
  mkdir -p "${path}"
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

relpath_from_root() {
  local path="$1"
  python - "$REPO_ROOT" "$path" <<'PY'
import os
import sys
root, path = sys.argv[1], sys.argv[2]
print(os.path.relpath(os.path.abspath(path), os.path.abspath(root)))
PY
}

