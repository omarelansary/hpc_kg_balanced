# C4.2 Local Cut-Crossing Candidate Search

Status: read-only local evidence search. No graph candidate was generated.

## Inputs

- Config: `experiments/graph_candidates/C4_bridge_aware_replace_add/configs/config.template.json`
- Bridge-cut audit: `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/replacement_pool_bridge_cut_audit.json`
- Parent graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Parent graph SHA256: `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`
- Allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Allocation SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

## Search Result

- Cuts tested: `200`
- Cut-crossing candidate rows found: `629`
- Unique cut-crossing candidates: `625`
- Allocated cut-crossing candidate rows: `106`
- Unique allocated cut-crossing candidates: `102`
- Surplus-reducing candidate-cut pairs: `546`
- Unique balance-improving candidates: `523`
- Allocated surplus-reducing candidate-cut pairs: `0`
- Unallocated surplus-reducing candidate-cut pairs: `546`
- Candidate-cut pairs that would increase deficit: `0`
- Primary result: `only_unallocated_cut_crossing_candidates_reduce_surplus`

## Source Scan Counts

| Source | Files | Rows scanned | Parsed triples | Both endpoints in B0 | Already in B0 | Cut-crossing rows | Allocated crossing rows |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `frozen_candidate_pools` | 2 | 872156 | 872156 | 15995 | 0 | 625 | 102 |
| `stage02_candidate_shards` | 139 | 81958 | 81958 | 18239 | 17941 | 4 | 4 |
| `stage11_graph_output` | 1 | 24670 | 24670 | 24638 | 24638 | 0 | 0 |
| `stage12_graph_output` | 1 | 24715 | 24715 | 24683 | 24683 | 0 | 0 |

## Top Feasible-Looking Candidates

No feasible-looking candidates were found under the local read-only search criteria.

## Interpretation

This search broadens C4.1 beyond the eligible replacement pool by scanning Stage11/Stage12 graph outputs, Stage2 candidate shards, and frozen candidate pools. It still uses only local frozen files.

The search excludes triples already present in B0 and requires both candidate endpoints to be in B0. A cut-crossing hit means the candidate connects the two sides exposed by removing a tested target bridge edge.

This output is evidence only. It does not create a graph and does not update the candidate registry.
