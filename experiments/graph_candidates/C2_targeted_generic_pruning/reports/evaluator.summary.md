# Graph Candidate Summary: targeted_generic_pruning_from_B0

## Inputs

- Graph: `experiments/graph_candidates/C2_targeted_generic_pruning/outputs/pruned_graph.jsonl`
- Graph SHA256: `a017ac53fe6ead1f81b26a3cd4c10679eb14036aad40144039d1ed2185d53da0`
- Allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Allocation SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

## Core Metrics

| Metric | Value |
| --- | ---: |
| Raw graph rows | 24656 |
| Total triples (unique, allocation basis) | 24656 |
| Unique triples | 24656 |
| Duplicate triple count | 0 |
| Unique entities | 21893 |
| Unique relations | 139 |
| Weak component count | 1 |
| Largest weak component ratio | 1 |
| Allocation relations | 139 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total expected eta | 20000 |
| Observed allocated triples | 24656 |
| Total deficit | 2019 |
| Total surplus | 6675 |

## Pattern Metrics

| Pattern | Expected Eta | Observed | Deficit | Surplus |
| --- | ---: | ---: | ---: | ---: |
| anti_symmetric | 5000 | 4970.75136654 | 29.2486334585 | 0 |
| composition | 5000 | 11239.9339653 | 0 | 6239.93396534 |
| inverse | 5000 | 4824.21749892 | 175.782501082 | 0 |
| symmetric | 5000 | 3621.0971692 | 1378.9028308 | 0 |

## Top Underfilled Relations

| Relation | Expected | Observed | Deficit |
| --- | ---: | ---: | ---: |
| P514 | 497 | 38 | 459 |
| P4545 | 339 | 59 | 280 |
| P2152 | 329 | 54 | 275 |
| P12994 | 227 | 106 | 121 |
| P2155 | 318 | 207 | 111 |
| P8865 | 230 | 129 | 101 |
| P10374 | 178 | 98 | 80 |
| P7209 | 197 | 138 | 59 |
| P2743 | 468 | 445 | 23 |
| P13177 | 429 | 408 | 21 |

## Top Overfilled Relations

| Relation | Expected | Observed | Surplus |
| --- | ---: | ---: | ---: |
| P31 | 238 | 5952 | 5714 |
| P279 | 227 | 744 | 517 |
| P131 | 179 | 337 | 158 |
| P527 | 191 | 255 | 64 |
| P361 | 183 | 241 | 58 |
| P1889 | 205 | 251 | 46 |
| P1001 | 172 | 216 | 44 |
| P366 | 180 | 198 | 18 |
| P2670 | 183 | 192 | 9 |
| P1312 | 69 | 77 | 8 |

## Extraction Notes

- Allocation eta field precedence: `eta_integer`, then `eta`, then `eta_expected`.
- Allocation relations are unique relations with positive extracted eta.
- Eta and allocation metrics use unique triples, not raw graph rows.
- Pattern observed counts are apportioned by per-relation eta weights to avoid double-counting multi-pattern relations.
- Connectivity, entity counts, and default relation counts are computed from unique triples.
- This evaluator reads graph and allocation inputs and writes reports only; it does not modify inputs.
