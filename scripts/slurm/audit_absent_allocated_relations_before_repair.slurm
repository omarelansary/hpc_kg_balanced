#!/bin/bash
#SBATCH --job-name=audit_absent_rel_t9_before
#SBATCH --output=logs/audit_absent_rel_t9_before_%j.out
#SBATCH --error=logs/audit_absent_rel_t9_before_%j.err
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
GRAPH_TRIPLES="data/connectedgraph/trial9/relation_audit_before_repair/filtered_by_allocation/all_trial9_unique_triplets.filtered_by_allocation.json"
RELATION_AUDIT_JSON="data/connectedgraph/trial9/relation_audit_before_repair/filtered_by_allocation/relation_audit_report.json"
VALID_TYPES_JSON="data/raw/wikidata_ontology.properties.json"

# -------- Output --------
OUTPUT_DIR="data/connectedgraph/trial9/absent_allocated_relation_before_repair_filtered"

# -------- WDQS settings --------
USER_AGENT="absent-allocated-audit/1.0 (mailto:omaransary@gmail.com)"
TIMEOUT_SEC="60"
QUERY_LIMIT="200"

# -------- Run control --------
# Set to 1 to resume an interrupted run in OUTPUT_DIR.
RESUME=0
RESUME_FLAG=""
if [[ "${RESUME}" == "1" ]]; then
  RESUME_FLAG="--resume"
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
echo "Resume: ${RESUME}"
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
