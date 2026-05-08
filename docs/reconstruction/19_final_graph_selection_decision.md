# Final Graph Selection Decision

Status: decision template and recommendation. No final graph has been selected until the human decision field below is filled. No graph was generated, no pruning was run, and `docs/reconstruction/graph_candidates.tsv` was not edited for this document.

## 1. Candidate Set Considered

| Candidate | Type | Current status | Evidence |
| --- | --- | --- | --- |
| `B0` | Graph candidate | `frozen_baseline`, not final | `docs/reconstruction/graph_candidates.tsv`; `docs/reconstruction/10_current_decision_state.md`; `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json` |
| `C1` | Graph candidate | `active_candidate_not_final` / registry `active_candidate` | `docs/reconstruction/graph_candidates.tsv`; `docs/reconstruction/10_current_decision_state.md`; `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json` |
| `C2` | Graph candidate | `generated_failed_minimum_thresholds`, rejected as final | `docs/reconstruction/graph_candidates.tsv`; `docs/reconstruction/12_C2_result_interpretation.md`; `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json` |
| `C3_probe_v1` | Feasibility probe, not a graph | `feasibility_probe_only` | `docs/reconstruction/17_C3_feasibility_probe_result.md`; `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_report.json` |

## 2. Exclusions

`C2` is excluded from final selection because it failed the surplus threshold:

- Required: `total_surplus <= 6581`.
- Actual: `total_surplus = 6675`.
- C2 did not beat C1 surplus of `6582`.
- Evidence: `docs/reconstruction/12_C2_result_interpretation.md`; `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`.

`C3_probe_v1` is excluded because it is not a graph candidate:

- No C3 graph was generated.
- No graph output was written.
- No `graph_candidates.tsv` row should be added for the probe.
- Evidence: `docs/reconstruction/17_C3_feasibility_probe_result.md`; `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_report.json`.

Full C3 bridge-rescue is not pursued with eligible pool v1:

- The probe tested 473 computed B0 bridge-like target edges requiring replacement.
- Connectivity-critical targets with feasible replacement: `0`.
- Evidence: `docs/reconstruction/17_C3_feasibility_probe_result.md`; `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_report.json`.

## 3. B0 vs C1 Comparison

| Metric | B0 | C1 | Main tradeoff | Evidence |
| --- | ---: | ---: | --- | --- |
| Unique triples | 24683 | 24223 | C1 is smaller by 460 triples | `docs/reconstruction/10_current_decision_state.md`; `docs/reconstruction/18_final_graph_decision_state_after_C3_probe.md`; B0/C1 evaluator reports under `docs/reconstruction/graph_candidate_reports/` |
| Unique entities | 21893 | 21893 | Tie | Same evidence as above |
| Unique relations | 139 | 139 | Tie | Same evidence as above |
| Weak component count | 1 | 1 | Tie; both preserve weak connectivity | Same evidence as above |
| Allocated relations observed | 139 | 139 | Tie; both preserve allocated relation coverage | Same evidence as above |
| Zero allocated relations | 0 | 0 | Tie | Same evidence as above |
| Total deficit | 2019 | 2359 | B0 is better by 340 | Same evidence as above |
| Total surplus | 6702 | 6582 | C1 is better by 120 | Same evidence as above |
| Duplicate triple count | 0 | 0 | Tie | Same evidence as above |

Summary:

- B0 has lower deficit.
- C1 has lower surplus and fewer triples.
- C1 preserves connectivity and relation coverage, but worsens deficit.
- B0 is more conservative because it avoids promoting Stage13 pruning to the final reported graph unless the thesis explicitly accepts Stage13 as part of the reported workflow.

## 4. Decision Options

### Option A: Select B0

Select:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`

This option is defensible if the thesis prioritizes:

- lower quota deficit,
- conservative traceability,
- avoiding the need to defend Stage13 pruning as the reported final graph step,
- and keeping the final artifact closer to the Stage12 repaired largest component.

Main limitation:

- B0 has higher total surplus than C1: `6702` vs `6582`.

Evidence:

- `docs/reconstruction/10_current_decision_state.md`
- `docs/reconstruction/18_final_graph_decision_state_after_C3_probe.md`
- `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`

### Option B: Select C1

Select:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl`

This option is defensible if the thesis explicitly prioritizes:

