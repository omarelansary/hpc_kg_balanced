#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_common.sh"

parse_force_only_args "$@"

cd "${REPO_ROOT}"

SELECTED_GRAPH="${RECON_B0_GRAPH}"
ALLOCATION="${RECON_ALLOCATION}"
EVALUATOR="tools/graph_candidate_evaluation/evaluate_graph_candidate.py"
REBUILD_DIR="${RECON_REBUILD_DIR}"
REPORT="${REBUILD_DIR}/B0_reaudit.report.json"
SUMMARY="${REBUILD_DIR}/B0_reaudit.summary.md"

EXPECTED_GRAPH_SHA="${RECON_EXPECTED_B0_SHA}"
EXPECTED_ALLOCATION_SHA="${RECON_EXPECTED_ALLOCATION_SHA}"

require_files "${SELECTED_GRAPH}" "${ALLOCATION}" "${EVALUATOR}"

refuse_overwrite_unless_force "${FORCE}" "${REPORT}" "${SUMMARY}"

GRAPH_SHA="$(assert_sha256 "${SELECTED_GRAPH}" "${EXPECTED_GRAPH_SHA}" "selected graph")"
ALLOCATION_SHA="$(assert_sha256 "${ALLOCATION}" "${EXPECTED_ALLOCATION_SHA}" "allocation")"

safe_mkdir "${REBUILD_DIR}"

"${PYTHON_BIN}" "${EVALUATOR}" \
  --graph "${SELECTED_GRAPH}" \
  --allocation "${ALLOCATION}" \
  --output-report "${REPORT}" \
  --output-summary "${SUMMARY}" \
  --candidate-id "B0" \
  --label "Stage12 repaired largest component; final-selected B0 reaudit"

"${PYTHON_BIN}" - "${REPORT}" "${EXPECTED_GRAPH_SHA}" "${EXPECTED_ALLOCATION_SHA}" <<'PY'
import json
import sys

report_path, expected_graph_sha, expected_allocation_sha = sys.argv[1:4]
report = json.load(open(report_path, encoding="utf-8"))
graph_sha = report.get("graph_sha256")
allocation_sha = report.get("allocation_sha256")
if graph_sha != expected_graph_sha:
    raise SystemExit(f"reaudit graph SHA mismatch in report: {graph_sha}")
if allocation_sha != expected_allocation_sha:
    raise SystemExit(f"reaudit allocation SHA mismatch in report: {allocation_sha}")
print(f"B0 reaudit complete: {report_path}")
print(f"graph_sha256={graph_sha}")
print(f"allocation_sha256={allocation_sha}")
PY
