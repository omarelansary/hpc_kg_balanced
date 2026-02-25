#!/bin/bash
#SBATCH --job-name=hop_discovery_json
#SBATCH --output=logs/hop_discovery_json_%j.out
#SBATCH --error=logs/hop_discovery_json_%j.err
#SBATCH --time=48:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G

set -euo pipefail

# ----------------------------
# Project paths
# ----------------------------
WORK_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
SCRIPT_PATH="${WORK_DIR}/src/archive/hop_discovery.py"

# Input/exported JSON from relation_profiles
INPUT_JSON="${WORK_DIR}/data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json"

# Output + checkpoint (file mode)
OUTPUT_JSONL="${WORK_DIR}/data/processed/hop_discovery_from_json.jsonl"
CHECKPOINT_JSON="${WORK_DIR}/data/processed/hop_discovery_from_json.checkpoint.json"

# ----------------------------
# WDQS / runtime config
# ----------------------------
USER_AGENT="hop_discovery/1.0 (mailto:omar@gmail.com)"
WDQS_ENDPOINT="https://query.wikidata.org/sparql"
TIMEOUT_SEC=180
MAX_RETRIES=7
BACKOFF_BASE_SEC=5
BACKOFF_CAP_SEC=300

# Query / processing controls
NUM_QUERY_WORKERS=4
SAMPLE_LIMIT=50000
CHECKPOINT_EVERY=50
DELAY_BETWEEN_QUERIES=0.5
LOG_LEVEL="INFO"

# Optional behavior flags (set to true/false)
USE_FILTER_TO_VALID_R2=true
USE_SKIP_EXISTING=true
USE_RETRY_ERRORS=true

# ----------------------------
# Env setup
# ----------------------------
cd "${WORK_DIR}"
mkdir -p "${WORK_DIR}/logs" "${WORK_DIR}/data/processed"

if [ -f "${WORK_DIR}/.venv/bin/activate" ]; then
  source "${WORK_DIR}/.venv/bin/activate"
fi

# Build optional flags
EXTRA_FLAGS=()
if [ "${USE_FILTER_TO_VALID_R2}" = "true" ]; then
  EXTRA_FLAGS+=("--filter_to_valid_r2")
fi
if [ "${USE_SKIP_EXISTING}" = "true" ]; then
  EXTRA_FLAGS+=("--skip_existing")
fi
if [ "${USE_RETRY_ERRORS}" = "true" ]; then
  EXTRA_FLAGS+=("--retry_errors")
fi

# ----------------------------
# Run (JSON file mode)
# ----------------------------
python "${SCRIPT_PATH}" \
  --input_json "${INPUT_JSON}" \
  --output_jsonl "${OUTPUT_JSONL}" \
  --checkpoint_json "${CHECKPOINT_JSON}" \
  --user_agent "${USER_AGENT}" \
  --wdqs_endpoint "${WDQS_ENDPOINT}" \
  --timeout_sec "${TIMEOUT_SEC}" \
  --max_retries "${MAX_RETRIES}" \
  --backoff_base_sec "${BACKOFF_BASE_SEC}" \
  --backoff_cap_sec "${BACKOFF_CAP_SEC}" \
  --num_query_workers "${NUM_QUERY_WORKERS}" \
  --sample_limit "${SAMPLE_LIMIT}" \
  --checkpoint_every "${CHECKPOINT_EVERY}" \
  --delay_between_queries "${DELAY_BETWEEN_QUERIES}" \
  --log_level "${LOG_LEVEL}" \
  "${EXTRA_FLAGS[@]}"
