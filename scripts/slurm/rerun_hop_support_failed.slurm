#!/bin/bash
#SBATCH --job-name=hop_support_rerun_failed
#SBATCH --output=logs/hop_support_rerun_failed_%j.out
#SBATCH --error=logs/hop_support_rerun_failed_%j.err
#SBATCH --time=24:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G

set -euo pipefail

cd /data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced
mkdir -p logs data/processed

# Activate venv if present
if [ -f .venv/bin/activate ]; then
  source .venv/bin/activate
fi

# Conservative rerun settings to minimize WDQS timeouts
python src/hop_support.py \
  --input data/processed/hop_discovery_failed_only.jsonl \
  --output_jsonl data/processed/hop_support_failed_rerun.jsonl \
  --checkpoint data/processed/hop_support_failed_rerun_checkpoint.json \
  --user_agent "hop_support/1.0 (mailto:omar@gmail.com)" \
  --workers 4 \
  --qps 0.05 \
  --max_inflight 1 \
  --chunk_size 5 \
  --topk 50 \
  --sampled_t_limit 5000 \
  --timeout_sec 180 \
  --max_retries 4 \
  --backoff_base_sec 5 \
  --backoff_cap_sec 300 \
  --log_level INFO
