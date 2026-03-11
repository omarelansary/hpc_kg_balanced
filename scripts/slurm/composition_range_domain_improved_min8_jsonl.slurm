#!/bin/bash
#SBATCH --job-name=composition_min8_jsonl
#SBATCH --output=logs/composition_hop_support_v3_min8_jsonl_%j.out
#SBATCH --error=logs/composition_hop_support_v3_min8_jsonl_%j.err
#SBATCH --time=168:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=omar_essameldeen_ahmad.elansary@mailbox.tu-dresden.de

set -euo pipefail

# ----------------------------
# Project paths
# ----------------------------
WORK_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
SCRIPT_PATH="${WORK_DIR}/src/composition_verification/composition_range_domain_improved.py"

# First RUN 
# INPUT_JSONL="${WORK_DIR}/data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.jsonl"
# OUTPUT_JSONL="${WORK_DIR}/data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition_verified.jsonl"
# OUTPUT_COMPACT_JSONL="${WORK_DIR}/data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl"
# CHECKPOINT_JSON="${WORK_DIR}/data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition.checkpoint.json"
# STATS_JSON="${WORK_DIR}/data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition.stats.json"
# REPORT_JSONL="${WORK_DIR}/data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.composition.report.jsonl"

INPUT_JSONL="${WORK_DIR}/data/processed/hop_support_v3/new_pairs_composition_in_v3_only.jsonl"
OUTPUT_JSONL="${WORK_DIR}/data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.jsonl"
OUTPUT_COMPACT_JSONL="${WORK_DIR}/data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl"
CHECKPOINT_JSON="${WORK_DIR}/data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition.checkpoint.json"
STATS_JSON="${WORK_DIR}/data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition.stats.json"
REPORT_JSONL="${WORK_DIR}/data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition.report.jsonl"

# ----------------------------
# Runtime config
# ----------------------------
USER_AGENT="CompositionChecker/2.0 (contact: omar.ansary@gmail.com)"
ENDPOINT="https://query.wikidata.org/sparql"

TIMEOUT_S=60
MAX_RETRIES=3
BACKOFF_S=2.0
MIN_DELAY_S=0.2
MAX_DELAY_S=0.5

LIMIT=1000
OFFSET=0
SAMPLE_N=300
EXAMPLES_K=5
MAX_EXAMPLE_TARGETS=20
PAIRS_BATCH_SIZE=300
TARGETS_BATCH_SIZE=30
LOG_EVERY_DOCS=1
LOG_LEVEL="INFO"

# Optional flags
USE_RESUME=true
USE_DETERMINISTIC_SAMPLE=true
USE_REQUIRE_DISTINCT_NODES=false
USE_EXCLUDE_SELF_LOOPS=true

# ----------------------------
# Env setup
# ----------------------------
cd "${WORK_DIR}"
mkdir -p "${WORK_DIR}/logs" "${WORK_DIR}/data/processed"

if [ -f "${WORK_DIR}/.venv/bin/activate" ]; then
  source "${WORK_DIR}/.venv/bin/activate"
fi

if [[ ! -f "${INPUT_JSONL}" ]]; then
  echo "ERROR: Input file not found: ${INPUT_JSONL}"
  exit 1
fi

EXTRA_FLAGS=()
if [ "${USE_RESUME}" = "true" ]; then
  EXTRA_FLAGS+=("--resume")
fi
if [ "${USE_DETERMINISTIC_SAMPLE}" = "true" ]; then
  EXTRA_FLAGS+=("--deterministic_sample")
fi
if [ "${USE_REQUIRE_DISTINCT_NODES}" = "true" ]; then
  EXTRA_FLAGS+=("--require_distinct_nodes")
fi
if [ "${USE_EXCLUDE_SELF_LOOPS}" = "true" ]; then
  EXTRA_FLAGS+=("--exclude_self_loops")
fi

echo "============================================================"
echo "Job started: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-N/A}"
echo "Node: ${SLURMD_NODENAME:-N/A}"
echo "Input: ${INPUT_JSONL}"
echo "Output: ${OUTPUT_JSONL}"
echo "Compact output: ${OUTPUT_COMPACT_JSONL}"
echo "Checkpoint: ${CHECKPOINT_JSON}"
echo "Stats: ${STATS_JSON}"
echo "Report: ${REPORT_JSONL}"
echo "============================================================"

python "${SCRIPT_PATH}" \
  --input_jsonl "${INPUT_JSONL}" \
  --output_jsonl "${OUTPUT_JSONL}" \
  --output_jsonl_compact "${OUTPUT_COMPACT_JSONL}" \
  --jsonl_checkpoint "${CHECKPOINT_JSON}" \
  --stats_path "${STATS_JSON}" \
  --report_path "${REPORT_JSONL}" \
  --endpoint "${ENDPOINT}" \
  --user_agent "${USER_AGENT}" \
  --timeout_s "${TIMEOUT_S}" \
  --max_retries "${MAX_RETRIES}" \
  --backoff_s "${BACKOFF_S}" \
  --min_delay_s "${MIN_DELAY_S}" \
  --max_delay_s "${MAX_DELAY_S}" \
  --limit "${LIMIT}" \
  --offset "${OFFSET}" \
  --sample_n "${SAMPLE_N}" \
  --examples_k "${EXAMPLES_K}" \
  --max_example_targets "${MAX_EXAMPLE_TARGETS}" \
  --pairs_batch_size "${PAIRS_BATCH_SIZE}" \
  --targets_batch_size "${TARGETS_BATCH_SIZE}" \
  --log_every_docs "${LOG_EVERY_DOCS}" \
  --log_level "${LOG_LEVEL}" \
  "${EXTRA_FLAGS[@]}"

EXIT_CODE=$?

echo "============================================================"
echo "Job finished: $(date)"
echo "Exit code: ${EXIT_CODE}"
echo "============================================================"

exit ${EXIT_CODE}
