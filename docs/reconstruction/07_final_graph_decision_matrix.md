# Final Graph Decision Matrix

## Candidate Graphs

| Metric | Stage12 Largest Component | Stage13 Aggressive But Guarded Pruned Graph | Evidence |
| --- | ---: | ---: | --- |
| Graph path | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl` | Artifact paths |
| File type | CSV with header `h,r,t` | JSONL with `h`, `r`, `t`, `triple_id` | `head` inspection |
| SHA256 | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` | `e01d7137c1dbcd790082825a025cade7198a957b3c936f0d9b5b3f0b33780b73` | `sha256sum` |
| Number of triples | 24683 | 24223 | Stage12 eta summary; Stage13 report; direct line/unique-triple check |
| Unique triples | 24683 | 24223 | Direct graph check |
| Number of unique relations | 139 | 139 | Direct graph check; eta summaries |
| Entity count | 21893 | 21893 | Direct weak-component check; Stage13 report |
| Weak component count | 1 | 1 | Direct graph check; Stage13 report |
| Largest component ratio | 1.0 | 1.0 | Direct graph check; Stage13 report |
| Weak connectivity preserved | Yes | Yes | Direct graph check; Stage13 branch `summary.csv` |
| Total expected eta | 20000 | 20000 | Eta summaries |
| Observed allocated triples | 24683 | 24223 | Eta summaries |
| Total deficit | 2019 | 2359 | Eta summaries |
| Total surplus | 6702 | 6582 | Eta summaries |
| Weighted fulfillment ratio | 1.23415 | 1.21115 | Eta summaries |
| Zero allocated relations | 0 | 0 | Eta summaries |
| Fully fulfilled relations | 41 | 23 | Eta summaries |
| Exactly fulfilled relations | 17 | 8 | Eta summaries |
| Overfilled relations | 24 | 15 | Eta summaries |
| Partially fulfilled relations | 98 | 116 | Eta summaries |
| Pattern anti-symmetric observed / expected | 4970 / 5000 | 4685 / 5000 | `pattern_expected_vs_observed` in eta summaries |
| Pattern composition observed / expected | 11267 / 5000 | 11145 / 5000 | `pattern_expected_vs_observed` in eta summaries |
| Pattern inverse observed / expected | 4824 / 5000 | 4771 / 5000 | `pattern_expected_vs_observed` in eta summaries |
| Pattern symmetric observed / expected | 3622 / 5000 | 3622 / 5000 | `pattern_expected_vs_observed` in eta summaries |
| Pruning changed relation coverage | Not applicable | No relation loss detected: 139 relations before and after | Direct relation counts; Stage13 report relation count maps |
| Audit report exists | Yes: `largest_component_eta_analysis/summary.json` and supervisor summary | Yes: `pruned_graph.report.json` and `eta_analysis/summary.json` | Artifact existence and hashes |
| Direct SLURM log or manifest | Stage11/12 manifests and reports exist; no direct Stage12 SLURM log found in `logs/` | Direct SLURM log exists: `logs/stage13_prune_revised_29012090.out`; branch summary files exist | Log search and artifact inspection |
| Allocation linkage clarity | Medium-high: Stage12 summary stores stale `src/kg_builder/input/bidirectional_allocation_results5k.json`; manifests point to `/home/kg_benchmark/src/kg_builder/input/bidirectional_allocation_results5k.json`; local equivalent is inferred as `src/Pruning graph/bidirectional_allocation_results5k.json` | High: Stage13 log directly names `ALLOCATION_MANIFEST=src/Pruning graph/bidirectional_allocation_results5k.json` | Stage12 summary/manifests; Stage13 log |
| Thesis suitability | Strong candidate for "post-repair connected largest component before pruning" | Strongest candidate for "final balance-pruned reported dataset" if Stage13 is accepted as a reported stage | Evidence-based recommendation |
| Main risks | More overfull globally; composition surplus dominated by P31/P279/P131; external input path unresolved | Worse total deficit and fewer fulfilled relations than Stage12; Stage13 must be explicitly justified as final stage | Eta summaries; supervisor summary; Stage13 report |

## Recommendation

