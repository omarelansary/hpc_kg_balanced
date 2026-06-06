#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_DIR="experiments/graph_candidates/C6_observed_canonical_densification/runs/${RUN_ID}"
export C6_RUN_MODE="${C6_RUN_MODE:-smoke_bounded}"
MAX_DELETIONS="${MAX_DELETIONS:-250}"

python scripts/graph_candidates/c6_candidate_census.py \
  --run-dir "${RUN_DIR}"

python scripts/graph_candidates/c6_controlled_addition.py \
  --run-dir "${RUN_DIR}"

python scripts/graph_candidates/c6_redundancy_audit.py \
  --run-dir "${RUN_DIR}"

python scripts/graph_candidates/c6_add_then_safe_delete.py \
  --run-dir "${RUN_DIR}" \
  --max-deletions "${MAX_DELETIONS}"

echo "C6 run directory: ${RUN_DIR}"
echo "C6 run mode: ${C6_RUN_MODE}"
echo "C6 max deletions: ${MAX_DELETIONS}"
