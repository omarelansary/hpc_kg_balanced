#!/bin/bash
#SBATCH --job-name=repair_rel_alloc_abs
#SBATCH --output=logs/repair_rel_alloc_abs_%j.out
#SBATCH --error=logs/repair_rel_alloc_abs_%j.err
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

# -----------------------------
# Inputs (override via env vars)
# -----------------------------
GRAPH_JSONL="${GRAPH_JSONL:-data/connectedgraph/trial9/repair_apply_top100/graph_output.jsonl}"
HOP_SUPPORT_JSONL="${HOP_SUPPORT_JSONL:-data/archived/hop_support_v2_w_failed_statuses.wikibase_item_only_before_target_enrichment.jsonl}"
ALLOCATION_JSON="${ALLOCATION_JSON:-data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json}"
ABSENT_STATE_JSON="${ABSENT_STATE_JSON:-data/connectedgraph/trial9/absent_allocated_relation_before_repair_filtered/state.json}"

OUT_DIR="${OUT_DIR:-data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected}"
mkdir -p "${OUT_DIR}"

MISSING_RELATIONS_FILE="${MISSING_RELATIONS_FILE:-${OUT_DIR}/runtime_missing_relations.txt}"
PRIORITIES_FILE="${PRIORITIES_FILE:-${OUT_DIR}/runtime_priorities.jsonl}"
CHECKPOINT_PATH="${CHECKPOINT_PATH:-${OUT_DIR}/repair_checkpoint.json}"

USER_AGENT="${USER_AGENT:-kg-repair/1.0 (mailto:omar_ansary@gmail.com)}"

# -----------------------------
# Runtime knobs (env-overridable)
# -----------------------------
PRIORITY_FIELD="${PRIORITY_FIELD:-eta_expected}"
ALLOCATION_ETA_FIELD="${ALLOCATION_ETA_FIELD:-eta_expected}"
ALLOCATION_ETA_ROUNDING="${ALLOCATION_ETA_ROUNDING:-ceil}"
TOP_PAIR_CANDIDATES="${TOP_PAIR_CANDIDATES:-3}"
MAX_RECONSIDER_PASSES="${MAX_RECONSIDER_PASSES:-0}"
MAX_ACCEPTS_PER_ANCHOR="${MAX_ACCEPTS_PER_ANCHOR:-2}"
VALUES_CHUNK_SIZE="${VALUES_CHUNK_SIZE:-50}"
QUERY_LIMIT="${QUERY_LIMIT:-200}"
TIMEOUT_SEC="${TIMEOUT_SEC:-120}"
MAX_RETRIES="${MAX_RETRIES:-2}"
MIN_DELAY_SEC="${MIN_DELAY_SEC:-1.0}"
GIANT_COMPONENT_BONUS="${GIANT_COMPONENT_BONUS:-1.25}"
TYPE_BONUS="${TYPE_BONUS:-1.10}"
RANDOM_SEED="${RANDOM_SEED:-13}"
CHECKPOINT_EVERY="${CHECKPOINT_EVERY:-1}"
DRY_RUN="${DRY_RUN:-0}"
VERBOSE="${VERBOSE:-1}"
REBUILD_RUNTIME_INPUTS="${REBUILD_RUNTIME_INPUTS:-1}"

# Optional type-filter files
CONSTRAINTS_JSON="${CONSTRAINTS_JSON:-}"
ENTITY_TYPES_JSON="${ENTITY_TYPES_JSON:-}"
ENABLE_TYPE_FILTER="${ENABLE_TYPE_FILTER:-0}"

# Optional realized relation whitelist
REALIZED_RELATIONS="${REALIZED_RELATIONS:-}"

for required_file in "${GRAPH_JSONL}" "${HOP_SUPPORT_JSONL}" "${ALLOCATION_JSON}" "${ABSENT_STATE_JSON}"; do
  if [[ ! -f "${required_file}" ]]; then
    echo "Missing required input: ${required_file}" >&2
    exit 1
  fi
done

# ----------------------------------------------------------
# Build runtime inputs:
# 1) priorities JSONL (max eta per relation)
# 2) missing relations txt (from audit state target_relations)
# ----------------------------------------------------------
if [[ "${REBUILD_RUNTIME_INPUTS}" == "1" || ! -s "${PRIORITIES_FILE}" || ! -s "${MISSING_RELATIONS_FILE}" ]]; then
  python - <<PY
import json
from pathlib import Path

allocation_path = Path("${ALLOCATION_JSON}")
state_path = Path("${ABSENT_STATE_JSON}")
priorities_path = Path("${PRIORITIES_FILE}")
missing_path = Path("${MISSING_RELATIONS_FILE}")

