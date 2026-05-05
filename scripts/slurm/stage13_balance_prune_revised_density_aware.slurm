#!/bin/bash
# Revised Stage13 pruning run:
# - balance-first
# - density-aware
# - connectivity-preserving by default
# - explicit relation-throttling and post-round guard settings
#
# This wrapper is intended for a "real" revised experiment rather than the
# destructive ablation. It keeps the downstream analysis / plotting stages from
# the existing Stage13 wrappers, but switches to the revised pruning engine and
# passes the new control parameters explicitly.
#
# Override any variable at submission time, for example:
#   MAX_TOTAL_REMOVALS=1800 RELATION_OVERCAP_MODE=sqrt \
#   sbatch scripts/slurm/stage13_balance_prune_revised_density_aware.slurm

#SBATCH --job-name=stage13_prune_revised
#SBATCH --output=logs/stage13_prune_revised_%j.out
#SBATCH --error=logs/stage13_prune_revised_%j.err
#SBATCH --time=168:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=omar_essameldeen_ahmad.elansary@mailbox.tu-dresden.de

set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$PWD}"
mkdir -p logs

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

pick_first_existing_file() {
  local path
  for path in "$@"; do
    if [[ -f "${path}" ]]; then
      printf '%s\n' "${path}"
      return 0
    fi
  done
  printf '%s\n' "$1"
}

pick_first_existing_dir() {
  local path
  for path in "$@"; do
    if [[ -d "${path}" ]]; then
      printf '%s\n' "${path}"
      return 0
    fi
  done
  printf '%s\n' "$1"
}

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "No Python interpreter found." >&2
    exit 1
  fi
fi

PRUNER_PY="${PRUNER_PY:-$(pick_first_existing_file \
  'src/Pruning graph/kg_balance_pruner_revised_pruning_only.py')}"
ANALYZE_PY="${ANALYZE_PY:-$(pick_first_existing_file \
  'src/kg_builder/analyze_graph_against_allocation.py' \
  'src/Pruning graph/analyze_graph_against_allocation.py')}"
PLOT_PY="${PLOT_PY:-$(pick_first_existing_file \
  'src/kg_builder/plot_triplets_graph_3d.py' \
  'src/Pruning graph/plot_triplets_graph_3d.py')}"
KG_PATTERN_STATS_PY="${KG_PATTERN_STATS_PY:-$(pick_first_existing_file \
  'src/statistics/kg_pattern_stats.py')}"
EXTRACT_2PATHS_PY="${EXTRACT_2PATHS_PY:-$(pick_first_existing_file \
  'src/statistics/extract_2paths.py')}"

BASE_DIR="${BASE_DIR:-$(pick_first_existing_dir \
  'runs/prod_refine_20260315_180520/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod' \
  'src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod')}"
ALLOCATION_MANIFEST="${ALLOCATION_MANIFEST:-$(pick_first_existing_file \
  'src/kg_builder/input/bidirectional_allocation_results5k.json' \
  'src/Pruning graph/bidirectional_allocation_results5k.json')}"
INPUT_GRAPH="${INPUT_GRAPH:-${BASE_DIR}/largest_component.csv}"

RUN_TS="${RUN_TS:-$(date +%Y%m%d_%H%M%S)}"
PRUNE_DIR="${PRUNE_DIR:-${BASE_DIR}/stage13_balance_prune_revised_density_aware_${RUN_TS}}"

# Core pruning budget. These defaults are intentionally less destructive than
# the ablation, but less conservative than the original Stage13 run.
MAX_ROUNDS="${MAX_ROUNDS:-60}"
MAX_BATCH_REMOVALS="${MAX_BATCH_REMOVALS:-50}" # was 25 (conservative)
MAX_TOTAL_REMOVALS="${MAX_TOTAL_REMOVALS:-2000}" # was 1200 (conservative)
SELECTION_MODE="${SELECTION_MODE:-sequential}"

# Structural protections remain on by default for the revised experiment.
DISABLE_HARD_PRESERVE_LARGEST_COMPONENT="${DISABLE_HARD_PRESERVE_LARGEST_COMPONENT:-0}"
DISABLE_HARD_PROTECT_PATTERNS_BELOW_TARGET="${DISABLE_HARD_PROTECT_PATTERNS_BELOW_TARGET:-0}"

