# C2 Result Interpretation

C2 was generated as a controlled candidate, but it is rejected as a final graph and kept as exploratory negative evidence.

## Evidence

- C2 graph: `experiments/graph_candidates/C2_targeted_generic_pruning/outputs/pruned_graph.jsonl`
- C2 generation report: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json`
- C2 evaluator report: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`
- C2 decision: `experiments/graph_candidates/C2_targeted_generic_pruning/decision.md`

## Structural Result

C2 preserved the hard structural constraints used for graph-candidate tracking.

| Metric | C2 value |
| --- | ---: |
| Weak components | 1 |
| Largest weak component ratio | 1.0 |
| Duplicate triples | 0 |
| Unique relations | 139 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total deficit | 2019 |

Evidence: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`

## Balance Result

C2 failed the minimum surplus threshold.

| Candidate | Total surplus |
| --- | ---: |
| B0 | 6702 |
| C1 | 6582 |
| C2 | 6675 |

C2 improved B0 surplus by only 27. It did not beat C1 surplus.

Minimum C2 threshold:

- Required: `total_surplus <= 6581`
- Actual: `total_surplus = 6675`

Evidence:

- B0 and C1 metrics: `docs/reconstruction/10_current_decision_state.md`
- C2 metrics: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`

## Target Relations

| Relation | C2 observed | C2 surplus |
| --- | ---: | ---: |
| `P31` | 5952 | 5714 |
| `P279` | 744 | 517 |
| `P131` | 337 | 158 |

C2 did reduce all three targeted generic relations, but the reductions were too small to meet the candidate objective.

Evidence:

- `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json`
- `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`

## Connectivity Constraint Evidence

The C2 generator accepted 27 deletions and recorded 92106 rejected deletion checks.

| Rejection reason | Count |
| --- | ---: |
| `would_disconnect_graph` | 75893 |
| `endpoint_degree_not_redundant` | 16212 |
| `no_connectivity_safe_candidate` | 1 |

The high `would_disconnect_graph` count indicates that many candidate generic triples act as connectivity-supporting edges under the current weak-connectivity invariant.

Evidence: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json`

## Interpretation

C2 shows that targeted deletion-only pruning can preserve hard structural constraints, but it does not solve the relation-balance problem. The graph remains dominated by generic surplus, especially `P31`, and further deletion-only pruning is unlikely to produce a strong candidate without either disconnecting the graph or removing only a small number of safe edges.

This does not mean the balance objective is impossible. It means the current deletion-only approach is the wrong next direction.

## Recommended Next Direction

The next controlled experiment should use remove-and-replace rather than another deletion-only candidate.

Reason:

Deletion-only pruning is blocked by connectivity constraints. A remove-and-replace approach can try to remove generic surplus edges while adding or preserving alternative connectivity-supporting triples from the candidate pool.

This recommendation is based on C2's negative evidence only. It does not claim that a remove-and-replace candidate has been run or accepted.
