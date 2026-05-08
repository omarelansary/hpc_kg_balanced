# Final Graph Decision State After C3 Probe

Status: decision-state summary only. No final graph has been selected. No C3 graph has been generated. `C3_probe_v1` is evidence, not a graph candidate.

## 1. Current Candidates

| ID | Status | Graph candidate? | Role | Evidence |
| --- | --- | --- | --- | --- |
| `B0` | `frozen_baseline` | Yes | Stage12 largest-component baseline | `docs/reconstruction/graph_candidates.tsv`; `docs/reconstruction/10_current_decision_state.md`; `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json` |
| `C1` | `active_candidate_not_final` / registry `active_candidate` | Yes | Stage13 `aggressive_but_guarded` pruning candidate | `docs/reconstruction/graph_candidates.tsv`; `docs/reconstruction/10_current_decision_state.md`; `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json` |
| `C2` | `generated_failed_minimum_thresholds` | Yes, rejected | Deletion-only targeted generic pruning from B0 | `docs/reconstruction/graph_candidates.tsv`; `docs/reconstruction/12_C2_result_interpretation.md`; `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json` |
| `C3_probe_v1` | `feasibility_probe_only` | No | Remove-and-replace feasibility evidence | `docs/decisions/graph_candidate_decision_log.md`; `docs/reconstruction/17_C3_feasibility_probe_result.md`; `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_report.json` |

Registry note:

- `docs/reconstruction/graph_candidates.tsv` contains graph candidates `B0`, `C1`, and `C2`.
- `C3_probe_v1` is recorded in `docs/decisions/graph_candidate_decision_log.md`, not in `docs/reconstruction/graph_candidates.tsv`, because no C3 graph candidate was generated.

## 2. Candidate Metrics

### B0

B0 is the frozen Stage12 largest-component baseline.

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

- `docs/reconstruction/10_current_decision_state.md`
- `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`

### C1

C1 is the Stage13 `aggressive_but_guarded` pruning candidate. It is not final.

| Metric | Value |
| --- | ---: |
| Unique triples | 24223 |
| Duplicate triple count | 0 |
| Unique entities | 21893 |
| Unique relations | 139 |
| Weak component count | 1 |
| Largest weak component ratio | 1.0 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total deficit | 2359 |
| Total surplus | 6582 |

Compared with B0:

- C1 reduces total surplus by 120: `6702 -> 6582`.
- C1 worsens total deficit by 340: `2019 -> 2359`.
- C1 preserves weak connectivity, relation coverage, and duplicate-free graph content.

Evidence:

- `docs/reconstruction/10_current_decision_state.md`
- `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`
- `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.report.json`

### C2

C2 is a generated graph candidate, but it is rejected as final and kept as exploratory negative evidence.

| Metric | Value |
| --- | ---: |
| Accepted deletions | 27 |
| Weak component count | 1 |
| Largest weak component ratio | 1.0 |
| Duplicate triples | 0 |
| Unique relations | 139 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total deficit | 2019 |
| Total surplus | 6675 |

C2 rejection reason:

- C2 failed the configured minimum surplus threshold.
- Required: `total_surplus <= 6581`.
- Actual: `total_surplus = 6675`.
- C2 did not beat C1 surplus of `6582`.
- C2 accepted only 27 deletions and recorded `75893` `would_disconnect_graph` rejections.

Evidence:

- `docs/reconstruction/12_C2_result_interpretation.md`
- `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json`
- `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`

### C3 Probe

`C3_probe_v1` is not a graph candidate. It is a feasibility probe against eligible replacement pool v1.

| Probe metric | Value |
| --- | ---: |
| Target edges tested | 500 |
| C2 accepted deletion targets tested | 27 |
| Computed B0 bridge-like target edges tested | 473 |
| Replacement candidates loaded | 990 |
| Replacement pair tests performed | 495000 |
| Safe deletions without replacement | 27 |
| Targets requiring replacement | 473 |
| Connectivity-critical targets with feasible replacement | 0 |
| Total feasible swaps found | 20493 |

Interpretation:

