#!/bin/bash
#SBATCH --job-name=audit_absent_rel_t9
#SBATCH --output=logs/audit_absent_rel_t9_%j.out
#SBATCH --error=logs/audit_absent_rel_t9_%j.err
#SBATCH --time=48:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G

set -euo pipefail

ROOT_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
cd "${ROOT_DIR}"
mkdir -p logs

source .venv/bin/activate

# -------- Inputs --------
GRAPH_TRIPLES="data/connectedgraph/trial9/repair_apply_top100/graph_output.jsonl"
RELATION_AUDIT_JSON="data/connectedgraph/trial9/relation_audit_before_repair/filtered_by_allocation/relation_audit_report.json"
VALID_TYPES_JSON="data/raw/wikidata_ontology.properties.json"

# -------- Output --------
OUTPUT_DIR="data/connectedgraph/trial9/absent_allocated_relation_audit_top100"

# -------- WDQS settings --------
USER_AGENT="absent-allocated-audit/1.0 (mailto:omaransary@gmail.com)"
TIMEOUT_SEC="60"
QUERY_LIMIT="200"

# -------- Run control --------
# RESUME_MODE:
#   auto  -> resume if OUTPUT_DIR already has manifest/state
#   always -> always pass --resume
#   never -> never pass --resume
RESUME_MODE="auto"
RESUME_FLAG=""
if [[ "${RESUME_MODE}" == "always" ]]; then
  RESUME_FLAG="--resume"
elif [[ "${RESUME_MODE}" == "auto" ]]; then
  if [[ -f "${OUTPUT_DIR}/manifest.json" && -f "${OUTPUT_DIR}/state.json" ]]; then
    RESUME_FLAG="--resume"
  fi
fi

echo "============================================================"
echo "Absent allocated relation audit"
echo "Job started: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-N/A}"
echo "Node: $(hostname)"
echo "Graph triples: ${GRAPH_TRIPLES}"
echo "Relation audit: ${RELATION_AUDIT_JSON}"
echo "Valid types: ${VALID_TYPES_JSON}"
echo "Output dir: ${OUTPUT_DIR}"
echo "Resume mode: ${RESUME_MODE}"
echo "Resume flag: ${RESUME_FLAG:-<none>}"
echo "============================================================"

PYTHONUNBUFFERED=1 python -u src/statistics/audit_absent_allocated_relations.py \
  --graph_triples "${GRAPH_TRIPLES}" \
  --relation_audit_json "${RELATION_AUDIT_JSON}" \
  --valid_types_json "${VALID_TYPES_JSON}" \
  --output_dir "${OUTPUT_DIR}" \
  --user_agent "${USER_AGENT}" \
  --timeout_sec "${TIMEOUT_SEC}" \
  --query_limit "${QUERY_LIMIT}" \
  ${RESUME_FLAG}

echo "============================================================"
echo "Audit completed: $(date)"
echo "============================================================"
