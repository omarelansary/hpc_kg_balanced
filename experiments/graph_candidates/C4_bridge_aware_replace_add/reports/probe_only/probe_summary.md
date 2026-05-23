# C4 Bridge-Aware Replace/Add Probe

Status: probe only. No graph candidate was generated.

## Inputs

- Config: `experiments/graph_candidates/C4_bridge_aware_replace_add/configs/config.template.json`
- Parent graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Parent graph SHA256: `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`
- Allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Allocation SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`
- Replacement pool: `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/eligible_replacement_candidates.jsonl`
- Replacement pool SHA256: `5440075235b69bd9586c602371ad80202fe805c9d27235efb4de5e90796d061e`
- Replacement pool note: configured path missing; used restored eligible_v1 pool path

## Baseline B0 Metrics

- Unique triples: `24683`
- Weak components: `1`
- Duplicate triples: `0`
- Allocated relations observed: `139`
- Zero allocated relations: `0`
- Total surplus: `6702.0`
- Total deficit: `2019.0`

## Probe Results

- Target edges tested: `200`
- Deletion-safe targets: `0`
- Connectivity-critical targets: `200`
- Feasible safe deletions: `0`
- Connectivity-critical targets with feasible replacement: `0`
- Total feasible independent moves: `0`
- Greedy non-reuse candidate count: `0`
- Best observed surplus delta: `None`
- Best observed deficit delta: `None`

## Rejection Reasons

| Reason | Count |
| --- | ---: |
| `does_not_reconnect_bridge_cut` | 122400 |
| `replacement_endpoint_not_in_parent_graph` | 75600 |

## Notes

- This probe writes reports only under `reports/probe_only/`.
- `outputs/graph.jsonl` is not written.
- The candidate registry is not updated.
- Live WDQS and LLM sources are disabled.
