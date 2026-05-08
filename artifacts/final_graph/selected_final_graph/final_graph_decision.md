# Final Graph Decision

Selected final graph: `B0`

Selected graph path:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`

Selected graph SHA256:

`c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`

Allocation:

`src/Pruning graph/bidirectional_allocation_results5k.json`

Allocation SHA256:

`a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

## Why Selected

B0 is selected as the final reported graph because it preserves weak connectivity, keeps all 139 allocated relations observed, has zero allocated-relation absence, and has the lower total quota deficit among the remaining defensible graph candidates. C1 reduces surplus and graph size, but the surplus reduction is modest relative to the increase in deficit. C2 was rejected after failing the surplus threshold, and the C3 feasibility probe did not support a full bridge-rescue candidate with eligible pool v1.

## Limitations

B0 has higher total surplus than C1 and remains affected by generic-relation dominance. Stage13 and later C2/C3 analyses are therefore reported as post hoc candidate investigations rather than as the selected final graph.

## Why Other Candidates Were Not Selected

- `C1` was not selected after the final B0/C1 tradeoff decision. Evidence: `docs/reconstruction/19_final_graph_selection_decision.md`; `docs/reconstruction/18_final_graph_decision_state_after_C3_probe.md`.
- `C2` was rejected as final because it failed the surplus threshold and did not beat C1 surplus. Evidence: `experiments/graph_candidates/C2_targeted_generic_pruning/decision.md`; `docs/reconstruction/12_C2_result_interpretation.md`.
- `C3_probe_v1` was not selected because it is not a graph candidate. The probe found 0 feasible replacements for 473 tested connectivity-critical bridge-like target edges. Evidence: `docs/reconstruction/17_C3_feasibility_probe_result.md`.

## Safe Thesis Wording

The thesis should describe the final graph as the Stage12 repaired largest component. Stage13 should be described as a later candidate analysis that reduced surplus modestly but increased quota deficit, and was therefore not selected as the final reported graph.

## Unsafe Claims

Do not claim:

- C3 was generated.
- `C3_probe_v1` is a graph candidate.
- Full end-to-end reproducibility has been achieved unless environment and upstream frozen inputs are resolved.
- Offline Phase II execution produced the final graph unless direct evidence is added.
- Nonselected candidates are final.

## Registration Notes

- No graph artifact was modified.
- The selected graph file was not copied.
- This package records hashes, metrics, and decision evidence only.
