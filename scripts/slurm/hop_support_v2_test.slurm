#!/bin/bash
#SBATCH --job-name=hop_supp_test
#SBATCH --output=logs/hop_support_v2_test_%j.out
#SBATCH --error=logs/hop_support_v2_test_%j.err
#SBATCH --time=4:00:00
#SBATCH --partition=short
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G

# ============================================================
# Hop Support v2 - TEST RUN (first 50 r1)
# ============================================================
# Use this to test parameters before running full job
# ============================================================

set -euo pipefail

EMAIL="YOUR_EMAIL@example.com"
USER_AGENT="hop_support/2.0 (mailto:${EMAIL})"

WORK_DIR="${HOME}/wikidata-ontology"
SCRIPT="${WORK_DIR}/hop_support_v2.py"
INPUT="${WORK_DIR}/data/hop_discovery.jsonl"
OUTPUT="${WORK_DIR}/data/hop_support_v2_TEST.jsonl"
CHECKPOINT="${WORK_DIR}/data/hop_support_v2_TEST_checkpoint.json"

# Create test input (first 50 r1)
TEST_INPUT="${WORK_DIR}/data/hop_discovery_test50.jsonl"
head -50 "${INPUT}" > "${TEST_INPUT}"

echo "============================================================"
echo "TEST RUN - First 50 r1"
echo "Job started: $(date)"
echo "============================================================"

mkdir -p "${WORK_DIR}/logs"

# Aggressive parameters for testing
python "${SCRIPT}" \
    --input "${TEST_INPUT}" \
    --output_jsonl "${OUTPUT}" \
    --checkpoint "${CHECKPOINT}" \
    --user_agent "${USER_AGENT}" \
    --chunk_size 40 \
    --qps 1.0 \
    --workers 4 \
    --max_inflight 4 \
    --timeout_sec 90 \
    --max_retries 3 \
    --topk 50 \
    --log_level DEBUG

echo ""
echo "============================================================"
echo "TEST COMPLETE: $(date)"
echo "Output: ${OUTPUT}"
echo "Lines: $(wc -l < "${OUTPUT}")"
echo ""
echo "Check for errors/429s in the output above."
echo "If clean, use hop_support_v2.slurm for full run."
echo "============================================================"