- Feasible swaps exist only for deletion-safe targets.
- Eligible pool v1 did not rescue any of the 473 tested connectivity-critical bridge-like target edges.
- Full bridge-rescue C3 is not recommended with eligible pool v1.

Evidence:

- `docs/reconstruction/17_C3_feasibility_probe_result.md`
- `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_report.json`
- `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_summary.md`

## 3. Decision Implications

Verified decisions:

- C2 is rejected as a final graph candidate.
- C2 is retained as exploratory negative evidence.
- `C3_probe_v1` is evidence only and not a graph candidate.
- No `graph_candidates.tsv` row should be added for `C3_probe_v1`.

Evidence-based implications:

- Full C3 bridge-rescue is not recommended with eligible pool v1.
- C3a bounded safe-edge swap is optional exploratory work only.
- C3a must not be framed as solving the C2 connectivity blocker, because the probe found zero feasible replacements for the tested connectivity-critical bridge-like targets.
- The final graph decision currently remains between B0 and C1.

Evidence:

- `docs/reconstruction/12_C2_result_interpretation.md`
- `docs/reconstruction/13_C3_remove_replace_experiment_plan.md`
- `docs/reconstruction/14_C3_replacement_pool_audit.md`
- `docs/reconstruction/15_C3_replacement_pool_v1_freeze_report.md`
- `docs/reconstruction/16_C3_eligible_replacement_pool_v1_report.md`
- `docs/reconstruction/17_C3_feasibility_probe_result.md`
- `docs/decisions/graph_candidate_decision_log.md`

## 4. Recommendation

Do not continue full C3 bridge-rescue unless replacement-pool design changes materially.

Current practical choice:

| Choice | When it is defensible | Main tradeoff |
| --- | --- | --- |
| Choose `B0` | Thesis priority is lower deficit, conservative traceability, and avoiding an extra pruning stage as the reported final step | Higher surplus and denser graph than C1 |
| Choose `C1` | Thesis priority is lower surplus/density and Stage13 pruning is accepted as part of the reported pipeline | Worse deficit than B0 and requires explicitly defending Stage13 as reported workflow |
| Choose `C2` | Not recommended | Rejected: failed surplus threshold and did not beat C1 |
| Choose `C3_probe_v1` | Not allowed | It is not a graph candidate |

Clear recommendation:

- Do not choose C2.
- Do not treat `C3_probe_v1` as a candidate graph.
- Do not claim C3 was generated.
- Do not claim a final graph has been selected.
- Decide between B0 and C1 based on the thesis priority and what can be defended as the reported pipeline.

## 5. Open Human Decision

The remaining thesis-level decision is not technical automation; it is a reporting choice.

The thesis author must decide:

1. Whether Stage13 is allowed as the reported final pipeline step.
2. Whether accepting worse deficit for lower surplus is justified.
3. Whether the final graph should prioritize quota deficit or surplus reduction.

Decision framing:

- If quota deficit is the stronger thesis criterion, B0 is currently more defensible.
- If surplus/density reduction is the stronger thesis criterion, and Stage13 can be defended as part of the reported workflow, C1 is currently more defensible.
- If neither tradeoff is acceptable, further work must materially change the replacement-pool design or the graph-construction objective; eligible pool v1 and `C3_probe_v1` do not currently justify proceeding with full C3 bridge-rescue.

## 6. Claims Not Supported

Unsafe claims after the C3 probe:

- A final graph has been selected.
- C3 was generated.
- C3 improves B0 or C1.
- C3 solves the C2 connectivity blocker.
- `C3_probe_v1` is a graph candidate.
- The final graph is reproducible from frozen inputs end to end.

Safe claims after the C3 probe:

- B0, C1, and C2 have duplicate-safe evaluator reports.
- C2 was rejected as final and retained as exploratory negative evidence.
- A local eligible replacement pool was derived from Stage11/Stage12 evidence.
- A feasibility probe found no feasible replacement for 473 tested connectivity-critical bridge-like target edges using eligible pool v1.
- The unresolved final-graph decision remains B0 versus C1.
