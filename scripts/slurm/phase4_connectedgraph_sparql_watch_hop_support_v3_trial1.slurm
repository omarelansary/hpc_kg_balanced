#!/bin/bash
#SBATCH --job-name=phase4_hop_v3_t1_resume
#SBATCH --output=logs/trial1_hop_v3_phase4_connectedgraph_sparql_watch_%j.out
#SBATCH --error=logs/trial1_hop_v3_phase4_connectedgraph_sparql_watch_%j.err
#SBATCH --time=168:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --mail-type=BEGIN,END,FAIL
#SBATCH --mail-user=omar_essameldeen_ahmad.elansary@mailbox.tu-dresden.de

set -euo pipefail

ROOT_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
cd "${ROOT_DIR}"
mkdir -p logs data/connectedgraph/hop_support_v3

# -------- Inputs --------
ALLOCATION_JSON="data/processed/hop_support_v3/bidirectional_allocation_results_hop_v3_patchedby_v2_allsup50_60sym_99anti_90inv_95comp.json"
PROPERTIES_JSON="data/raw/wikidata_ontology.properties.json"

# -------- Outputs --------
OUT_TRIPLES="data/connectedgraph/hop_support_v3/trial1_connected_allocation_sample.watch.triples.jsonl"
OUT_META="data/connectedgraph/hop_support_v3/trial1_connected_allocation_sample.watch.metadata.json"
# Resume from trial1 state (same checkpoint path).
CHECKPOINT_PATH="data/connectedgraph/hop_support_v3/trial1_phase4_connected_realization.checkpoint.json"

# -------- SPARQL / runtime settings --------
USER_AGENT="phase4-connected/1.0 (mailto:omaransary@gmail.com)"
ENDPOINT_URL="https://query.wikidata.org/sparql"

ATTEMPTS="1"
RCL_SIZE="10"
ANCHOR_FRACTION="0.2"
OVERLAP_PROBE="30"
ANY_FETCH="80"
ATTACH_FETCH="60"
MAX_V_VALUES="30"
TIMEOUT_SEC="60"
RETRIES="2"
MAX_TYPE_VALUES="12"
SEED="42"
CHECKPOINT_EVERY="1"
MICRO_FILL_CHUNK_SIZE="10"
STALL_MAX_ROUNDS="25"
MAX_FAIL_PER_RELATION="3"
SEED_MIN_ATTACHABLE_FRACTION="0.05"
SEED_EXPAND_ROUNDS="3"
SEED_EXPAND_RELATIONS="20"
SEED_EXPAND_TRIPLES_PER_RELATION="3"
BRIDGE_SEED_RELATIONS="15"
BRIDGE_SEED_TRIPLES_PER_RELATION="3"
BRIDGE_SEED_NEW_ENTITIES_TARGET="25"
CAPACITY_PROBE_ROUNDS="3"
ZERO_TRIPLE_FORCE_BOOTSTRAP_ROUNDS="5"

# -------- Feature toggles --------
NON_STRICT_FLAG="--non_strict"
USE_BACKBONE_FLAG="--use_backbone_seed"
USE_RELAX_FLAG="--use_controlled_relaxation"
RESUME_FLAG="--resume_from_checkpoint"

# -------- Monitoring --------
MONITOR_INTERVAL_SEC=60

echo "============================================================"
echo "Phase4 SPARQL Slurm Run (trial1 resume)"
echo "Job started: $(date)"
echo "Job ID: ${SLURM_JOB_ID}"
echo "Node: $(hostname)"
echo "Allocation: ${ALLOCATION_JSON}"
echo "Checkpoint (resume): ${CHECKPOINT_PATH}"
echo "Output triples: ${OUT_TRIPLES}"
echo "Output metadata: ${OUT_META}"
echo "============================================================"