# Original structural scoring terms.
BRIDGE_PENALTY="${BRIDGE_PENALTY:-1000000}"
LOW_DEGREE_PENALTY="${LOW_DEGREE_PENALTY:-50}"
LOW_DEGREE_THRESHOLD="${LOW_DEGREE_THRESHOLD:-2}"
ARTICULATION_ENDPOINT_PENALTY="${ARTICULATION_ENDPOINT_PENALTY:-20}"
LOCAL_REDUNDANCY_BONUS="${LOCAL_REDUNDANCY_BONUS:-5}"
COMMON_NEIGHBOR_BONUS_CAP="${COMMON_NEIGHBOR_BONUS_CAP:-10}"
SAME_COMPONENT_CYCLE_BONUS="${SAME_COMPONENT_CYCLE_BONUS:-2}"

# Balance / saturation controls.
PATTERN_SURPLUS_WEIGHT="${PATTERN_SURPLUS_WEIGHT:-10}"
PATTERN_DEFICIT_PENALTY_WEIGHT="${PATTERN_DEFICIT_PENALTY_WEIGHT:-25}"
PROTECTED_PATTERN_PENALTY_WEIGHT="${PROTECTED_PATTERN_PENALTY_WEIGHT:-40}"
RELATION_OVERCAP_WEIGHT="${RELATION_OVERCAP_WEIGHT:-2}"
RELATION_OVERCAP_MODE="${RELATION_OVERCAP_MODE:-log1p}"
RELATION_OVERCAP_CAP="${RELATION_OVERCAP_CAP:-25}"

# Density / local structure controls.
DENSITY_TRIPLES_PER_ENTITY_PENALTY="${DENSITY_TRIPLES_PER_ENTITY_PENALTY:-10}"
DENSITY_ENTITIES_PER_TRIPLE_PENALTY="${DENSITY_ENTITIES_PER_TRIPLE_PENALTY:-10}"
TARGET_MIN_TRIPLES_PER_ENTITY="${TARGET_MIN_TRIPLES_PER_ENTITY:-1.02}" # was 1.05
TARGET_MAX_ENTITIES_PER_TRIPLE="${TARGET_MAX_ENTITIES_PER_TRIPLE:-0.98}" # was 0.95
TARGET_MIN_AVERAGE_PARTICIPATION="${TARGET_MIN_AVERAGE_PARTICIPATION:-2.04}" # was 2.10
PROJECTED_LOW_DEGREE_CREATION_PENALTY="${PROJECTED_LOW_DEGREE_CREATION_PENALTY:-15}"
TWO_PATH_LOSS_PENALTY="${TWO_PATH_LOSS_PENALTY:-1}"
HARD_GUARD_PROJECTED_TRIPLES_GT_ENTITIES="${HARD_GUARD_PROJECTED_TRIPLES_GT_ENTITIES:-1}"

# Relation floor / semantic backbone protection.
PROTECTED_RELATIONS="${PROTECTED_RELATIONS:-P31,P279}"
HARD_RELATION_MIN_COUNTS="${HARD_RELATION_MIN_COUNTS:-P31=5000,P279=650}" # was P31=5000,P279=650

# Per-round throttling.
MAX_FRACTION_PER_RELATION_PER_ROUND="${MAX_FRACTION_PER_RELATION_PER_ROUND:-0.20}" # was 0.25
MAX_REMOVALS_PER_RELATION_PER_ROUND="${MAX_REMOVALS_PER_RELATION_PER_ROUND:-8}" # was 10

# Batch-level acceptance guards.
BATCH_GUARD_ACTION="${BATCH_GUARD_ACTION:-reject_round}"
MIN_POST_ROUND_TRIPLES_PER_ENTITY="${MIN_POST_ROUND_TRIPLES_PER_ENTITY:-1.05}"
MAX_POST_ROUND_ENTITIES_PER_TRIPLE="${MAX_POST_ROUND_ENTITIES_PER_TRIPLE:-0.95}"
MIN_POST_ROUND_AVERAGE_PARTICIPATION="${MIN_POST_ROUND_AVERAGE_PARTICIPATION:-2.10}"
MAX_POST_ROUND_WEAK_COMPONENT_COUNT="${MAX_POST_ROUND_WEAK_COMPONENT_COUNT:-1}"
MIN_POST_ROUND_LARGEST_COMPONENT_RATIO="${MIN_POST_ROUND_LARGEST_COMPONENT_RATIO:-1.0}"

