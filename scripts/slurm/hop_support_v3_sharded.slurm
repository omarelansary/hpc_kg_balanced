#!/bin/bash
#SBATCH --job-name=hop_support_v3_sharded
#SBATCH --output=logs/hop_support_v3_sharded_%A_%a.out
#SBATCH --error=logs/hop_support_v3_sharded_%A_%a.err
#SBATCH --time=168:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
# Optional: override at submit time
#SBATCH --array=0-1

set -euo pipefail

# ------------------------------------------------------------
# Minimal sharded runner for hop_support_v3.py
# 1) Create shard inputs with scripts/shard_hop_support_v3_input.py
# 2) Submit this script as an array job
# 3) Merge outputs with scripts/merge_hop_support_v3_shards.py
# ------------------------------------------------------------

WORK_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
SCRIPT="${WORK_DIR}/src/hop_support_and_sym_anti_verification/hop_support_v3.py"

EMAIL="${EMAIL:-oansary@gmail.com}"
USER_AGENT="${USER_AGENT:-hop_support/3.0 (mailto:${EMAIL})}"

# Shard controls
NUM_SHARDS="${NUM_SHARDS:-${SLURM_ARRAY_TASK_COUNT:-1}}"
SHARD_INDEX="${SHARD_INDEX:-${SLURM_ARRAY_TASK_ID:-0}}"
SHARD_INPUT_DIR="${SHARD_INPUT_DIR:-${WORK_DIR}/data/processed/shards}"
SHARD_INPUT_PREFIX="${SHARD_INPUT_PREFIX:-hop_support_v3_input}"
RUN_TAG="${RUN_TAG:-hop_support_v3_sharded}"

# Output directories (isolated per run-tag and per shard)
OUTPUT_DIR="${OUTPUT_DIR:-${WORK_DIR}/data/processed/shards/${RUN_TAG}}"
mkdir -p "${WORK_DIR}/logs" "${OUTPUT_DIR}"

SHARD_WIDTH="${#NUM_SHARDS}"
if (( SHARD_WIDTH < 2 )); then
  SHARD_WIDTH=2
fi
printf -v SHARD_ID "%0${SHARD_WIDTH}d" "${SHARD_INDEX}"
printf -v SHARD_N "%0${SHARD_WIDTH}d" "${NUM_SHARDS}"

INPUT="${SHARD_INPUT_DIR}/${SHARD_INPUT_PREFIX}.s${SHARD_ID}of${SHARD_N}.jsonl"
OUTPUT="${OUTPUT_DIR}/output.s${SHARD_ID}of${SHARD_N}.jsonl"
CHECKPOINT="${OUTPUT_DIR}/checkpoint.s${SHARD_ID}of${SHARD_N}.json"
TRIPLETS_OUTPUT="${OUTPUT_DIR}/triplets.s${SHARD_ID}of${SHARD_N}.jsonl"
FINGERPRINT_PATH="${OUTPUT_DIR}/fingerprint.s${SHARD_ID}of${SHARD_N}.txt"

# WDQS parameters (conservative defaults for parallel shards)
CHUNK_SIZE="${CHUNK_SIZE:-10}"
QPS="${QPS:-0.015}"
WORKERS="${WORKERS:-2}"
MAX_INFLIGHT="${MAX_INFLIGHT:-1}"
TIMEOUT_SEC="${TIMEOUT_SEC:-180}"
MAX_RETRIES="${MAX_RETRIES:-2}"
TOPK="${TOPK:-50}"
TRIPLETS_QUEUE_SIZE="${TRIPLETS_QUEUE_SIZE:-1000}"

echo "============================================================"
echo "Job started: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-N/A} ArrayTask: ${SLURM_ARRAY_TASK_ID:-N/A}"
echo "Node: ${SLURMD_NODENAME:-N/A}"
echo "Work dir: ${WORK_DIR}"
echo "Shard: index=${SHARD_INDEX} num_shards=${NUM_SHARDS}"
echo "Input: ${INPUT}"
echo "Output: ${OUTPUT}"
echo "Triplets: ${TRIPLETS_OUTPUT}"
echo "============================================================"

