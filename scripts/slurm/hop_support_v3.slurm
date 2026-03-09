#!/bin/bash
#SBATCH --job-name=extended_rerun_hop_support_v3
#SBATCH --output=logs/normalized_hop_support_v3_rerun%j.out
#SBATCH --error=logs/normalized_hop_support_v3_rerun%j.err
#SBATCH --time=168:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=omar_essameldeen_ahmad.elansary@mailbox.tu-dresden.de

# ============================================================
# Hop Support v3 - SLURM Job Script
# ============================================================
# Computes loop/non-loop support counts for all (r1, r2) pairs
# with 1-hop self-loop exclusion filters:
#   FILTER(?x != ?y)
#   FILTER(?y != ?z)
# ============================================================

set -euo pipefail

# ----------------------------
# Configuration
# ----------------------------
EMAIL="omar@gmail.com"
USER_AGENT="hop_support/3.0 (mailto:${EMAIL})"

WORK_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
SCRIPT="${WORK_DIR}/src/hop_support_and_sym_anti_verification/hop_support_v3.py"
INPUT="${WORK_DIR}/data/processed/hop_support_v2_before_target_enrichment_hopdiscovery_like.jsonl"
OUTPUT="${WORK_DIR}/data/processed/output_hop_support_v3_from_hop_discovery_from_json_and_support_v2_rerun.normalized.jsonl"
CHECKPOINT="${WORK_DIR}/data/processed/hop_support_v3_from_hop_discovery_from_json_and_support_v2_rerun.normalized_checkpoint.json"
TRIPLETS_OUTPUT="${WORK_DIR}/data/processed/output_hop_support_v3_triplets_from_hop_discovery_from_json_and_support_v2_rerun.normalized.jsonl"
TRIPLETS_QUEUE_SIZE=1000

# WDQS parameters (conservative to avoid 429)
CHUNK_SIZE=10
QPS=0.03
WORKERS=4
MAX_INFLIGHT=1
TIMEOUT_SEC=180
MAX_RETRIES=3
TOPK=50

# ----------------------------
# Setup
# ----------------------------
echo "============================================================"
echo "Job started: $(date)"
echo "Job ID: ${SLURM_JOB_ID}"
echo "Node: ${SLURMD_NODENAME}"
echo "Working directory: ${WORK_DIR}"
echo "============================================================"

mkdir -p "${WORK_DIR}/logs"

echo "Python: $(which python)"
python --version
echo ""

if [[ ! -f "${INPUT}" ]]; then
    echo "ERROR: Input file not found: ${INPUT}"
    exit 1
fi

INPUT_LINES=$(wc -l < "${INPUT}")
echo "Input file: ${INPUT}"
echo "Input lines: ${INPUT_LINES}"
echo ""

if [[ -f "${OUTPUT}" ]]; then
    OUTPUT_LINES=$(wc -l < "${OUTPUT}")
    echo "Resuming from existing output: ${OUTPUT}"
    echo "Already processed: ${OUTPUT_LINES} r1"
else
    echo "Starting fresh run"
fi
echo ""

# ----------------------------
# Run
# ----------------------------
echo "Starting hop_support_v3.py..."
echo "Parameters:"
echo "  --chunk_size ${CHUNK_SIZE}"
echo "  --qps ${QPS}"
echo "  --workers ${WORKERS}"
echo "  --max_inflight ${MAX_INFLIGHT}"
echo "  --timeout_sec ${TIMEOUT_SEC}"
echo "  --triplets_output_jsonl ${TRIPLETS_OUTPUT}"
echo "  --triplets_queue_size ${TRIPLETS_QUEUE_SIZE}"
echo ""

python "${SCRIPT}" \
    --input "${INPUT}" \
    --output_jsonl "${OUTPUT}" \
    --checkpoint "${CHECKPOINT}" \
    --resume \
    --user_agent "${USER_AGENT}" \
    --chunk_size ${CHUNK_SIZE} \
    --qps ${QPS} \
    --workers ${WORKERS} \
    --max_inflight ${MAX_INFLIGHT} \
    --timeout_sec ${TIMEOUT_SEC} \
    --max_retries ${MAX_RETRIES} \
    --topk ${TOPK} \
    --triplets_output_jsonl "${TRIPLETS_OUTPUT}" \
    --triplets_queue_size ${TRIPLETS_QUEUE_SIZE} \
    --log_level INFO

EXIT_CODE=$?

# ----------------------------
# Summary
# ----------------------------
echo ""
echo "============================================================"
echo "Job finished: $(date)"
echo "Exit code: ${EXIT_CODE}"

if [[ -f "${OUTPUT}" ]]; then
    FINAL_LINES=$(wc -l < "${OUTPUT}")
    echo "Output lines: ${FINAL_LINES}"
fi

if [[ -f "${TRIPLETS_OUTPUT}" ]]; then
    TRIPLETS_LINES=$(wc -l < "${TRIPLETS_OUTPUT}")
    echo "Triplets output lines: ${TRIPLETS_LINES}"
fi

if [[ -f "${CHECKPOINT}" ]]; then
    echo "Checkpoint:"
    cat "${CHECKPOINT}"
fi

echo "============================================================"

exit ${EXIT_CODE}