PRUNED_GRAPH="${PRUNED_GRAPH:-${PRUNE_DIR}/pruned_graph.jsonl}"
PRUNED_GRAPH_CSV="${PRUNED_GRAPH_CSV:-${PRUNE_DIR}/pruned_graph.csv}"
PRUNED_REPORT="${PRUNED_REPORT:-${PRUNE_DIR}/pruned_graph.report.json}"
PRUNED_BRANCH_ETA_DIR="${PRUNED_BRANCH_ETA_DIR:-${PRUNE_DIR}/eta_analysis}"
PRUNED_GRAPH_PATTERN_STATS_DIR="${PRUNED_GRAPH_PATTERN_STATS_DIR:-${PRUNE_DIR}/pattern_stats_pruned_graph}"
PRUNED_GRAPH_2PATHS_CSV="${PRUNED_GRAPH_2PATHS_CSV:-${PRUNE_DIR}/pruned_graph_2paths.csv}"
PRUNED_BRANCH_PLOT_HTML="${PRUNED_BRANCH_PLOT_HTML:-${PRUNE_DIR}/pruned_graph.3d.html}"
LCC_HTML="${LCC_HTML:-${PRUNE_DIR}/largest_component.3d.html}"
LCC_CSV="${LCC_CSV:-${PRUNE_DIR}/largest_component.csv}"
LCC_ETA_DIR="${LCC_ETA_DIR:-${PRUNE_DIR}/largest_component_eta_analysis}"
LCC_PATTERN_STATS_DIR="${LCC_PATTERN_STATS_DIR:-${PRUNE_DIR}/pattern_stats_largest_component}"
LCC_2PATHS_CSV="${LCC_2PATHS_CSV:-${PRUNE_DIR}/largest_component_2paths.csv}"

for required_path in \
  "${PRUNER_PY}" \
  "${ANALYZE_PY}" \
  "${KG_PATTERN_STATS_PY}" \
  "${EXTRACT_2PATHS_PY}" \
  "${PLOT_PY}" \
  "${ALLOCATION_MANIFEST}" \
  "${INPUT_GRAPH}"
do
  if [[ ! -f "${required_path}" ]]; then
    echo "Missing required input: ${required_path}" >&2
    exit 1
  fi
done

mkdir -p "${PRUNE_DIR}"

log() {
  echo "[$(date --iso-8601=seconds)] $*"
}

PRUNER_ARGS=(
  --input_graph "${INPUT_GRAPH}"
  --allocation_manifest "${ALLOCATION_MANIFEST}"
  --out_graph "${PRUNED_GRAPH}"
  --out_report "${PRUNED_REPORT}"
  --selection_mode "${SELECTION_MODE}"
  --max_rounds "${MAX_ROUNDS}"
  --max_batch_removals "${MAX_BATCH_REMOVALS}"
  --max_total_removals "${MAX_TOTAL_REMOVALS}"
  --pattern_surplus_weight "${PATTERN_SURPLUS_WEIGHT}"
  --pattern_deficit_penalty_weight "${PATTERN_DEFICIT_PENALTY_WEIGHT}"
  --protected_pattern_penalty_weight "${PROTECTED_PATTERN_PENALTY_WEIGHT}"
  --relation_overcap_weight "${RELATION_OVERCAP_WEIGHT}"
  --relation_overcap_mode "${RELATION_OVERCAP_MODE}"
  --relation_overcap_cap "${RELATION_OVERCAP_CAP}"
  --bridge_penalty "${BRIDGE_PENALTY}"
  --low_degree_penalty "${LOW_DEGREE_PENALTY}"
  --low_degree_threshold "${LOW_DEGREE_THRESHOLD}"
  --articulation_endpoint_penalty "${ARTICULATION_ENDPOINT_PENALTY}"
  --local_redundancy_bonus "${LOCAL_REDUNDANCY_BONUS}"
  --common_neighbor_bonus_cap "${COMMON_NEIGHBOR_BONUS_CAP}"
  --same_component_cycle_bonus "${SAME_COMPONENT_CYCLE_BONUS}"
  --density_triples_per_entity_penalty "${DENSITY_TRIPLES_PER_ENTITY_PENALTY}"
  --density_entities_per_triple_penalty "${DENSITY_ENTITIES_PER_TRIPLE_PENALTY}"
  --target_min_triples_per_entity "${TARGET_MIN_TRIPLES_PER_ENTITY}"
  --target_max_entities_per_triple "${TARGET_MAX_ENTITIES_PER_TRIPLE}"
  --target_min_average_participation "${TARGET_MIN_AVERAGE_PARTICIPATION}"
  --projected_low_degree_creation_penalty "${PROJECTED_LOW_DEGREE_CREATION_PENALTY}"
  --two_path_loss_penalty "${TWO_PATH_LOSS_PENALTY}"
  --max_fraction_per_relation_per_round "${MAX_FRACTION_PER_RELATION_PER_ROUND}"
  --max_removals_per_relation_per_round "${MAX_REMOVALS_PER_RELATION_PER_ROUND}"
  --batch_guard_action "${BATCH_GUARD_ACTION}"
  --min_post_round_triples_per_entity "${MIN_POST_ROUND_TRIPLES_PER_ENTITY}"
  --max_post_round_entities_per_triple "${MAX_POST_ROUND_ENTITIES_PER_TRIPLE}"
  --min_post_round_average_participation "${MIN_POST_ROUND_AVERAGE_PARTICIPATION}"
  --max_post_round_weak_component_count "${MAX_POST_ROUND_WEAK_COMPONENT_COUNT}"
  --min_post_round_largest_component_ratio "${MIN_POST_ROUND_LARGEST_COMPONENT_RATIO}"
  --stop_when_all_pattern_surpluses_zero
  --verbose
)

