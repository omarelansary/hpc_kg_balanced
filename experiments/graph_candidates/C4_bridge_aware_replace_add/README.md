# C4_bridge_aware_replace_add

Label: Bridge-aware replace/add experiment

Strategy: `bridge_aware_remove_replace_controlled_addition`

Status: `planned_not_generated`

This scaffold does not generate a graph. It only creates the standard directory layout and metadata template for a future graph-candidate experiment.

## Directory Layout

- `outputs/`: place the future candidate graph here, usually `outputs/graph.jsonl`.
- `reports/`: evaluator report package output.
- `logs/`: command logs for future generation/evaluation runs.
- `configs/`: run-specific config files.
- `manifest.template.json`: planned candidate metadata.
- `decision.md`: write after evaluation and human review.

## Evaluation Command After Graph Exists

Run from this experiment directory after `outputs/graph.jsonl` exists. Adjust the relative script path if the experiment root is nested differently from `experiments/graph_candidates/<candidate-id>/`:

```bash
python ../../../scripts/graph_candidates/evaluate_candidate.py --candidate-id C4_bridge_aware_replace_add --label "Bridge-aware replace/add experiment" --graph "outputs/graph.jsonl" --allocation "../../../src/Pruning graph/bidirectional_allocation_results5k.json" --out-dir reports --force --parent-candidate-id B0
```

## Decision Step

After evaluation, write `decision.md` with the candidate status, accepted/rejected decision, metrics, limitations, and evidence paths.

## Registry Step

Do not update the candidate registry until a graph exists, reports exist, and a human decision has been recorded.
