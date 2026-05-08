# C2 Decision: Targeted Generic Pruning From B0

Decision date: 2026-05-07

Status: `generated_failed_minimum_thresholds`

Decision: rejected as final candidate, kept as exploratory negative evidence.

C2 was generated as a controlled graph candidate from B0 using the operational layer under `experiments/graph_candidates/C2_targeted_generic_pruning/`. It is not accepted as a final thesis graph. It is retained because it provides useful evidence about the limits of deletion-only targeted generic pruning under the current connectivity constraints.

## Evidence

- Candidate graph: `experiments/graph_candidates/C2_targeted_generic_pruning/outputs/pruned_graph.jsonl`
- Generation report: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json`
- Evaluator report: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`
- Evaluator summary: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.summary.md`
- Run command: `experiments/graph_candidates/C2_targeted_generic_pruning/command.run.sh`
- Run config: `configs/graph_candidates/C2_targeted_generic_pruning.run.json`

## Hash Chain

| Artifact | SHA256 |
| --- | --- |
| Parent B0 graph | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` |
| Allocation | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` |
| C2 graph | `a017ac53fe6ead1f81b26a3cd4c10679eb14036aad40144039d1ed2185d53da0` |

## Outcome

C2 preserved the hard structural and relation-coverage constraints, but failed the minimum surplus threshold.

| Metric | Value |
| --- | ---: |
| Accepted deletions | 27 |
| Weak components | 1 |
| Largest weak component ratio | 1.0 |
| Duplicate triples | 0 |
| Unique relations | 139 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total deficit | 2019 |
| Total surplus | 6675 |
| Passes minimum thresholds | false |
| Passes strong thresholds | false |

Minimum-threshold failure:

- Required `total_surplus <= 6581`
- Actual `total_surplus = 6675`

## Target Relations

| Relation | Observed | Surplus |
| --- | ---: | ---: |
| `P31` | 5952 | 5714 |
| `P279` | 744 | 517 |
| `P131` | 337 | 158 |

## Rejection Reasons

| Reason | Count |
| --- | ---: |
| `would_disconnect_graph` | 75893 |
| `endpoint_degree_not_redundant` | 16212 |
| `no_connectivity_safe_candidate` | 1 |

## Decision Rationale

C2 is rejected as a final candidate because it did not meet the configured minimum surplus target. It reduced B0 surplus from 6702 to 6675, an improvement of only 27, and did not beat C1's total surplus of 6582.

C2 is kept as exploratory evidence because it preserved weak connectivity, duplicate-free graph content, all 139 relations, all allocated relation coverage, and zero allocated relation absence. The high `would_disconnect_graph` count indicates that many candidate generic-relation deletions were blocked by weak-connectivity preservation.

This decision does not promote C2, does not mark it final, and does not change the thesis-reported graph choice.