IFS=',' read -r -a PROTECTED_RELATION_ARRAY <<< "${PROTECTED_RELATIONS}"
for relation in "${PROTECTED_RELATION_ARRAY[@]}"; do
  relation="$(printf '%s' "${relation}" | xargs)"
  if [[ -n "${relation}" ]]; then
    PRUNER_ARGS+=(--protected_relation "${relation}")
  fi
done

IFS=',' read -r -a HARD_RELATION_MIN_COUNT_ARRAY <<< "${HARD_RELATION_MIN_COUNTS}"
for item in "${HARD_RELATION_MIN_COUNT_ARRAY[@]}"; do
  item="$(printf '%s' "${item}" | xargs)"
  if [[ -n "${item}" ]]; then
    PRUNER_ARGS+=(--hard_relation_min_count "${item}")
  fi
done

if [[ "${DISABLE_HARD_PRESERVE_LARGEST_COMPONENT}" == "1" ]]; then
  PRUNER_ARGS+=(--disable_hard_preserve_largest_component)
fi

if [[ "${DISABLE_HARD_PROTECT_PATTERNS_BELOW_TARGET}" == "1" ]]; then
  PRUNER_ARGS+=(--disable_hard_protect_patterns_below_target)
fi

if [[ "${HARD_GUARD_PROJECTED_TRIPLES_GT_ENTITIES}" == "1" ]]; then
  PRUNER_ARGS+=(--hard_guard_projected_triples_gt_entities)
fi

log "START stage13 balance prune revised density-aware"
log "PYTHON_BIN=${PYTHON_BIN}"
log "BASE_DIR=${BASE_DIR}"
log "PRUNE_DIR=${PRUNE_DIR}"
log "INPUT_GRAPH=${INPUT_GRAPH}"
log "ALLOCATION_MANIFEST=${ALLOCATION_MANIFEST}"
log "SELECTION_MODE=${SELECTION_MODE}"
log "MAX_ROUNDS=${MAX_ROUNDS}"
log "MAX_BATCH_REMOVALS=${MAX_BATCH_REMOVALS}"
log "MAX_TOTAL_REMOVALS=${MAX_TOTAL_REMOVALS}"
log "RELATION_OVERCAP_MODE=${RELATION_OVERCAP_MODE}"
log "TARGET_MIN_TRIPLES_PER_ENTITY=${TARGET_MIN_TRIPLES_PER_ENTITY}"
log "TARGET_MAX_ENTITIES_PER_TRIPLE=${TARGET_MAX_ENTITIES_PER_TRIPLE}"
log "TARGET_MIN_AVERAGE_PARTICIPATION=${TARGET_MIN_AVERAGE_PARTICIPATION}"
log "PROTECTED_RELATIONS=${PROTECTED_RELATIONS}"
log "HARD_RELATION_MIN_COUNTS=${HARD_RELATION_MIN_COUNTS}"
log "MAX_FRACTION_PER_RELATION_PER_ROUND=${MAX_FRACTION_PER_RELATION_PER_ROUND}"
log "MAX_REMOVALS_PER_RELATION_PER_ROUND=${MAX_REMOVALS_PER_RELATION_PER_ROUND}"
log "BATCH_GUARD_ACTION=${BATCH_GUARD_ACTION}"
log "MIN_POST_ROUND_TRIPLES_PER_ENTITY=${MIN_POST_ROUND_TRIPLES_PER_ENTITY}"
log "MAX_POST_ROUND_ENTITIES_PER_TRIPLE=${MAX_POST_ROUND_ENTITIES_PER_TRIPLE}"
log "MIN_POST_ROUND_AVERAGE_PARTICIPATION=${MIN_POST_ROUND_AVERAGE_PARTICIPATION}"
log "MAX_POST_ROUND_WEAK_COMPONENT_COUNT=${MAX_POST_ROUND_WEAK_COMPONENT_COUNT}"
log "MIN_POST_ROUND_LARGEST_COMPONENT_RATIO=${MIN_POST_ROUND_LARGEST_COMPONENT_RATIO}"

