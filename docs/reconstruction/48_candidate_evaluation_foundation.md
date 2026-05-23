# Phase II-A Candidate Evaluation Foundation

This implementation adds reusable, pure graph-candidate evaluation helpers under `src/kg_pipeline/evaluation/`. It does not replace the historical standalone evaluator at `tools/graph_candidate_evaluation/evaluate_graph_candidate.py`; the goal is to provide a shared foundation for future controlled candidates while preserving the duplicate-safe semantics already used for B0/C1/C2 evaluation.

## Created Modules

- `src/kg_pipeline/evaluation/graph_io.py`
  - loads CSV and JSONL graph files with `h`, `r`, and `t` fields;
  - normalizes rows to `(h, r, t)` tuples;
  - reports raw rows, unique triples, duplicate triples, unique entities, unique relations, raw relation counts, and unique relation counts.

- `src/kg_pipeline/evaluation/allocation_metrics.py`
  - loads allocation JSON payloads;
  - extracts eta with the same precedence as the standalone evaluator: `eta_integer`, then `eta`, then `eta_expected`;
  - computes relation expected counts, observed counts, deficits, surpluses, allocated relations observed, and zero allocated relations.

- `src/kg_pipeline/evaluation/connectivity_metrics.py`
  - computes weak components with a local Union-Find implementation;
  - reports weak component count, largest weak component size, and largest weak component ratio from unique triples.

- `src/kg_pipeline/evaluation/pattern_balance.py`
  - reads pattern membership from allocation payloads;
  - computes evaluator-compatible floating pattern totals by eta-weighted apportioning;
  - also exposes integer pattern totals that round each eta-weighted relation-row contribution before summing for compact candidate comparison.

- `src/kg_pipeline/evaluation/candidate_report.py`
  - combines graph, connectivity, allocation, and pattern-balance summaries into a report dictionary compatible with the existing evaluator's core report shape.

## Golden-Master Check

`scripts/reconstruction/check_candidate_evaluation_foundation.py` evaluates the selected B0 graph:

- graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`

The check verifies the known B0 metrics:

| Metric | Expected |
| --- | ---: |
| unique triples | 24,683 |
| unique entities | 21,893 |
| unique relations | 139 |
| weak components | 1 |
| largest weak component ratio | 1.0 |
| duplicate triples | 0 |
| allocated relations observed | 139 |
| zero allocated relations | 0 |
| total surplus | 6,702 |
| total deficit | 2,019 |

It also verifies integer pattern totals:

| Pattern | Expected Observed Total |
| --- | ---: |
| anti_symmetric | 4,970 |
| composition | 11,267 |
| inverse | 4,824 |
| symmetric | 3,622 |

## Scope Boundary

This phase creates reusable evaluation helpers only. It does not:

- modify historical graph candidates;
- run graph generation or pruning;
- query WDQS;
- call LLMs;
- refactor historical Phase II generator code;
- replace the existing standalone evaluator.

Future work can migrate `tools/graph_candidate_evaluation/evaluate_graph_candidate.py` onto these helpers after another golden-master comparison against the existing B0/C1/C2 reports.