allocation_obj = json.loads(allocation_path.read_text(encoding="utf-8"))
state_obj = json.loads(state_path.read_text(encoding="utf-8"))

rows = allocation_obj.get("allocations", [])
if not isinstance(rows, list):
    raise ValueError("allocation JSON must contain list field 'allocations'")

max_eta_expected = {}
max_eta_integer = {}
for row in rows:
    if not isinstance(row, dict):
        continue
    rel = row.get("relation")
    if not isinstance(rel, str) or not rel:
        continue
    eta_expected = row.get("eta_expected")
    eta_integer = row.get("eta_integer")
    if isinstance(eta_expected, (int, float)):
        prev = max_eta_expected.get(rel)
        if prev is None or float(eta_expected) > prev:
            max_eta_expected[rel] = float(eta_expected)
    if isinstance(eta_integer, (int, float)):
        prev_i = max_eta_integer.get(rel)
        if prev_i is None or float(eta_integer) > prev_i:
            max_eta_integer[rel] = float(eta_integer)

priorities_path.parent.mkdir(parents=True, exist_ok=True)
with priorities_path.open("w", encoding="utf-8") as f:
    for rel in sorted(set(max_eta_expected) | set(max_eta_integer)):
        obj = {"relation": rel}
        if rel in max_eta_expected:
            obj["eta_expected"] = max_eta_expected[rel]
        if rel in max_eta_integer:
            obj["eta_integer"] = max_eta_integer[rel]
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

target_relations = state_obj.get("target_relations", [])
if not isinstance(target_relations, list):
    raise ValueError("state JSON must contain list field 'target_relations'")

missing = sorted({x for x in target_relations if isinstance(x, str) and x})
missing_path.parent.mkdir(parents=True, exist_ok=True)
missing_path.write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")

print(f"Prepared priorities rows: {len(max_eta_expected)}")
print(f"Prepared missing relations: {len(missing)}")
PY
fi

CMD=(
  python -u src/kg_building/repair_relation_allocated_absence.py
  --graph_jsonl "${GRAPH_JSONL}"
  --hop_support_jsonl "${HOP_SUPPORT_JSONL}"
  --priorities "${PRIORITIES_FILE}"
  --missing_relations "${MISSING_RELATIONS_FILE}"
  --priority_field "${PRIORITY_FIELD}"
  --allocation_results_json "${ALLOCATION_JSON}"
  --allocation_eta_field "${ALLOCATION_ETA_FIELD}"
  --allocation_eta_rounding "${ALLOCATION_ETA_ROUNDING}"
  --top_pair_candidates_per_missing_relation "${TOP_PAIR_CANDIDATES}"
  --max_reconsider_passes "${MAX_RECONSIDER_PASSES}"
  --max_accepts_per_missing_relation 1
  --max_accepts_per_anchor "${MAX_ACCEPTS_PER_ANCHOR}"
  --values_chunk_size "${VALUES_CHUNK_SIZE}"
  --query_limit "${QUERY_LIMIT}"
  --user_agent "${USER_AGENT}"
  --timeout_sec "${TIMEOUT_SEC}"
  --max_retries "${MAX_RETRIES}"
  --min_delay_sec "${MIN_DELAY_SEC}"
  --giant_component_bonus "${GIANT_COMPONENT_BONUS}"
  --type_bonus "${TYPE_BONUS}"
  --out_dir "${OUT_DIR}"
  --checkpoint_path "${CHECKPOINT_PATH}"
  --checkpoint_every "${CHECKPOINT_EVERY}"
  --checkpoint_every_accept
  --resume
  --random_seed "${RANDOM_SEED}"
)

if [[ -n "${REALIZED_RELATIONS}" ]]; then
  CMD+=(--realized_relations "${REALIZED_RELATIONS}")
fi

if [[ "${ENABLE_TYPE_FILTER}" == "1" ]]; then
  if [[ -z "${CONSTRAINTS_JSON}" || -z "${ENTITY_TYPES_JSON}" ]]; then
    echo "ENABLE_TYPE_FILTER=1 requires CONSTRAINTS_JSON and ENTITY_TYPES_JSON" >&2
    exit 1
  fi
  CMD+=(--constraints_json "${CONSTRAINTS_JSON}" --entity_types_json "${ENTITY_TYPES_JSON}" --enable_type_filter)
fi

if [[ "${DRY_RUN}" == "1" ]]; then
  CMD+=(--dry_run)
fi

if [[ "${VERBOSE}" == "1" ]]; then
  CMD+=(--verbose)
fi

echo "Running command:"
printf ' %q' "${CMD[@]}"
echo

PYTHONUNBUFFERED=1 "${CMD[@]}"
