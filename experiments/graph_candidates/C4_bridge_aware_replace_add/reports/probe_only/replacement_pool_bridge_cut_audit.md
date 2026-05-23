# C4.1 Replacement Pool Bridge-Cut Audit

Status: read-only audit. No graph candidate was generated.

## Inputs

- Config: `experiments/graph_candidates/C4_bridge_aware_replace_add/configs/config.template.json`
- Probe report: `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/probe_report.json`
- Parent graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Parent graph SHA256: `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`
- Allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Allocation SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`
- Replacement pool: `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/eligible_replacement_candidates.jsonl`
- Replacement pool SHA256: `5440075235b69bd9586c602371ad80202fe805c9d27235efb4de5e90796d061e`

## Audit Counts

- Tested bridge targets: `200`
- Replacement rows loaded: `990`
- Replacement rows with both endpoints in B0: `612`
- Replacement rows with one endpoint in B0: `378`
- Replacement rows with no endpoints in B0: `0`
- Unique replacement rows crossing any tested cut: `0`
- Unique cut-crossing allocated replacement rows: `0`
- Unique cut-crossing balance-improving replacement rows: `0`
- Unique cut-crossing duplicate rows: `0`

## Pair-Test Aggregate

| Check | Count |
| --- | ---: |
| `endpoint_inside_b0_both` | 122400 |
| `endpoint_inside_b0_one` | 75600 |
| `endpoint_inside_b0_none` | 0 |
| `crosses_cut` | 0 |
| `crosses_cut_and_allocated` | 0 |
| `crosses_cut_and_balance_improving` | 0 |
| `crosses_cut_but_duplicate` | 0 |
| `deficit_would_increase` | 0 |
| `feasible_if_hard_constraints_hold` | 0 |
| `reject_endpoint_not_both_inside_b0` | 75600 |
| `reject_does_not_cross_bridge_cut` | 122400 |
| `reject_duplicate` | 0 |
| `reject_unallocated_relation` | 0 |
| `reject_not_surplus_reducing` | 0 |
| `reject_deficit_increase` | 0 |

## Replacement Relation Distribution

| Relation | Rows |
| --- | ---: |
| `P5277` | 194 |
| `P2959` | 69 |
| `P2500` | 68 |
| `P2499` | 52 |
| `P1445` | 52 |
| `P1753` | 47 |
| `P3403` | 42 |
| `P2935` | 36 |
| `P4329` | 32 |
| `P3032` | 29 |
| `P1420` | 28 |
| `P163` | 27 |
| `P814` | 25 |
| `P1151` | 23 |
| `P1403` | 20 |
| `P1639` | 20 |
| `P2389` | 20 |
| `P612` | 19 |
| `P167` | 18 |
| `P7938` | 16 |
| `P1398` | 16 |
| `P355` | 11 |
| `P1322` | 10 |
| `P8289` | 10 |
| `P1434` | 9 |
| `P12765` | 9 |
| `P466` | 8 |
| `P399` | 8 |
| `P12764` | 6 |
| `P3461` | 6 |

## Interpretation

Primary failure mode: `bridge_cut_crossing_failure`.

The bounded audit shows that eligible replacement candidates with both endpoints in B0 exist, but none cross any of the tested bridge cuts. The zero feasible C4 probe result is therefore explained primarily by bridge-cut crossing coverage, not by allocation status or balance-delta filtering after a crossing candidate exists.

## Notes

- This audit reads frozen local files only.
- It does not write `outputs/graph.jsonl`.
- It does not update `candidate_registry.v1.json`.
- It does not query WDQS or call LLMs.
