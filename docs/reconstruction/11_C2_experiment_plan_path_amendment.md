# C2 Experiment Plan Path Amendment

This amendment updates only the future output location in `docs/reconstruction/11_C2_experiment_plan.md`.

## Amendment

The original C2 design remains valid.

The future output location is changed from:

`data/connectedgraph/candidates/C2_targeted_generic_dominance/`

to:

`experiments/graph_candidates/C2_targeted_generic_pruning/`

Reason:

`data/connectedgraph/` is historical artifact space. New controlled graph-candidate experiments should use `experiments/graph_candidates/` as the operational layer for manifests, templates, reports, and future outputs.

C2 still does not exist as a generated graph. No C2 pruning has been run, no C2 graph has been created, and `docs/reconstruction/graph_candidates.tsv` has not been updated for C2.

## Updated Future C2 Paths

| Role | Path |
| --- | --- |
| Candidate root | `experiments/graph_candidates/C2_targeted_generic_pruning/` |
| Future candidate graph | `experiments/graph_candidates/C2_targeted_generic_pruning/outputs/pruned_graph.jsonl` |
| Future generation report | `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json` |
| Future evaluator report | `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json` |
| Future evaluator summary | `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.summary.md` |
| Future config | `configs/graph_candidates/C2_targeted_generic_pruning.template.json` |
| Future command | `experiments/graph_candidates/C2_targeted_generic_pruning/command.template.sh` |

## Operational Rule

Existing graph and allocation paths remain provenance references. They must not be moved or copied into the new operational layer unless a later human decision explicitly authorizes a controlled archival copy.
