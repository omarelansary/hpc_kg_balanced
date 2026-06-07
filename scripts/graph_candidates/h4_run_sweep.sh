#!/usr/bin/env bash
set -euo pipefail

RUN_STAMP="${RUN_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_ROOT="${RUN_ROOT:-experiments/graph_candidates/H4_labelled_rule_completion/runs}"

H4_A1_RUN_DIR="${RUN_ROOT}/h4_A1_deficit_capped_${RUN_STAMP}"
H4_A2_RUN_DIR="${RUN_ROOT}/h4_A2_add_all_${RUN_STAMP}"
H4_A3_RUN_DIR="${RUN_ROOT}/h4_A3_add_all_safe_delete_${RUN_STAMP}"

python scripts/graph_candidates/h4_generate_symmetric_completion.py \
  --run-dir "${H4_A1_RUN_DIR}" \
  --mode deficit-capped

python scripts/graph_candidates/h4_generate_symmetric_completion.py \
  --run-dir "${H4_A2_RUN_DIR}" \
  --mode add-all

python scripts/graph_candidates/h4_generate_symmetric_completion.py \
  --run-dir "${H4_A3_RUN_DIR}" \
  --mode add-all

python scripts/graph_candidates/h4_post_completion_safe_delete.py \
  --run-dir "${H4_A3_RUN_DIR}" \
  --max-deletions "${MAX_DELETIONS:-100000}"

echo "H4-A1 run directory: ${H4_A1_RUN_DIR}"
echo "H4-A2 run directory: ${H4_A2_RUN_DIR}"
echo "H4-A3 run directory: ${H4_A3_RUN_DIR}"
