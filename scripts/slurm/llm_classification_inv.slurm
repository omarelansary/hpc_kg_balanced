#!/bin/bash
#SBATCH --job-name=llm_classification_inv
#SBATCH --output=logs/llm_classification_inv_%j.out
#SBATCH --error=logs/llm_classification_inv_%j.err
#SBATCH --time=72:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
# Optional for parallel shards (override at submit time if needed):
#SBATCH --array=0-7

set -euo pipefail

WORK_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
SCRIPT="${WORK_DIR}/src/llm_classification_inv.py"
INPUT_PATH="${WORK_DIR}/data/processed/hop_support.wikibase_item_only.jsonl"
RELATION_PROFILES_PATH="${WORK_DIR}/data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json"
LABELS_PATH="${WORK_DIR}/data/raw/wikidata_ontology.properties_label_embeddings.json"
INVERSE_ALIASES_PATH="${WORK_DIR}/data/processed/wikidata_ontology.inverse_mode_aliases_topk.json"
OUTPUT_BASENAME="${WORK_DIR}/data/processed/hop_support.wikibase_item_only.inv_llm"
REPORT_BASENAME="${WORK_DIR}/data/processed/hop_support.wikibase_item_only.inv_llm.report"

MODEL="gpt-4.1"
CANDIDATE_SOURCE="union"
BATCH_SIZE=15
CHECKPOINT_EVERY=1
MAX_ALIASES_PER_RELATION=3
MAX_ALIAS_CHARS=80
ALIAS_SAMPLE_SEED=42

# Sharding controls
# - In array mode, shard index comes from SLURM_ARRAY_TASK_ID
# - NUM_SHARDS defaults to SLURM_ARRAY_TASK_COUNT when available
NUM_SHARDS="${NUM_SHARDS:-${SLURM_ARRAY_TASK_COUNT:-1}}"
SHARD_INDEX="${SLURM_ARRAY_TASK_ID:-0}"

OUTPUT_PATH="${OUTPUT_BASENAME}.shard${SHARD_INDEX}.jsonl"
REPORT_PATH="${REPORT_BASENAME}.shard${SHARD_INDEX}.json"

echo "============================================================"
echo "Job started: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-N/A}"
echo "Node: ${SLURMD_NODENAME:-N/A}"
echo "Work dir: ${WORK_DIR}"
echo "============================================================"

cd "${WORK_DIR}"
mkdir -p "${WORK_DIR}/logs"

# Load environment variables (expects OPENAI_API_KEY in .env)
if [[ -f "${WORK_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${WORK_DIR}/.env"
  set +a
else
  echo "ERROR: .env not found at ${WORK_DIR}/.env"
  exit 1
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: OPENAI_API_KEY is missing after loading .env"
  exit 1
fi

# Optional venv activation
if [[ -f "${WORK_DIR}/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${WORK_DIR}/.venv/bin/activate"
fi

echo "Python: $(which python)"
python --version
echo "Input: ${INPUT_PATH}"
echo "Output: ${OUTPUT_PATH}"
echo "Report: ${REPORT_PATH}"
echo "Inverse aliases context: ${INVERSE_ALIASES_PATH}"
echo "Sharding: num_shards=${NUM_SHARDS} shard_index=${SHARD_INDEX}"
echo ""

python "${SCRIPT}" \
  --input_path "${INPUT_PATH}" \
  --relation_profiles_path "${RELATION_PROFILES_PATH}" \
  --labels_path "${LABELS_PATH}" \
  --inverse_aliases_path "${INVERSE_ALIASES_PATH}" \
  --output_path "${OUTPUT_PATH}" \
  --report_path "${REPORT_PATH}" \
  --model "${MODEL}" \
  --candidate_source "${CANDIDATE_SOURCE}" \
  --batch_size "${BATCH_SIZE}" \
  --max_aliases_per_relation "${MAX_ALIASES_PER_RELATION}" \
  --max_alias_chars "${MAX_ALIAS_CHARS}" \
  --alias_sample_seed "${ALIAS_SAMPLE_SEED}" \
  --num_shards "${NUM_SHARDS}" \
  --shard_index "${SHARD_INDEX}" \
  --checkpoint_every "${CHECKPOINT_EVERY}" \
  --resume \
  --log_level INFO

EXIT_CODE=$?

echo ""
echo "============================================================"
echo "Job finished: $(date)"
echo "Exit code: ${EXIT_CODE}"
echo "============================================================"

exit ${EXIT_CODE}
