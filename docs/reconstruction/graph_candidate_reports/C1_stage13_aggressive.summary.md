# Graph Candidate Summary: Stage13 aggressive_but_guarded

## Inputs

- Graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl`
- Graph SHA256: `e01d7137c1dbcd790082825a025cade7198a957b3c936f0d9b5b3f0b33780b73`
- Allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Allocation SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Raw graph rows | 24223 |
| Total triples (unique, allocation basis) | 24223 |
| Unique triples | 24223 |
| Duplicate triple count | 0 |
| Unique entities | 21893 |
| Unique relations | 139 |
| Weak component count | 1 |
| Largest weak component ratio | 1 |
| Allocation relations | 139 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total expected eta | 20000 |
| Observed allocated triples | 24223 |
| Total deficit | 2359 |
| Total surplus | 6582 |

## Pattern Metrics

| Pattern | Expected Eta | Observed | Deficit | Surplus |
| --- | ---: | ---: | ---: | ---: |
| anti_symmetric | 5000 | 4686.71158653 | 313.288413471 | 0 |
| composition | 5000 | 11144.2107511 | 0 | 6144.21075106 |
| inverse | 5000 | 4770.98049322 | 229.019506783 | 0 |
| symmetric | 5000 | 3621.0971692 | 1378.9028308 | 0 |

## Top Underfilled Relations

| Relation | Expected | Observed | Deficit |
| --- | ---: | ---: | ---: |
| P514 | 497 | 38 | 459 |
| P4545 | 339 | 59 | 280 |
| P2152 | 329 | 54 | 275 |
| P12994 | 227 | 104 | 123 |
| P2155 | 318 | 207 | 111 |
| P8865 | 230 | 129 | 101 |
| P8308 | 175 | 88 | 87 |
| P10374 | 178 | 97 | 81 |
| P527 | 191 | 124 | 67 |
| P7209 | 197 | 138 | 59 |

## Top Overfilled Relations

| Relation | Expected | Observed | Surplus |
| --- | ---: | ---: | ---: |
| P31 | 238 | 5953 | 5715 |
| P279 | 227 | 748 | 521 |
| P131 | 179 | 344 | 165 |
| P361 | 183 | 238 | 55 |
| P1001 | 172 | 216 | 44 |
| P1889 | 205 | 242 | 37 |
| P366 | 180 | 197 | 17 |
| P2283 | 59 | 66 | 7 |
| P127 | 179 | 184 | 5 |
| P2670 | 183 | 188 | 5 |

## Extraction Notes

- Allocation eta field precedence: `eta_integer`, then `eta`, then `eta_expected`.
- Allocation relations are unique relations with positive extracted eta.
- Eta and allocation metrics use unique triples, not raw graph rows.
- Pattern observed counts are apportioned by per-relation eta weights to avoid double-counting multi-pattern relations.
- Connectivity, entity counts, and default relation counts are computed from unique triples.
- This evaluator reads graph and allocation inputs and writes reports only; it does not modify inputs.
