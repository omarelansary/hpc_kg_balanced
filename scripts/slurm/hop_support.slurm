#!/bin/bash
#SBATCH --job-name=hop_support
#SBATCH --partition=barnard
#SBATCH --output=hop_support_%j.out
#SBATCH --error=hop_support_%j.err
#SBATCH --time=12:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=8G
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=omar_essameldeen_ahmad.elansary@mailbox.tu-dresden.de

set -euo pipefail
set -x

echo "========== JOB START =========="
echo "Job ID      : ${SLURM_JOB_ID:-N/A}"
echo "Node        : $(hostname)"
echo "Partition   : ${SLURM_JOB_PARTITION:-N/A}"
echo "Start time  : $(date)"
echo "Workdir     : ${SLURM_SUBMIT_DIR:-$(pwd)}"
echo

if [[ -n "${SLURM_SUBMIT_DIR:-}" ]]; then
  cd "$SLURM_SUBMIT_DIR"
fi

echo "=== PYTHON ENV SETUP ==="
if [[ -f ".venv/bin/activate" ]]; then
  source .venv/bin/activate
  echo "Activated venv: .venv"
else
  echo "No .venv found; using system python"
fi
python --version
which python
echo

echo "=== CONFIG ==="
INPUT_PATH="${INPUT_PATH:-data/raw/wikidata_ontology.hop_discovery_run2.json}"
OUTPUT_JSONL="${OUTPUT_JSONL:-data/processed/hop_support.jsonl}"
CHECKPOINT_PATH="${CHECKPOINT_PATH:-data/processed/hop_support_checkpoint.json}"
WDQS_ENDPOINT="${WDQS_ENDPOINT:-https://query.wikidata.org/sparql}"
USER_AGENT="${USER_AGENT:-${WDQS_USER_AGENT:-}}"
WORKERS="${WORKERS:-8}"
QPS="${QPS:-0.5}"
MAX_INFLIGHT="${MAX_INFLIGHT:-4}"
CHUNK_SIZE="${CHUNK_SIZE:-40}"
TOPK="${TOPK:-50}"
SAMPLED_T_LIMIT="${SAMPLED_T_LIMIT:-20000}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
RESUME_FLAG="${RESUME_FLAG:---resume}"

echo "INPUT_PATH      : $INPUT_PATH"
echo "OUTPUT_JSONL    : $OUTPUT_JSONL"
echo "CHECKPOINT_PATH : $CHECKPOINT_PATH"
echo "WDQS_ENDPOINT   : $WDQS_ENDPOINT"
echo "WORKERS         : $WORKERS"
echo "QPS             : $QPS"
echo "MAX_INFLIGHT    : $MAX_INFLIGHT"
echo "CHUNK_SIZE      : $CHUNK_SIZE"
echo "TOPK            : $TOPK"
echo "SAMPLED_T_LIMIT : $SAMPLED_T_LIMIT"
echo "LOG_LEVEL       : $LOG_LEVEL"
echo "RESUME_FLAG     : $RESUME_FLAG"
echo

if [[ ! -f "$INPUT_PATH" ]]; then
  echo "ERROR: Input file not found: $INPUT_PATH"
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT_JSONL")" "$(dirname "$CHECKPOINT_PATH")"

if [[ -z "$USER_AGENT" || "$USER_AGENT" != *"mailto:"* ]]; then
  echo "ERROR: USER_AGENT/WDQS_USER_AGENT must contain mailto:..."
  echo "Example: export USER_AGENT='hop_support/1.0 (mailto:you@example.com)'"
  exit 2
fi

echo "=== RUN hop_support.py ==="
CMD=(
  python src/hop_support.py
  --input "$INPUT_PATH"
  --output_jsonl "$OUTPUT_JSONL"
  --checkpoint "$CHECKPOINT_PATH"
  --wdqs_endpoint "$WDQS_ENDPOINT"
  --user_agent "$USER_AGENT"
  --workers "$WORKERS"
  --qps "$QPS"
  --max_inflight "$MAX_INFLIGHT"
  --chunk_size "$CHUNK_SIZE"
  --topk "$TOPK"
  --sampled_t_limit "$SAMPLED_T_LIMIT"
  --log_level "$LOG_LEVEL"
)

if [[ "$RESUME_FLAG" == "--resume" ]]; then
  CMD+=(--resume)
fi

printf 'Command: '
printf '%q ' "${CMD[@]}"
echo

"${CMD[@]}"
RC=$?

echo
echo "=== OUTPUT CHECK ==="
ls -lh "$OUTPUT_JSONL" "$CHECKPOINT_PATH" 2>/dev/null || true

echo
echo "Exit code   : $RC"
echo "End time    : $(date)"
echo "=========== JOB END ==========="
exit "$RC"
