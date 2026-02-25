#!/bin/bash
#SBATCH --job-name=trial6_phase4_conn_sparql
#SBATCH --output=logs/trial6_phase4_connectedgraph_sparql_%j.out
#SBATCH --error=logs/trial6_phase4_connectedgraph_sparql_%j.err
#SBATCH --time=48:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G

set -euo pipefail

ROOT_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
cd "${ROOT_DIR}"

mkdir -p logs data/connectedgraph

# -------- Inputs --------
ALLOCATION_JSON="data/connectedgraph/bidirectional_allocation_results_backup.json"
PROPERTIES_JSON="data/raw/wikidata_ontology.properties.json"

# -------- Outputs (use SLURM-specific names to avoid collisions) --------
OUT_TRIPLES="data/connectedgraph/trial6_connected_allocation_sample.slurm.triples.jsonl"
OUT_META="data/connectedgraph/trial6_connected_allocation_sample.slurm.metadata.json"
CHECKPOINT_PATH="data/connectedgraph/trial6_phase4_connected_realization.slurm.checkpoint.json"

# -------- SPARQL / runtime settings --------
USER_AGENT="phase4-connected/1.0 (mailto:omar@ansary.com)"
ENDPOINT_URL="https://query.wikidata.org/sparql"

ATTEMPTS="1" #was 3
RCL_SIZE="10"
ANCHOR_FRACTION="0.2"
OVERLAP_PROBE="30" #was 200, reduced for testing to speed up
ANY_FETCH="120" #was 200, then 600
ATTACH_FETCH="120" #was 200, then 600
MAX_V_VALUES="40" #was 30,15
TIMEOUT_SEC="10" #was 30
RETRIES="1" #was 3
MAX_TYPE_VALUES="12"
SEED="42"
CHECKPOINT_EVERY="1"
MICRO_FILL_CHUNK_SIZE="20"
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
USE_RELAX_FLAG="" #was --use_controlled_relaxation
RESUME_FLAG="--resume_from_checkpoint"

echo "============================================================"
echo "Phase4 SPARQL Slurm Run"
echo "Job started: $(date)"
echo "Job ID: ${SLURM_JOB_ID}"
echo "Node: $(hostname)"
echo "Allocation: ${ALLOCATION_JSON}"
echo "Checkpoint: ${CHECKPOINT_PATH}"
echo "Output triples: ${OUT_TRIPLES}"
echo "Output metadata: ${OUT_META}"
echo "============================================================"

python src/kg_building/run_phase4_sparql_from_allocation.py \
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
  ${RESUME_FLAG}

echo "============================================================"
echo "Phase4 SPARQL Slurm completed: $(date)"
echo "============================================================"
