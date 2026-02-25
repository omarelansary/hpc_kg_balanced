#!/bin/bash
#SBATCH --job-name=build_inverse_alias_topk
#SBATCH --output=logs/build_inverse_alias_topk_%j.out
#SBATCH --error=logs/build_inverse_alias_topk_%j.err
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G

set -euo pipefail

WORK_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"
SCRIPT="${WORK_DIR}/src/build_inverse_alias_topk.py"

RELATION_PROFILES_PATH="${WORK_DIR}/data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json"
ALIASES_JSON_PATH="${WORK_DIR}/data/raw/wikidata_ontology.property_aliases.json"
LABEL_EMBEDDINGS_JSON_PATH="${WORK_DIR}/data/raw/wikidata_ontology.properties_label_embeddings.json"
OUTPUT_PATH="${WORK_DIR}/data/processed/wikidata_ontology.inverse_mode_aliases_topk.json"

K=5
LABEL_SIM_WEIGHT=0.35

echo "============================================================"
echo "Job started: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-N/A}"
echo "Node: ${SLURMD_NODENAME:-N/A}"
echo "Work dir: ${WORK_DIR}"
echo "============================================================"

cd "${WORK_DIR}"
mkdir -p "${WORK_DIR}/logs"

if [[ -f "${WORK_DIR}/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "${WORK_DIR}/.venv/bin/activate"
fi

echo "Python: $(which python)"
python --version
echo "Output: ${OUTPUT_PATH}"
echo ""

python "${SCRIPT}" \
  --relation_profiles_path "${RELATION_PROFILES_PATH}" \
  --aliases_json_path "${ALIASES_JSON_PATH}" \
  --label_embeddings_json_path "${LABEL_EMBEDDINGS_JSON_PATH}" \
  --output_path "${OUTPUT_PATH}" \
  --k "${K}" \
  --label_similarity_weight "${LABEL_SIM_WEIGHT}"

EXIT_CODE=$?

echo ""
echo "============================================================"
echo "Job finished: $(date)"
echo "Exit code: ${EXIT_CODE}"
echo "============================================================"

exit ${EXIT_CODE}
