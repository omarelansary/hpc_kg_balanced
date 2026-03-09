#!/bin/bash
#SBATCH --job-name=repair_apply_top100
#SBATCH --output=logs/repair_apply_top100_%j.out
#SBATCH --error=logs/repair_apply_top100_%j.err
#SBATCH --time=168:00:00
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G

set -euo pipefail

cd "${SLURM_SUBMIT_DIR:-$PWD}"
mkdir -p logs

source .venv/bin/activate

# python src/kg_building/repair_kg_connectivity.py \
#   --input_triples data/connectedgraph/trial9/all_trial9_unique_triplets.triplets.json \
#   --relation_scope_manifest data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json \
#   --output_dir data/connectedgraph/trial9/repair_apply_top20 \
#   --collect_noncore \
#   --max_components 20 \
#   --anchor_nodes_per_component 5 \
#   --query_limit 200 \
#   --timeout_sec 60 \
#   --wikidata_sleep_sec 0.2 \
#   --user_agent "kg-repair/1.0 (mailto:omaransary@gmail.com)"

python src/kg_building/repair_kg_connectivity.py \
  --input_triples data/connectedgraph/trial9/all_trial9_unique_triplets.triplets.json \
  --relation_scope_manifest data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json \
  --output_dir data/connectedgraph/trial9/repair_apply_top100 \
  --collect_noncore \
  --max_components 100 \
  --anchor_nodes_per_component 5 \
  --query_limit 200 \
  --timeout_sec 60 \
  --wikidata_sleep_sec 0.2 \
  --user_agent "kg-repair/1.0 (mailto:omaransary@gmail.com)"