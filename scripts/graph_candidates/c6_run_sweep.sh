#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_DIR="experiments/graph_candidates/C6_observed_canonical_densification/runs/${RUN_ID}"

python scripts/graph_candidates/c6_candidate_census.py \
  --run-dir "${RUN_DIR}"

python scripts/graph_candidates/c6_controlled_addition.py \
  --run-dir "${RUN_DIR}"

python scripts/graph_candidates/c6_redundancy_audit.py \
  --run-dir "${RUN_DIR}"

python scripts/graph_candidates/c6_add_then_safe_delete.py \
  --run-dir "${RUN_DIR}" \
  --max-deletions "${MAX_DELETIONS:-250}"

echo "C6 run directory: ${RUN_DIR}"
