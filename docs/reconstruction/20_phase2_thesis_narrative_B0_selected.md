# Phase II Thesis Narrative: B0 Selected

Status: thesis-ready narrative draft. This document does not generate graphs, run pruning, or modify graph artifacts.

## 1. Final Graph Statement

The selected final reported graph is `B0`.

`B0` is the Stage12 repaired largest component:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`

Final graph SHA256:

`c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`

The final graph is registered in:

- `artifacts/final_graph/selected_final_graph/final_graph_manifest.json`
- `artifacts/final_graph/selected_final_graph/final_graph_metrics.json`
- `artifacts/final_graph/selected_final_graph/final_graph_decision.md`

Selected B0 metrics:

| Metric | Value |
| --- | ---: |
| Unique triples | 24683 |
| Duplicate triple count | 0 |
| Unique entities | 21893 |
| Unique relations | 139 |
| Weak component count | 1 |
| Largest weak component ratio | 1.0 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total deficit | 2019 |
| Total surplus | 6702 |

Evidence:

- `artifacts/final_graph/selected_final_graph/final_graph_manifest.json`
- `artifacts/final_graph/selected_final_graph/final_graph_metrics.json`
- `artifacts/final_graph/selected_final_graph/final_graph_decision.md`

## 2. Methodology Narrative

Phase II consumed the relation-level allocation produced by the preceding allocation stage. The allocation file assigned integer target quotas to selected relations and therefore supplied the quota objective used to audit graph construction outcomes. In the finalized artifact package, the canonical allocation is:

`src/Pruning graph/bidirectional_allocation_results5k.json`

Allocation SHA256:

`a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

The graph construction and repair workflow produced a connected Stage12 candidate. The selected final graph is the Stage12 repaired largest component, `B0`, which preserves weak connectivity and observes all 139 allocated relations with zero allocated-relation absence. This graph was selected after comparing B0 against later controlled candidates and probes.

This wording intentionally does not claim that the intended offline Phase II design was fully proven by execution logs. The defensible claim is narrower: the final reported graph is the Stage12 repaired largest component, and it is selected based on the reconstructed candidate evidence and duplicate-safe evaluation reports.

Evidence:

- `docs/reconstruction/18_final_graph_decision_state_after_C3_probe.md`
- `docs/reconstruction/19_final_graph_selection_decision.md`
- `artifacts/final_graph/selected_final_graph/final_graph_manifest.json`
- `artifacts/final_graph/selected_final_graph/final_graph_metrics.json`

## 3. Candidate Analysis Paragraph

Later candidates were treated as post hoc candidate analyses rather than final graph outputs. `C1`, the Stage13 `aggressive_but_guarded` pruning candidate, reduced graph size and surplus relative to B0, but increased total deficit. `C2`, a controlled deletion-only targeted generic-pruning candidate, preserved connectivity and relation coverage but failed the minimum surplus threshold and was rejected as final. A subsequent C3 feasibility probe tested remove-and-replace feasibility using an eligible replacement pool, but found zero feasible replacements for 473 tested connectivity-critical bridge-like target edges. Therefore, later C1/C2/C3 analyses did not supersede B0 as the selected final reported graph.

Evidence:

- C1 comparison: `docs/reconstruction/18_final_graph_decision_state_after_C3_probe.md`
- C2 rejection: `docs/reconstruction/12_C2_result_interpretation.md`
- C3 probe result: `docs/reconstruction/17_C3_feasibility_probe_result.md`
- Final decision: `artifacts/final_graph/selected_final_graph/final_graph_decision.md`

## 4. Limitations

B0 remains affected by generic-relation dominance and has higher total surplus than C1. The final graph decision therefore prioritizes lower deficit, conservative traceability, weak connectivity, and complete allocated-relation coverage over the modest surplus reduction achieved by Stage13 pruning.

Full end-to-end reproducibility also remains conditional on resolving environment and upstream frozen-input evidence. The final artifact package records the selected graph hash, allocation hash, evaluator report, metrics, and decision rationale, but it does not by itself prove that every upstream live-data or environment-dependent step can be rerun exactly.

Unsafe claims:

- Do not claim C3 was generated.
- Do not claim C1, C2, or C3 is final.
- Do not claim full end-to-end reproducibility unless environment and upstream frozen inputs are resolved.
- Do not claim offline Phase II execution unless additional direct evidence is added.

Evidence:

- `docs/reconstruction/19_final_graph_selection_decision.md`
- `docs/reconstruction/17_C3_feasibility_probe_result.md`
- `artifacts/final_graph/selected_final_graph/final_graph_decision.md`

## 5. Safe LaTeX-Ready Wording

### Concise Paragraph

The final reported graph is the Stage12 repaired largest component, denoted B0. B0 contains 24,683 unique triples over 21,893 entities and 139 relations, forms a single weakly connected component, observes all 139 allocated relations, and has zero allocated-relation absence. It was selected over later candidates because it has the lower total quota deficit among the defensible graph candidates, while later pruning and remove-and-replace investigations did not produce a stronger final artifact.

### Methodology Subsection

Phase II used the relation-level allocation output as the quota reference for graph construction and evaluation. The allocation file assigns integer target quotas to the selected relations, and candidate graphs were evaluated against these quotas using duplicate-safe relation counts. The graph construction and repair process produced a Stage12 repaired graph, from which the largest weakly connected component was retained as candidate B0. B0 contains 24,683 unique triples, 21,893 unique entities, and 139 unique relations. It preserves weak connectivity as a single weak component and observes all 139 allocated relations with zero allocated-relation absence. Its total quota deficit is 2,019 and its total surplus is 6,702.

After constructing B0, later candidates were evaluated as controlled post hoc analyses. The Stage13 `aggressive_but_guarded` pruning candidate reduced graph size and total surplus, but increased total deficit relative to B0. A deletion-only targeted generic-pruning candidate, C2, preserved the hard structural constraints but failed the predefined surplus threshold and was rejected as final. A subsequent remove-and-replace feasibility probe found no feasible replacements for the tested connectivity-critical bridge-like target edges using the eligible replacement pool. On this basis, B0 was selected as the final reported graph because it preserves connectivity and allocated-relation coverage while maintaining the lower total deficit among the remaining defensible candidates.

### Limitations Paragraph

The selected graph is not free of imbalance. B0 has higher total surplus than the Stage13 pruning candidate and remains affected by generic-relation dominance, especially among broad Wikidata relations. The final selection therefore reflects a conservative tradeoff: lower quota deficit, single-component connectivity, and complete allocated-relation coverage were prioritized over the modest surplus reduction achieved by later pruning. In addition, the final artifact package records hashes, metrics, and decision evidence, but full end-to-end reproducibility still depends on resolving environment details and upstream frozen-input provenance. The final selection should therefore be described as the defended final reported graph, not as proof that every upstream live-data-dependent step can be exactly rerun.