Recommended final graph:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl`

Reason:

This is the strongest candidate if the thesis goal is to report the latest connected, balance-pruned dataset artifact. It has direct Stage13 SLURM evidence, a pruning report, branch-sweep comparison, an eta audit, preserved weak connectivity, preserved 139-relation coverage, and a direct allocation link to `src/Pruning graph/bidirectional_allocation_results5k.json`.

Evidence:

- Stage13 log: `logs/stage13_prune_revised_29012090.out`
- Input graph in log: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Allocation in log: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Output graph: `.../stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl`
- Report: `.../aggressive_but_guarded/pruned_graph.report.json`
- Eta audit: `.../aggressive_but_guarded/eta_analysis/summary.json`
- Branch comparison: `.../stage13_branch_sweep_20260423_160635/summary.csv` and `summary.md`

Risks:

- Stage13 has higher total deficit than Stage12: 2359 vs 2019.
- Stage13 has fewer fully fulfilled relations than Stage12: 23 vs 41.
- Stage13 pruning is not proven to be part of the originally intended Phase II pipeline; it is a later repair/refinement/pruning branch.
- The strongest upstream graph before pruning is Stage12, whose input path still points to an external `/home/kg_benchmark/...` production run.

What must be confirmed by human before final thesis use:

1. Confirm that Stage13 pruning should be part of the reported thesis pipeline, not only an optional post-pipeline analysis.
2. Confirm that the final dataset should optimize for a connected pruned artifact rather than the less-pruned Stage12 largest component.
3. Confirm the path translation from `src/kg_builder/input/bidirectional_allocation_results5k.json` and `/home/kg_benchmark/src/kg_builder/input/bidirectional_allocation_results5k.json` to local `src/Pruning graph/bidirectional_allocation_results5k.json`.
4. Confirm whether the thesis should report Stage12 as the final post-repair graph and Stage13 as an ablation/refinement, or Stage13 as the final dataset.

## If The Thesis Goal Differs

Both candidates are defensible, but they answer different thesis goals:

| Thesis Goal | Better Candidate | Reason |
| --- | --- | --- |
| Report the largest connected graph after Stage11/Stage12 repair, before pruning | Stage12 `largest_component.csv` | Stronger eta fulfillment metrics and fewer transformation layers after repair. |
| Report the latest connected graph after balance pruning | Stage13 `aggressive_but_guarded/pruned_graph.jsonl` | Direct Stage13 run log, branch sweep, preserved connectivity, preserved relation coverage, and explicit pruning report. |
| Avoid treating optional post-pipeline repair/pruning as native Phase II | Stage12 or earlier graph, with Stage13 as appendix | Existing reconstruction marks Stage11/12/13 as later repair/pruning branches unless accepted by thesis narrative. |

## Allocation Decision Matrix

| Allocation Artifact | SHA256 | Relation Universe Count | Allocation Rows With Positive Eta | Unique Positive Relations | Eta Total | Thresholds Encoded In Content | Linked Graph Outputs | Confidence | Risks |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json` | `aafade9887a863ee5bcebe8fb67a6e0f151ac2c696a6bc2c283044bca9b8090e` | 1148 | 209 | 164 | 20000 | `base_min_total=50`, `sym_min_conf=0.97`, `anti_min_conf=0.97`, `inv_min_conf=0.97`, `comp_min_conf=0.9` | Trial9 online and repair branch | High for Trial9 | Not linked to Stage12/Stage13 final candidates. |
| `data/connectedgraph/bidirectional_allocation_results_allsupp8_conf97_compconf90.json` | `790e856388e592c29cb2957dbea36aa4edcd43667d14b820b767748cfc8d19e5` | 1469 | 241 | 196 | 20000 | `base_min_total=8`, all support thresholds 8, confidence thresholds mostly 0.97/0.9 | Trial10 runner references | Medium | No strong final graph linkage found. |
| `data/processed/hop_support_v3/bidirectional_allocation_results_hop_v3_patchedby_v2_allsup50_60sym_99anti_90inv_95comp.json` | `472b32e6418b344267bf87237f3f4474d6a0542e3e8a46cf96bdfef393f94eec` | 1467 | 143 | 125 | 20000 | `sym_min_conf=0.6`, `anti_min_conf=0.99`, `inv_min_conf=0.9`, `comp_min_support=8`, `comp_min_conf=0.95` | Trial1/Trial2 hop-v3 online construction and checkpoint postprocess | High for Trial2 | Existing notes distinguish it from Stage12/Stage13 allocation family. |
| `src/Pruning graph/bidirectional_allocation_results5k.json` | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` | 1467 | 154 | 139 | 20000 | `sym_min_conf=0.6`, `anti_min_conf=0.99`, `inv_min_conf=0.6`, `comp_min_support=50`, `comp_min_conf=0.6` | Stage12 and Stage13 candidate final graph family | High for Stage13; medium-high for Stage12 | Direct allocation export log missing; Stage12 stored path is stale/external. |

Recommended allocation for Stage12 largest component:

`src/Pruning graph/bidirectional_allocation_results5k.json`

Evidence: Stage12 eta summary stores `src/kg_builder/input/bidirectional_allocation_results5k.json`; Stage11/12 manifests store `/home/kg_benchmark/src/kg_builder/input/bidirectional_allocation_results5k.json`; local comparison notes state Stage12/Stage13 use the `5k` allocation family; local available allocation is `src/Pruning graph/bidirectional_allocation_results5k.json`.

Recommended allocation for Stage13 aggressive pruned graph:

`src/Pruning graph/bidirectional_allocation_results5k.json`

Evidence: `logs/stage13_prune_revised_29012090.out` directly reports `ALLOCATION_MANIFEST=src/Pruning graph/bidirectional_allocation_results5k.json`; Stage13 eta summaries store `allocation_path: src/Pruning graph/bidirectional_allocation_results5k.json`.

Allocation artifacts not recommended for Stage12/Stage13 final candidates:

- `data/processed/hop_support_v3/bidirectional_allocation_results_hop_v3_patchedby_v2_allsup50_60sym_99anti_90inv_95comp.json`: strongest for Trial2 online branch, not Stage12/Stage13.
- `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json`: strongest for Trial9 online/repair branch.
- `data/connectedgraph/bidirectional_allocation_results_allsupp8_conf97_compconf90.json`: linked to Trial10 runner, not to inspected final candidates.

