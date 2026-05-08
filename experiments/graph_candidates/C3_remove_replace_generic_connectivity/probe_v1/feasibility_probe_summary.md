# C3 Remove-And-Replace Feasibility Probe v1

Status: feasibility probe only. No graph candidate was generated.

## Inputs

- B0 graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- B0 SHA256: `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`
- Allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Allocation SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`
- Eligible pool: `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/eligible_replacement_candidates.jsonl`
- Eligible pool SHA256: `5440075235b69bd9586c602371ad80202fe805c9d27235efb4de5e90796d061e`

## Results

- Target edges tested: `500`
- Replacement candidates loaded: `990`
- Replacement pair tests performed: `495000`
- Deletions already safe without replacement: `27`
- Targets requiring replacement: `473`
- Targets with at least one feasible replacement: `27`
- Targets requiring replacement with feasible replacement: `0`
- Targets with no feasible replacement: `473`
- Total feasible swaps found: `20493`

## Recommendation

A bounded safe-edge remove-and-replace generator is worth implementing only as a limited experiment: feasible swaps exist for deletion-safe target edges, but the eligible pool did not rescue any tested connectivity-critical bridge-like target edges. Do not frame this as solving the C2 connectivity blocker.

## Strongest Swap Examples

| Target | Replacement | Surplus delta | Deficit delta | Candidate score | Provenance |
| --- | --- | ---: | ---: | ---: | --- |
| `Q176 P131 Q16` | `Q993765 P2499 Q16831486` | -1 | -1 | 160 | `event_bridge_triples` |
| `Q74035 P131 Q239` | `Q993765 P2499 Q16831486` | -1 | -1 | 160 | `event_bridge_triples` |
| `Q14751 P31 Q5503` | `Q993765 P2499 Q16831486` | -1 | -1 | 160 | `event_bridge_triples` |
| `Q1904 P131 Q16` | `Q993765 P2499 Q16831486` | -1 | -1 | 160 | `event_bridge_triples` |
| `Q1948 P131 Q16` | `Q993765 P2499 Q16831486` | -1 | -1 | 160 | `event_bridge_triples` |
| `Q1965 P131 Q16` | `Q993765 P2499 Q16831486` | -1 | -1 | 160 | `event_bridge_triples` |
| `Q2003 P131 Q16` | `Q993765 P2499 Q16831486` | -1 | -1 | 160 | `event_bridge_triples` |
| `Q1394 P31 Q5` | `Q993765 P2499 Q16831486` | -1 | -1 | 160 | `event_bridge_triples` |
| `Q2007 P131 Q16` | `Q993765 P2499 Q16831486` | -1 | -1 | 160 | `event_bridge_triples` |
| `Q2009 P131 Q16` | `Q993765 P2499 Q16831486` | -1 | -1 | 160 | `event_bridge_triples` |

## Runtime Notes

- Started: `2026-05-07T22:15:33.004515+00:00`
- Finished: `2026-05-07T22:15:33.457260+00:00`
- Elapsed seconds: `0.453`

## Notes

- This probe used bridge analysis on B0 rather than writing modified graph files.
- No live WDQS query was made.
- `docs/reconstruction/graph_candidates.tsv` was not edited.