if [[ ! -f "${INPUT}" ]]; then
  echo "ERROR: shard input not found: ${INPUT}"
  exit 1
fi

cd "${WORK_DIR}"

if [[ -f "${WORK_DIR}/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${WORK_DIR}/.venv/bin/activate"
fi

echo "Python: $(which python)"
python --version
echo ""

PY_CMD=(
  python "${SCRIPT}"
  --input "${INPUT}"
  --output_jsonl "${OUTPUT}"
  --checkpoint "${CHECKPOINT}"
  --resume
  --user_agent "${USER_AGENT}"
  --chunk_size "${CHUNK_SIZE}"
  --qps "${QPS}"
  --workers "${WORKERS}"
  --max_inflight "${MAX_INFLIGHT}"
  --timeout_sec "${TIMEOUT_SEC}"
  --max_retries "${MAX_RETRIES}"
  --topk "${TOPK}"
  --triplets_output_jsonl "${TRIPLETS_OUTPUT}"
  --triplets_queue_size "${TRIPLETS_QUEUE_SIZE}"
  --log_level INFO
)

CLI_RENDERED="$(printf '%q ' "${PY_CMD[@]}")"
SCRIPT_SHA256="$(sha256sum "$0" | awk '{print $1}')"
RUN_FINGERPRINT="$(
  {
    printf '%s\n' "script=${0}"
    printf '%s\n' "script_sha256=${SCRIPT_SHA256}"
    printf '%s\n' "slurm_job_id=${SLURM_JOB_ID:-N/A}"
    printf '%s\n' "slurm_array_task_id=${SLURM_ARRAY_TASK_ID:-N/A}"
    printf '%s\n' "num_shards=${NUM_SHARDS}"
    printf '%s\n' "shard_index=${SHARD_INDEX}"
    printf '%s\n' "input=${INPUT}"
    printf '%s\n' "output=${OUTPUT}"
    printf '%s\n' "triplets_output=${TRIPLETS_OUTPUT}"
    printf '%s\n' "checkpoint=${CHECKPOINT}"
    printf '%s\n' "cli=${CLI_RENDERED}"
  } | sha256sum | awk '{print $1}'
)"

echo "CLI command:"
echo "  ${CLI_RENDERED}"
echo "Run fingerprint: ${RUN_FINGERPRINT}"
echo "Script sha256: ${SCRIPT_SHA256}"
{
  echo "run_fingerprint=${RUN_FINGERPRINT}"
  echo "script_sha256=${SCRIPT_SHA256}"
  echo "slurm_job_id=${SLURM_JOB_ID:-N/A}"
  echo "slurm_array_task_id=${SLURM_ARRAY_TASK_ID:-N/A}"
  echo "num_shards=${NUM_SHARDS}"
  echo "shard_index=${SHARD_INDEX}"
  echo "input=${INPUT}"
  echo "output=${OUTPUT}"
  echo "triplets_output=${TRIPLETS_OUTPUT}"
  echo "checkpoint=${CHECKPOINT}"
  echo "cli=${CLI_RENDERED}"
} > "${FINGERPRINT_PATH}"
echo "Fingerprint file: ${FINGERPRINT_PATH}"
echo ""

"${PY_CMD[@]}"

EXIT_CODE=$?

echo ""
echo "============================================================"
echo "Job finished: $(date)"
echo "Exit code: ${EXIT_CODE}"
if [[ -f "${OUTPUT}" ]]; then
  echo "Output lines: $(wc -l < "${OUTPUT}")"
fi
if [[ -f "${TRIPLETS_OUTPUT}" ]]; then
  echo "Triplets lines: $(wc -l < "${TRIPLETS_OUTPUT}")"
fi
echo "============================================================"

exit ${EXIT_CODE}
