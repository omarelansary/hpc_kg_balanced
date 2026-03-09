#!/bin/bash
#SBATCH --job-name=hop_v3_ip_smoke
#SBATCH --output=logs/hop_v3_ip_smoke_%A_%a.out
#SBATCH --error=logs/hop_v3_ip_smoke_%A_%a.err
#SBATCH --time=00:10:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=512M
# Optional: override at submit time
#SBATCH --array=0-1

set -euo pipefail

# ------------------------------------------------------------
# Smoke test: shard-aware IP probe for hop_support_v3 sharding.
# Uses the same shard indexing + input path pattern as:
#   scripts/slurm/hop_support_v3_sharded.slurm
# ------------------------------------------------------------

WORK_DIR="/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced"

NUM_SHARDS="${NUM_SHARDS:-${SLURM_ARRAY_TASK_COUNT:-1}}"
SHARD_INDEX="${SHARD_INDEX:-${SLURM_ARRAY_TASK_ID:-0}}"
SHARD_INPUT_DIR="${SHARD_INPUT_DIR:-${WORK_DIR}/data/processed/shards}"
SHARD_INPUT_PREFIX="${SHARD_INPUT_PREFIX:-hop_support_v3_input}"
RUN_TAG="${RUN_TAG:-hop_support_v3_ip_smoke}"
REQUIRE_SHARD_INPUT="${REQUIRE_SHARD_INPUT:-0}"

OUTPUT_DIR="${OUTPUT_DIR:-${WORK_DIR}/data/processed/shards/${RUN_TAG}}"
mkdir -p "${WORK_DIR}/logs" "${OUTPUT_DIR}"

SHARD_WIDTH="${#NUM_SHARDS}"
if (( SHARD_WIDTH < 2 )); then
  SHARD_WIDTH=2
fi
printf -v SHARD_ID "%0${SHARD_WIDTH}d" "${SHARD_INDEX}"
printf -v SHARD_N "%0${SHARD_WIDTH}d" "${NUM_SHARDS}"

INPUT="${SHARD_INPUT_DIR}/${SHARD_INPUT_PREFIX}.s${SHARD_ID}of${SHARD_N}.jsonl"
REPORT_JSON="${OUTPUT_DIR}/ip_report.s${SHARD_ID}of${SHARD_N}.json"

echo "============================================================"
echo "IP smoke started: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-N/A} ArrayTask: ${SLURM_ARRAY_TASK_ID:-N/A}"
echo "Node: ${SLURMD_NODENAME:-N/A}"
echo "Shard: index=${SHARD_INDEX} num_shards=${NUM_SHARDS}"
echo "Expected shard input: ${INPUT}"
echo "Require shard input: ${REQUIRE_SHARD_INPUT}"
echo "Report JSON: ${REPORT_JSON}"
echo "============================================================"

INPUT_EXISTS=0
if [[ -f "${INPUT}" ]]; then
  INPUT_EXISTS=1
else
  if [[ "${REQUIRE_SHARD_INPUT}" == "1" ]]; then
    echo "ERROR: shard input not found: ${INPUT}"
    exit 1
  fi
  echo "WARNING: shard input not found (smoke mode continues): ${INPUT}"
fi

HOSTNAME_SHORT="$(hostname -s 2>/dev/null || hostname)"
HOSTNAME_FQDN="$(hostname -f 2>/dev/null || true)"
NODE_NAME="${SLURMD_NODENAME:-${HOSTNAME_SHORT}}"
LOCAL_IPS="$(hostname -I 2>/dev/null | xargs || true)"
if [[ -z "${LOCAL_IPS}" ]]; then
  LOCAL_IPS="$(ip -o -4 addr show scope global 2>/dev/null | awk '{print $4}' | paste -sd ' ' - || true)"
fi
PRIMARY_SRC_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '/src/ {for (i=1; i<=NF; i++) if ($i==\"src\") {print $(i+1); exit}}' || true)"

EGRESS_IP=""
EGRESS_IP_SOURCE=""
for EP in "https://api.ipify.org" "https://ifconfig.me/ip" "https://ipinfo.io/ip"; do
  VAL="$(curl -fsS --max-time 8 "${EP}" 2>/dev/null | tr -d '\r\n' | xargs || true)"
  if [[ -n "${VAL}" ]]; then
    EGRESS_IP="${VAL}"
    EGRESS_IP_SOURCE="${EP}"
    break
  fi
done
if [[ -z "${EGRESS_IP}" ]]; then
  EGRESS_IP="UNAVAILABLE"
  EGRESS_IP_SOURCE="none"
fi

echo "Local hostname: ${HOSTNAME_SHORT}"
echo "Local FQDN: ${HOSTNAME_FQDN:-N/A}"
echo "Node name: ${NODE_NAME}"
echo "Local IPs: ${LOCAL_IPS:-N/A}"
echo "Primary src IP: ${PRIMARY_SRC_IP:-N/A}"
echo "Egress IP: ${EGRESS_IP} (source=${EGRESS_IP_SOURCE})"

export WORK_DIR NUM_SHARDS SHARD_INDEX SHARD_ID SHARD_N INPUT REPORT_JSON
export REQUIRE_SHARD_INPUT INPUT_EXISTS
export HOSTNAME_SHORT HOSTNAME_FQDN NODE_NAME LOCAL_IPS PRIMARY_SRC_IP EGRESS_IP EGRESS_IP_SOURCE
export SLURM_JOB_ID="${SLURM_JOB_ID:-N/A}"
export SLURM_ARRAY_TASK_ID="${SLURM_ARRAY_TASK_ID:-N/A}"

python - <<'PY'
import json
import os
import time

payload = {
    "timestamp_unix": time.time(),
    "work_dir": os.environ.get("WORK_DIR"),
    "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
    "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
    "num_shards": int(os.environ.get("NUM_SHARDS", "1")),
    "shard_index": int(os.environ.get("SHARD_INDEX", "0")),
    "shard_label": f"s{os.environ.get('SHARD_ID')}of{os.environ.get('SHARD_N')}",
    "input": os.environ.get("INPUT"),
    "require_shard_input": os.environ.get("REQUIRE_SHARD_INPUT"),
    "input_exists": int(os.environ.get("INPUT_EXISTS", "0")),
    "node_name": os.environ.get("NODE_NAME"),
    "hostname_short": os.environ.get("HOSTNAME_SHORT"),
    "hostname_fqdn": os.environ.get("HOSTNAME_FQDN"),
    "local_ips": os.environ.get("LOCAL_IPS"),
    "primary_src_ip": os.environ.get("PRIMARY_SRC_IP"),
    "egress_ip": os.environ.get("EGRESS_IP"),
    "egress_ip_source": os.environ.get("EGRESS_IP_SOURCE"),
}

report_json = os.environ["REPORT_JSON"]
with open(report_json, "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)
print(f"wrote_report: {report_json}")
PY

echo "============================================================"
echo "IP smoke finished: $(date)"
echo "============================================================"
