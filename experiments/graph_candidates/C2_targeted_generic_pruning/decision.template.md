# C2 Decision Template

Status: template only. C2 has not been generated.

Candidate root:

`experiments/graph_candidates/C2_targeted_generic_pruning/`

## Inputs

- Parent candidate ID: `B0`
- Parent graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Parent graph SHA256: `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`
- Allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Allocation SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`
- Config: `configs/graph_candidates/C2_targeted_generic_pruning.template.json`
- Command: `experiments/graph_candidates/C2_targeted_generic_pruning/command.template.sh`

## Outputs To Fill After Execution

- Candidate graph: `experiments/graph_candidates/C2_targeted_generic_pruning/outputs/pruned_graph.jsonl`
- Candidate graph SHA256: `<fill after evaluation>`
- Generation report: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json`
- Evaluator report: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`
- Evaluator summary: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.summary.md`

## Metrics To Fill From Evaluator

| Metric | Value |
| --- | ---: |
| Raw rows | `<fill>` |
| Unique triples | `<fill>` |
| Duplicate triples | `<fill>` |
| Unique relations | `<fill>` |
| Weak components | `<fill>` |
| Largest weak component ratio | `<fill>` |
| Allocated relations observed | `<fill>` |
| Zero allocated relations | `<fill>` |
| Total deficit | `<fill>` |
| Total surplus | `<fill>` |
| `P31` observed / surplus | `<fill>` |
| `P279` observed / surplus | `<fill>` |
| `P131` observed / surplus | `<fill>` |

## Accept Or Reject

Decision: `<accept / reject / exploratory only>`

Decision basis:

`<cite generation report, evaluator report, hashes, and comparison against B0/C1>`

Registry action:

`<append C2 row / do not append / append as rejected candidate>`

## Human Notes

`<record any thesis-facing interpretation or concerns here>`