"${PYTHON_BIN}" -u "${PRUNER_PY}" "${PRUNER_ARGS[@]}"

log "DONE stage13 balance prune revised density-aware"

log "START pruned-graph CSV export"
"${PYTHON_BIN}" - <<PY
import csv
import json
from pathlib import Path

inp = Path(${PRUNED_GRAPH@Q})
out = Path(${PRUNED_GRAPH_CSV@Q})
out.parent.mkdir(parents=True, exist_ok=True)

with inp.open("r", encoding="utf-8") as f, out.open("w", encoding="utf-8", newline="") as g:
    writer = csv.DictWriter(g, fieldnames=["h", "r", "t"])
    writer.writeheader()
    for line in f:
        row = json.loads(line)
        writer.writerow({"h": row["h"], "r": row["r"], "t": row["t"]})
PY
log "DONE pruned-graph CSV export"

log "START pruned-graph pattern statistics"
"${PYTHON_BIN}" -u "${KG_PATTERN_STATS_PY}" \
  --kg_file "${PRUNED_GRAPH_CSV}" \
  --output_dir "${PRUNED_GRAPH_PATTERN_STATS_DIR}"
log "DONE pruned-graph pattern statistics"

log "START pruned-graph 2-path extraction"
"${PYTHON_BIN}" -u "${EXTRACT_2PATHS_PY}" \
  --kg_file "${PRUNED_GRAPH_CSV}" \
  --out_path "${PRUNED_GRAPH_2PATHS_CSV}"
log "DONE pruned-graph 2-path extraction"

log "START largest-component export"
"${PYTHON_BIN}" -u "${PLOT_PY}" \
  --triples_path "${PRUNED_GRAPH}" \
  --out_html "${LCC_HTML}" \
  --dim 3 \
  --largest_component \
  --export_triplets_path "${LCC_CSV}" \
  --export_triplets_format csv
log "DONE largest-component export"

log "START largest-component pattern statistics"
"${PYTHON_BIN}" -u "${KG_PATTERN_STATS_PY}" \
  --kg_file "${LCC_CSV}" \
  --output_dir "${LCC_PATTERN_STATS_DIR}"
log "DONE largest-component pattern statistics"

log "START largest-component 2-path extraction"
"${PYTHON_BIN}" -u "${EXTRACT_2PATHS_PY}" \
  --kg_file "${LCC_CSV}" \
  --out_path "${LCC_2PATHS_CSV}"
log "DONE largest-component 2-path extraction"

log "START pruned-branch allocation analysis"
"${PYTHON_BIN}" -u "${ANALYZE_PY}" \
  --graph_path "${PRUNED_GRAPH}" \
  --allocation_path "${ALLOCATION_MANIFEST}" \
  --out_dir "${PRUNED_BRANCH_ETA_DIR}"
log "DONE pruned-branch allocation analysis"

log "START pruned-branch 3D plot"
"${PYTHON_BIN}" -u "${PLOT_PY}" \
  --triples_path "${PRUNED_GRAPH}" \
  --out_html "${PRUNED_BRANCH_PLOT_HTML}" \
  --dim 3
log "DONE pruned-branch 3D plot"

log "START largest-component allocation analysis"
"${PYTHON_BIN}" -u "${ANALYZE_PY}" \
  --graph_path "${LCC_CSV}" \
  --allocation_path "${ALLOCATION_MANIFEST}" \
  --out_dir "${LCC_ETA_DIR}"
log "DONE largest-component allocation analysis"

log "DONE full stage13 revised density-aware pipeline"