PYTHONUNBUFFERED=1 python -u src/kg_building/run_phase4_sparql_from_allocation.py \
  --allocation_json "${ALLOCATION_JSON}" \
  --properties_json "${PROPERTIES_JSON}" \
  --output_triples "${OUT_TRIPLES}" \
  --output_metadata "${OUT_META}" \
  --checkpoint_path "${CHECKPOINT_PATH}" \
  --endpoint_url "${ENDPOINT_URL}" \
  --user_agent "${USER_AGENT}" \
  --any_fetch "${ANY_FETCH}" \
  --attach_fetch "${ATTACH_FETCH}" \
  --max_v_for_values "${MAX_V_VALUES}" \
  --timeout_sec "${TIMEOUT_SEC}" \
  --retries "${RETRIES}" \
  --max_type_values "${MAX_TYPE_VALUES}" \
  --attempts "${ATTEMPTS}" \
  --rcl_size "${RCL_SIZE}" \
  --anchor_fraction "${ANCHOR_FRACTION}" \
  --overlap_probe_triples "${OVERLAP_PROBE}" \
  --seed "${SEED}" \
  --checkpoint_every_relations "${CHECKPOINT_EVERY}" \
  --micro_fill_chunk_size "${MICRO_FILL_CHUNK_SIZE}" \
  --stall_max_rounds "${STALL_MAX_ROUNDS}" \
  --max_fail_per_relation "${MAX_FAIL_PER_RELATION}" \
  --seed_min_attachable_fraction "${SEED_MIN_ATTACHABLE_FRACTION}" \
  --seed_expand_rounds "${SEED_EXPAND_ROUNDS}" \
  --seed_expand_relations "${SEED_EXPAND_RELATIONS}" \
  --seed_expand_triples_per_relation "${SEED_EXPAND_TRIPLES_PER_RELATION}" \
  --bridge_seed_relations "${BRIDGE_SEED_RELATIONS}" \
  --bridge_seed_triples_per_relation "${BRIDGE_SEED_TRIPLES_PER_RELATION}" \
  --bridge_seed_new_entities_target "${BRIDGE_SEED_NEW_ENTITIES_TARGET}" \
  --capacity_probe_rounds "${CAPACITY_PROBE_ROUNDS}" \
  --zero_triple_force_bootstrap_rounds "${ZERO_TRIPLE_FORCE_BOOTSTRAP_ROUNDS}" \
  ${NON_STRICT_FLAG} \
  ${USE_BACKBONE_FLAG} \
  ${USE_RELAX_FLAG} \
  ${RESUME_FLAG} &

RUN_PID=$!
echo "[watch] worker PID=${RUN_PID}"

while kill -0 "${RUN_PID}" 2>/dev/null; do
  if [[ -f "${CHECKPOINT_PATH}" ]]; then
    python - <<'PY' "${CHECKPOINT_PATH}"
import json,sys,time
p=sys.argv[1]
try:
    d=json.load(open(p,'r',encoding='utf-8'))
    status=d.get('status')
    attempt=d.get('attempt')
    triples_out=len(d.get('triples_out',[])) if isinstance(d.get('triples_out'),list) else None
    remaining=len(d.get('remaining',{})) if isinstance(d.get('remaining'),dict) else None
    triples=len(d.get('triples',[])) if isinstance(d.get('triples'),list) else None
    print(f"[watch] {time.strftime('%Y-%m-%d %H:%M:%S')} status={status} attempt={attempt} triples_out={triples_out} triples={triples} remaining={remaining}", flush=True)
except Exception as e:
    print(f"[watch] checkpoint read error: {e}", flush=True)
PY
  else
    echo "[watch] $(date '+%Y-%m-%d %H:%M:%S') checkpoint not found: ${CHECKPOINT_PATH}"
  fi
  sleep "${MONITOR_INTERVAL_SEC}"
done

wait "${RUN_PID}"
RC=$?

echo "============================================================"
echo "Phase4 SPARQL Slurm completed: $(date)"
echo "Exit code: ${RC}"
echo "============================================================"
exit "${RC}"

