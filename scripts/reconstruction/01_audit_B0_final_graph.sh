#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_common.sh"

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
  shift
fi
[[ "$#" -eq 0 ]] || die "usage: $0 [--force]"

cd "${REPO_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
SELECTED_GRAPH="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv"
ALLOCATION="src/Pruning graph/bidirectional_allocation_results5k.json"
EVALUATOR="tools/graph_candidate_evaluation/evaluate_graph_candidate.py"
REBUILD_DIR="artifacts/final_graph/selected_final_graph/rebuild"
REPORT="${REBUILD_DIR}/B0_reaudit.report.json"
SUMMARY="${REBUILD_DIR}/B0_reaudit.summary.md"

EXPECTED_GRAPH_SHA="c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9"
EXPECTED_ALLOCATION_SHA="a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb"

require_file "${SELECTED_GRAPH}"
require_file "${ALLOCATION}"
require_file "${EVALUATOR}"

if [[ "${FORCE}" -ne 1 ]]; then
  [[ ! -e "${REPORT}" ]] || die "refusing to overwrite ${REPORT}; rerun with --force"
  [[ ! -e "${SUMMARY}" ]] || die "refusing to overwrite ${SUMMARY}; rerun with --force"
fi

GRAPH_SHA="$(sha256_file "${SELECTED_GRAPH}")"
ALLOCATION_SHA="$(sha256_file "${ALLOCATION}")"

[[ "${GRAPH_SHA}" == "${EXPECTED_GRAPH_SHA}" ]] || die "selected graph SHA mismatch: ${GRAPH_SHA}"
[[ "${ALLOCATION_SHA}" == "${EXPECTED_ALLOCATION_SHA}" ]] || die "allocation SHA mismatch: ${ALLOCATION_SHA}"

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

