#!/usr/bin/env bash
set -euo pipefail

# Template only. Do not run until C2 generation is explicitly authorized.
# This command uses the isolated generator script:
# tools/graph_candidate_generation/targeted_generic_dominance_prune.py
# If the generator writes a graph that fails minimum thresholds, it still exits
# 0 so the standard evaluator below can write its report. Pre-generation
# failures still exit nonzero and stop this template under set -e.

GENERATOR="tools/graph_candidate_generation/targeted_generic_dominance_prune.py"
CONFIG="configs/graph_candidates/C2_targeted_generic_pruning.run.json"
INPUT_GRAPH="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv"
ALLOCATION="src/Pruning graph/bidirectional_allocation_results5k.json"
OUTPUT_GRAPH="experiments/graph_candidates/C2_targeted_generic_pruning/outputs/pruned_graph.jsonl"
GENERATION_REPORT="experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json"
EVALUATOR_REPORT="experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json"
EVALUATOR_SUMMARY="experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.summary.md"

if [[ ! -f "$GENERATOR" ]]; then
  echo "C2 generator not found at expected path: $GENERATOR" >&2
  echo "Check the generator path before running this template." >&2
  exit 2
fi

python "$GENERATOR" \
  --config "$CONFIG" \
  --input-graph "$INPUT_GRAPH" \
  --allocation "$ALLOCATION" \
  --output-graph "$OUTPUT_GRAPH" \
  --output-report "$GENERATION_REPORT" \
  --parent-candidate-id B0 \
  --parent-graph-sha256 c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9 \
  --allocation-sha256 a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb \
  --target-relation P31 \
  --target-relation P279 \
  --target-relation P131 \
  --max-removals 600 \
  --batch-size 1 \
  --require-weak-components 1 \
  --require-largest-ratio 1.0 \
  --min-allocated-relations-observed 139 \
  --max-zero-allocated-relations 0 \
  --max-total-deficit 2359 \
  --max-final-surplus 6581 \
  --require-duplicate-count 0

python tools/graph_candidate_evaluation/evaluate_graph_candidate.py \
  --candidate-id C2 \
  --label targeted_generic_pruning_from_B0 \
  --graph "$OUTPUT_GRAPH" \
  --allocation "$ALLOCATION" \
  --output-report "$EVALUATOR_REPORT" \
  --output-summary "$EVALUATOR_SUMMARY"

echo "Review $GENERATION_REPORT and $EVALUATOR_REPORT before adding any C2 registry row."
