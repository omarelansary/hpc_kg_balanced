# Pre-Stage11 Input Mapping Investigation

## Conclusion

The stale pre-Stage11 input path remains **unresolved** as a local file. No candidate found in the local workspace matched the Stage11-reported input count of 17,965 unique triples with suitable graph-file provenance.

Stale path under investigation:

- `/home/kg_benchmark/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl`

A derived reconstruction is evidence-supported but is not the original file: `stage11 graph_output.jsonl` minus `state.json` `added_core_triples` produces 17,965 unique triples, matching the Stage11 report. This does not recover the original file path or SHA256.

## Stage11 Evidence

| Evidence | Value |
|---|---:|
| Stage11 manifest | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/manifest.json` |
| Stage11 report | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/report.json` |
| Manifest input path | `/home/kg_benchmark/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl` |
| Reported original input triples | 17965 |
| Reported original unique triples | 17965 |
| Reported original weak components | 6021 |
| Stage11 output unique triples | 24670 |
| Stage11 added core triples | 6705 |
| Output minus recorded additions | 17965 unique triples |

## Search Method

Local workspace search used these patterns and checks:

- `*filtered*graph*triples*.jsonl`
- `*graph_triples*.jsonl`
- `*filtered*.jsonl`
- `*stage07*`
- `*eta_aware*`
- `*prod_refine*`
- `JSONL files with line count around 17,965`

For each candidate, the investigation recorded file size, SHA256, line count, JSONL parse status, h/r/t-like triple fields, feasible unique triple/relation counts, and overlap with `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl`.

## Candidate Summary

- Candidates examined: 48
- Candidates with exactly 17,965 lines: 0
- Candidates within ±100 lines of 17,965: 0
- Plausible local equivalents after count/provenance/overlap checks: 0

## Candidate Table