- lower surplus,
- lower graph density,
- and accepts Stage13 pruning as part of the reported final pipeline.

Main limitation:

- C1 worsens total deficit relative to B0: `2359` vs `2019`.

Evidence:

- `docs/reconstruction/10_current_decision_state.md`
- `docs/reconstruction/18_final_graph_decision_state_after_C3_probe.md`
- `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`
- `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.report.json`

## 5. Recommendation

Recommendation: select B0 unless the thesis explicitly prioritizes surplus/density reduction over deficit minimization.

Reason:

- B0 has lower total deficit: `2019` vs C1 `2359`.
- C1's surplus reduction is modest: `6702 -> 6582`, a reduction of 120.
- C1 worsens deficit by 340.
- Later C2/C3 investigations did not produce a better graph alternative.
- C2 is rejected as final because it failed the surplus threshold.
- C3 did not produce a graph candidate, and the feasibility probe did not support full bridge-rescue with eligible pool v1.
- B0 is therefore the more conservative and easier-to-defend final artifact unless Stage13 pruning is explicitly accepted as the reported final step.

Evidence:

- B0/C1 metrics: `docs/reconstruction/10_current_decision_state.md`; `docs/reconstruction/18_final_graph_decision_state_after_C3_probe.md`
- C2 rejection: `docs/reconstruction/12_C2_result_interpretation.md`
- C3 probe result: `docs/reconstruction/17_C3_feasibility_probe_result.md`
- Registry context: `docs/reconstruction/graph_candidates.tsv`

## 6. Human Decision Field

Selected final graph: B0

Decision date: 2026-05-08

Rationale:
B0 is selected as the final reported graph because it preserves weak connectivity, keeps all 139 allocated relations observed, has zero allocated-relation absence, and has the lower total quota deficit among the remaining defensible graph candidates. C1 reduces surplus and graph size, but the surplus reduction is modest relative to the increase in deficit. C2 was rejected after failing the surplus threshold, and the C3 feasibility probe did not support a full bridge-rescue candidate with eligible pool v1.

Limitations:
B0 has higher total surplus than C1 and remains affected by generic-relation dominance. Stage13 and later C2/C3 analyses are therefore reported as post hoc candidate investigations rather than as the selected final graph.

Thesis wording implication:
The thesis should describe the final graph as the Stage12 repaired largest component. Stage13 should be described as a later candidate analysis that reduced surplus modestly but increased quota deficit, and was therefore not selected as the final reported graph.

## 7. Safe Thesis Wording

### If B0 Is Selected

Suggested wording:

> The final reported graph is the Stage12 repaired largest component (`B0`). It preserves weak connectivity, contains 139 observed allocated relations with zero allocated-relation absence, and has the lower total quota deficit among the controlled final candidates considered. Stage13 and later experiments are reported as post hoc candidate analyses rather than as the selected final graph.

Use only with evidence:

- `docs/reconstruction/graph_candidates.tsv`
- `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`
- `docs/reconstruction/18_final_graph_decision_state_after_C3_probe.md`

### If C1 Is Selected

Suggested wording:

> The final reported graph is the Stage13 `aggressive_but_guarded` pruning candidate (`C1`). It preserves weak connectivity and all 139 allocated relations while reducing total surplus and graph size relative to the Stage12 baseline. This choice accepts a higher total quota deficit in exchange for lower surplus/density and treats Stage13 pruning as part of the reported final candidate-selection workflow.

Use only if the human decision explicitly accepts Stage13 as part of the reported final pipeline.

Use only with evidence:

- `docs/reconstruction/graph_candidates.tsv`
- `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`
- `docs/reconstruction/10_current_decision_state.md`
- `docs/reconstruction/18_final_graph_decision_state_after_C3_probe.md`
- `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.report.json`

## 8. Unsafe Claims

Do not claim:

- C3 was generated.
- `C3_probe_v1` is a graph candidate.
- Full end-to-end reproducibility has been achieved unless environment and upstream frozen inputs are resolved.
- Offline Phase II execution produced the final graph unless direct evidence is added.
- C1 is final unless the human decision field selects C1.
- B0 is final unless the human decision field selects B0.
- C2 is a final candidate.
- The final graph choice is purely automatic or metric-free; the B0/C1 tradeoff requires a thesis-level reporting decision.
