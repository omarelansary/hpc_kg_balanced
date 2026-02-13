#!/bin/bash
#SBATCH --job-name=hop_support_v2
#SBATCH --output=logs/hop_support_v2_%j.out
#SBATCH --error=logs/hop_support_v2_%j.err
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=omar_essameldeen_ahmad.elansary@mailbox.tu-dresden.de

# ============================================================
# Hop Support v2 - SLURM Job Script
# ============================================================
# Computes loop/non-loop support counts for all (r1, r2) pairs
# Estimated runtime: 3-7 days depending on WDQS responsiveness
# ============================================================

set -euo pipefail

# ----------------------------
# Configuration
# ----------------------------
EMAIL="omar@gmail.com"
USER_AGENT="hop_support/2.0 (mailto:${EMAIL})"

WORK_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
SCRIPT="${WORK_DIR}/src/hop_support_and_sym_anti_verification/hop_support_v2.py"
INPUT="${WORK_DIR}/data/raw/wikidata_ontology.hop_discovery_run2.json"
OUTPUT="${WORK_DIR}/data/processed/hop_support_v2.jsonl"
CHECKPOINT="${WORK_DIR}/data/processed/hop_support_v2_checkpoint.json"

# WDQS parameters (conservative to avoid 429)
CHUNK_SIZE=30
QPS=0.5
WORKERS=8
MAX_INFLIGHT=3
TIMEOUT_SEC=90
MAX_RETRIES=5
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

# Create logs directory if needed
mkdir -p "${WORK_DIR}/logs"

# Activate conda/virtualenv if needed
# source "${HOME}/miniconda3/etc/profile.d/conda.sh"
# conda activate wikidata-env

# Or for virtualenv:
# source "${WORK_DIR}/venv/bin/activate"

# Check Python and dependencies
echo "Python: $(which python)"
python --version
echo ""

# Check input file exists
if [[ ! -f "${INPUT}" ]]; then
    echo "ERROR: Input file not found: ${INPUT}"
    exit 1
fi

INPUT_LINES=$(wc -l < "${INPUT}")
echo "Input file: ${INPUT}"
echo "Input lines: ${INPUT_LINES}"
echo ""

# Check if resuming
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
echo "Starting hop_support_v2.py..."
echo "Parameters:"
echo "  --chunk_size ${CHUNK_SIZE}"
echo "  --qps ${QPS}"
echo "  --workers ${WORKERS}"
echo "  --max_inflight ${MAX_INFLIGHT}"
echo "  --timeout_sec ${TIMEOUT_SEC}"
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

if [[ -f "${CHECKPOINT}" ]]; then
    echo "Checkpoint:"
    cat "${CHECKPOINT}"
fi

echo "============================================================"

exit ${EXIT_CODE}
