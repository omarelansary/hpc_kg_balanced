#!/bin/bash
#SBATCH --job-name=extract_ckpt_t9_non_giant
#SBATCH --output=logs/extract_ckpt_expand_%j.out
#SBATCH --error=logs/extract_ckpt_expand_%j.err
#SBATCH --time=168:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G

set -euo pipefail

ROOT_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
cd "${ROOT_DIR}"
mkdir -p logs data/connectedgraph

# -------- Inputs --------
CHECKPOINT_JSON="data/connectedgraph/trial9_phase4_connected_realization.snapshot.json"

# -------- Outputs --------
OUT_TRIPLES="data/connectedgraph/trial9_attempt2_non_giant.triples.jsonl"
OUT_STATS="data/connectedgraph/trial9_attempt2_non_giant.stats.json"
OUT_REL_CSV="data/connectedgraph/trial9_attempt2_non_giant.relations.csv"
OUT_HTML="data/connectedgraph/trial9_attempt2_non_giant.graph.html"
EXPAND_CKPT="data/connectedgraph/trial9_attempt2_non_giant_expansion.checkpoint.json"

# -------- Attempt selection --------
ATTEMPT_MODE="running"   # auto|running|final
ATTEMPT_NUMBER=""        # e.g. "2" (leave empty for direct checkpoint_json)
ATTEMPT_GLOB=""          # e.g. data/connectedgraph/snapshots/trial9_attempt*.json

# -------- Component filtering --------
MIN_COMPONENT_NODES="50"
MIN_COMPONENT_TRIPLES="50"
EXCLUDE_LARGEST_FLAG="--exclude_largest_component"
KEEP_LARGEST_FLAG=""     # set to --keep_largest_only (mutually exclusive with exclude)
MAX_COMPONENTS="0"

# -------- Visualization --------
VIZ_MAX_NODES="0"
VIZ_MAX_EDGES="0"
VIZ_TOP_REL="25"
VIZ_LAYOUT_SEED="42"
VIZ_LAYOUT_ITERS="120"
VIZ_SAMPLE_EDGES_FLAG=""

# -------- Targeted expansion --------
EXPAND_SMALL_FLAG="--expand_small_components"
EXPAND_ENDPOINT="https://query.wikidata.org/sparql"
EXPAND_USER_AGENT="kg-expand/1.0 (mailto:omaransary@gmail.com)"
EXPAND_TIMEOUT_SEC="30"
EXPAND_RETRIES="2"
EXPAND_ROUNDS="2"
EXPAND_NODES_PER_QUERY="20"
EXPAND_LIMIT_PER_QUERY="120"
EXPAND_MAX_NEW_TRIPLES="3000"
EXPAND_RESUME_FLAG=""
EXPAND_CKPT_EVERY_ROUNDS="1"

echo "============================================================"
echo "Extract Subgraphs + Targeted Expansion"
echo "Job started: $(date)"
echo "Job ID: ${SLURM_JOB_ID}"
echo "Node: $(hostname)"
echo "Checkpoint JSON: ${CHECKPOINT_JSON}"
echo "Output triples: ${OUT_TRIPLES}"
echo "Expansion checkpoint: ${EXPAND_CKPT}"
echo "============================================================"

CMD=(
  python -u src/statistics/extract_subgraphs_from_checkpoint.py
  --checkpoint_json "${CHECKPOINT_JSON}"
  --output_triples_jsonl "${OUT_TRIPLES}"
  --output_stats_json "${OUT_STATS}"
  --output_relations_csv "${OUT_REL_CSV}"
  --out_html "${OUT_HTML}"
  --attempt_mode "${ATTEMPT_MODE}"
  --min_component_nodes "${MIN_COMPONENT_NODES}"
  --min_component_triples "${MIN_COMPONENT_TRIPLES}"
  --max_components "${MAX_COMPONENTS}"
  --viz_max_nodes "${VIZ_MAX_NODES}"
  --viz_max_edges "${VIZ_MAX_EDGES}"
  --viz_top_relations_colored "${VIZ_TOP_REL}"
  --viz_layout_seed "${VIZ_LAYOUT_SEED}"
  --viz_layout_iterations "${VIZ_LAYOUT_ITERS}"
  --expand_endpoint_url "${EXPAND_ENDPOINT}"
  --expand_user_agent "${EXPAND_USER_AGENT}"
  --expand_timeout_sec "${EXPAND_TIMEOUT_SEC}"
  --expand_retries "${EXPAND_RETRIES}"
  --expand_rounds "${EXPAND_ROUNDS}"
  --expand_nodes_per_query "${EXPAND_NODES_PER_QUERY}"
  --expand_limit_per_query "${EXPAND_LIMIT_PER_QUERY}"
  --expand_max_new_triples_total "${EXPAND_MAX_NEW_TRIPLES}"
  --expand_checkpoint_path "${EXPAND_CKPT}"
  --expand_checkpoint_every_rounds "${EXPAND_CKPT_EVERY_ROUNDS}"
)

if [[ -n "${ATTEMPT_NUMBER}" ]]; then
  CMD+=(--attempt_number "${ATTEMPT_NUMBER}")
fi
if [[ -n "${ATTEMPT_GLOB}" ]]; then
  CMD+=(--attempt_checkpoints_glob "${ATTEMPT_GLOB}")
fi
if [[ -n "${EXCLUDE_LARGEST_FLAG}" ]]; then
  CMD+=(${EXCLUDE_LARGEST_FLAG})
fi
if [[ -n "${KEEP_LARGEST_FLAG}" ]]; then
  CMD+=(${KEEP_LARGEST_FLAG})
fi
if [[ -n "${VIZ_SAMPLE_EDGES_FLAG}" ]]; then
  CMD+=(${VIZ_SAMPLE_EDGES_FLAG})
fi
if [[ -n "${EXPAND_SMALL_FLAG}" ]]; then
  CMD+=(${EXPAND_SMALL_FLAG})
fi
if [[ -n "${EXPAND_RESUME_FLAG}" ]]; then
  CMD+=(${EXPAND_RESUME_FLAG})
fi

printf '[cmd] %q ' "${CMD[@]}"; echo
"${CMD[@]}"
RC=$?

echo "============================================================"
echo "Extract completed: $(date)"
echo "Exit code: ${RC}"
echo "============================================================"
exit "${RC}"