| Path | Size Bytes | SHA256 | Lines | JSONL OK | h/r/t-like Records | Unique Triples | Unique Relations | Stage11 Output Overlap | Assessment |
|---|---:|---|---:|---|---:|---:|---:|---:|---|
| `data/connectedgraph/trial9/absent_allocated_relation_before_repair_filtered/events.jsonl` | 209794 | `ce5fdb2184c64a2584f8fb5aa30e4b50a95cbeb82593160fae0a58e36074b574` | 866 | True | 0 |  |  |  | against: event log, not an h/r/t graph file. |
| `data/connectedgraph/trial9/trial9_ckpt_filtered.triples.jsonl` | 3101 | `7353da3146dafd20c9496c51d034d5fdef01fa3cc8b8896cc1e0512d4c8bb44b` | 70 | True | 70 | 70 | 11 | 0 | against: Trial9 filtered graph has 70 triples and zero overlap with Stage11 output in h/r/t form. |
| `data/connectedgraph/trial9_ckpt_filtered.triples.jsonl` | 3101 | `7353da3146dafd20c9496c51d034d5fdef01fa3cc8b8896cc1e0512d4c8bb44b` | 70 | True | 70 | 70 | 11 | 0 | against: Trial9 filtered graph has 70 triples and zero overlap with Stage11 output in h/r/t form. |
| `data/connectedgraph/triples/trial9_ckpt_filtered.triples.jsonl` | 3101 | `7353da3146dafd20c9496c51d034d5fdef01fa3cc8b8896cc1e0512d4c8bb44b` | 70 | True | 70 | 70 | 11 | 0 | against: Trial9 filtered graph has 70 triples and zero overlap with Stage11 output in h/r/t form. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/events.jsonl` | 111368539 | `d1f7d5ee50d3a0d602d6f026ffdb0b8129cd9e8c34dd59b43d87d2e7fa0247f8` | 250477 | True | 0 |  |  |  | against: event log, not an h/r/t graph file. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl` | 1756236 | `73bc624bf9147b0bba4962ab286648bcfeeb931a94a1d1a727839f160b35ada5` | 24670 | True | 24670 | 24670 | 139 | 24670 | against: this is the Stage11 output, not the pre-Stage11 input; it has 24,670 unique triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/debug_score_scarcity_round1/pruned_graph.jsonl` | 2165733 | `ad4068afc8da69c67b43cc2e09f076ea3ed1351c86b648dd0b6a2f4f2271e171` | 24683 | True | 24683 | 24683 | 139 | 24638 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/events.jsonl` | 3121682 | `6f3b52a5bb2e620e5e13082fbb2a5fd2b353759bebc377d3a07dc43f71568527` | 8041 | True | 0 |  |  |  | against: event log, not an h/r/t graph file. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/graph_output.jsonl` | 1739977 | `89ec9bf9c8932962fd3d966073b51f76345666eda5ed5d9beb18659d02e294b0` | 24715 | True | 24715 | 24715 | 139 | 24670 | against: this is Stage12 output, downstream of Stage11; it has 24,715 unique triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component_eta_analysis/relation_fulfillment.jsonl` | 32830 | `1424e30f220be841c652f222c21ee17889dce4db65e6d29cdd391d0ccdcc0e53` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/my_debug_run/eta_analysis/relation_fulfillment.jsonl` | 32848 | `1a6d343e1fa97027f18f6310578cec3108c57955643f240e9539adaa2dbd11df` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/my_debug_run/largest_component_eta_analysis/relation_fulfillment.jsonl` | 32848 | `1a6d343e1fa97027f18f6310578cec3108c57955643f240e9539adaa2dbd11df` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/my_debug_run/pruned_graph.jsonl` | 2153082 | `bbad9c0b9860e9fc72d09cb215e00d14a7f1f736911e1a838cfc75250348e496` | 24534 | True | 24534 | 24534 | 139 | 24489 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_20260322_161843/eta_analysis/relation_fulfillment.jsonl` | 32876 | `4b01a0727d23a33881637676122b84b1373dcb659adca2636323b1d6543fefab` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_20260322_161843/largest_component_eta_analysis/relation_fulfillment.jsonl` | 32876 | `4b01a0727d23a33881637676122b84b1373dcb659adca2636323b1d6543fefab` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_20260322_161843/pruned_graph.jsonl` | 2147873 | `c77994917345f674d821e57ee286ad4a5dd41d5e3b2c562e4a26c56c205e96bb` | 24471 | True | 24471 | 24471 | 139 | 24426 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_ablation_20260322_215639/eta_analysis/relation_fulfillment.jsonl` | 32826 | `f96551bc2d67876212db98231747d05b29c75e94ba851694d9d4e10bd49beab9` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_ablation_20260322_215639/largest_component_eta_analysis/relation_fulfillment.jsonl` | 32680 | `75f7e4f5b54dadc792295d403cb1fa2ff02a724851d9485f48c57724e33d60c4` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_ablation_20260322_215639/pruned_graph.jsonl` | 1569425 | `a357092916a251151634d86c191d3dc3cb69af9e706933e62f2211283310ee56` | 17683 | True | 17683 | 17683 | 139 | 17638 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_revised_density_aware_20260423_124515/eta_analysis/relation_fulfillment.jsonl` | 32829 | `dbe25e21ffc3fa9ce2386b4cb20cb1c17e97e7144c5088af36bfb560eae0c6ca` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_revised_density_aware_20260423_124515/largest_component_eta_analysis/relation_fulfillment.jsonl` | 32829 | `dbe25e21ffc3fa9ce2386b4cb20cb1c17e97e7144c5088af36bfb560eae0c6ca` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_revised_density_aware_20260423_124515/pruned_graph.jsonl` | 2165646 | `12ea709097eb48116c5c372d1e2af3b6662e7cdebe64b1cd6179cce8a88a8f7d` | 24682 | True | 24682 | 24682 | 139 | 24637 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_revised_density_aware_RunA_conservative_20260423_110608/eta_analysis/relation_fulfillment.jsonl` | 32829 | `dbe25e21ffc3fa9ce2386b4cb20cb1c17e97e7144c5088af36bfb560eae0c6ca` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_revised_density_aware_RunA_conservative_20260423_110608/pruned_graph.jsonl` | 2165646 | `12ea709097eb48116c5c372d1e2af3b6662e7cdebe64b1cd6179cce8a88a8f7d` | 24682 | True | 24682 | 24682 | 139 | 24637 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_revised_density_aware_RunB_moderate_1_20260423_114813/eta_analysis/relation_fulfillment.jsonl` | 32829 | `dbe25e21ffc3fa9ce2386b4cb20cb1c17e97e7144c5088af36bfb560eae0c6ca` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_revised_density_aware_RunB_moderate_1_20260423_114813/pruned_graph.jsonl` | 2165646 | `12ea709097eb48116c5c372d1e2af3b6662e7cdebe64b1cd6179cce8a88a8f7d` | 24682 | True | 24682 | 24682 | 139 | 24637 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_revised_density_aware_RunB_moderate_2_20260423_120313/pruned_graph.jsonl` | 2165646 | `12ea709097eb48116c5c372d1e2af3b6662e7cdebe64b1cd6179cce8a88a8f7d` | 24682 | True | 24682 | 24682 | 139 | 24637 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_balance_prune_revised_density_aware_RunB_moderate_3_20260423_121214/pruned_graph.jsonl` | 2163671 | `7238e14ab0e5a5f0ee23221c4fa8e7c7ec5b613f9364a63d32b7fe0a516d381b` | 24659 | True | 24659 | 24659 | 139 | 24614 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/eta_analysis/relation_fulfillment.jsonl` | 32922 | `efc85aaf8e5aae14cd93c0807963d57a30494148b06b935fecbcb0701c87df4f` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/largest_component_eta_analysis/relation_fulfillment.jsonl` | 32922 | `efc85aaf8e5aae14cd93c0807963d57a30494148b06b935fecbcb0701c87df4f` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl` | 2127003 | `e01d7137c1dbcd790082825a025cade7198a957b3c936f0d9b5b3f0b33780b73` | 24223 | True | 24223 | 24223 | 139 | 24178 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/baseline_safe/eta_analysis/relation_fulfillment.jsonl` | 32840 | `b27aa06068b7101f816d6b0b3dc90e6604bbdc5dda2ecdbc14d3ffc3d77f7302` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/baseline_safe/largest_component_eta_analysis/relation_fulfillment.jsonl` | 32840 | `b27aa06068b7101f816d6b0b3dc90e6604bbdc5dda2ecdbc14d3ffc3d77f7302` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/baseline_safe/pruned_graph.jsonl` | 2163671 | `7238e14ab0e5a5f0ee23221c4fa8e7c7ec5b613f9364a63d32b7fe0a516d381b` | 24659 | True | 24659 | 24659 | 139 | 24614 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/density_loosen/eta_analysis/relation_fulfillment.jsonl` | 32854 | `de98a1fcd9d1fee441a335879cff62139ae8e79d5cab02d9d6fdf5e5fdcd1b04` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/density_loosen/largest_component_eta_analysis/relation_fulfillment.jsonl` | 32854 | `de98a1fcd9d1fee441a335879cff62139ae8e79d5cab02d9d6fdf5e5fdcd1b04` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/density_loosen/pruned_graph.jsonl` | 2152102 | `6c4969add65ca1587a95b4ec5937738935667cf990d558dcb86cc77ea0bca146` | 24522 | True | 24522 | 24522 | 139 | 24477 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/p31_floor_relax/eta_analysis/relation_fulfillment.jsonl` | 32848 | `1a6d343e1fa97027f18f6310578cec3108c57955643f240e9539adaa2dbd11df` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/p31_floor_relax/largest_component_eta_analysis/relation_fulfillment.jsonl` | 32848 | `1a6d343e1fa97027f18f6310578cec3108c57955643f240e9539adaa2dbd11df` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/p31_floor_relax/pruned_graph.jsonl` | 2153082 | `bbad9c0b9860e9fc72d09cb215e00d14a7f1f736911e1a838cfc75250348e496` | 24534 | True | 24534 | 24534 | 139 | 24489 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/stronger_balance/eta_analysis/relation_fulfillment.jsonl` | 32865 | `a5dad8b63e76d10a402b85d7348e0ff784b6aca92cf6616842692764f05b851e` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/stronger_balance/largest_component_eta_analysis/relation_fulfillment.jsonl` | 32865 | `a5dad8b63e76d10a402b85d7348e0ff784b6aca92cf6616842692764f05b851e` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/stronger_balance/pruned_graph.jsonl` | 2150430 | `5fbf3d2f1be4e5c423e79c7cb8c5f09c997cb849ad336cb60110369d1f98056d` | 24502 | True | 24502 | 24502 | 139 | 24457 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/structural_softening/eta_analysis/relation_fulfillment.jsonl` | 32895 | `a1f8d43629de468228c972973d33341b1eb9ae108bee4b3a999df2406bda63fe` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/structural_softening/largest_component_eta_analysis/relation_fulfillment.jsonl` | 32895 | `a1f8d43629de468228c972973d33341b1eb9ae108bee4b3a999df2406bda63fe` | 139 | True | 0 |  |  |  | against: eta/audit rows, not h/r/t graph triples. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/structural_softening/pruned_graph.jsonl` | 2137720 | `b6167baad85a24618f235f3ac14a6408916e1a97bd5a91c6210ad6e32d8c0068` | 24350 | True | 24350 | 24350 | 139 | 24305 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage2_branch_sweep_20260424_095629/core_density_first/stage2_graph.jsonl` | 1906984 | `14f9bb9bfb576dd1f00dec8f9e95a2f6e8e17fee6464d84f4547f2d4d791d65a` | 21850 | True | 21850 | 21850 | 139 | 21806 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage2_branch_sweep_20260424_095629/core_two_path_first/stage2_graph.jsonl` | 1907012 | `fcc5a715bb650b03a660e57a766cf6c2c224ef195d882ffb272a821f21193eac` | 21850 | True | 21850 | 21850 | 139 | 21806 | against: downstream experimental/pruned graph artifact; line count and provenance do not match the Stage11 input. |

## Inferred Reconstruction Evidence

Verified facts:

- `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl` contains 24670 unique triples.
- `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/state.json` contains 6705 `added_core_triples` records, parsed as 6705 unique triples.
- All parsed `added_core_triples` are present in Stage11 `graph_output.jsonl`: `True`.
- `graph_output.jsonl` minus parsed `added_core_triples` yields 17965 unique triples and 139 unique relations.

Evidence-based inference: the missing Stage11 input can likely be reconstructed from Stage11 output minus recorded Stage11 additions. This is not equivalent to finding the original local input file because the original file SHA256 and original record ordering/format remain unknown.

## Path Translation Manifest v2

Created controlled investigation manifest: `artifacts/final_graph/selected_final_graph/rebuild/path_translation_manifest.v2.json`

Status recorded there: `unresolved_after_broader_search` for the pre-Stage11 input graph; allocation mapping unchanged from v1.

## Final Status

- Stale pre-Stage11 path status: **unresolved**.
- Local allocation path status: **resolved** to `src/Pruning graph/bidirectional_allocation_results5k.json`.
- No Stage11/Stage12 manifests were modified.
- No graph artifacts were edited, copied, or generated.
