# C3 Feasibility Probe Result

Status: evidence registration only. C3 has still not been generated. No C3 graph candidate was created, no graph file was written, no live WDQS query was made, and `docs/reconstruction/graph_candidates.tsv` should not be updated from this probe.

## Evidence

Primary probe evidence:

- Probe script: `tools/graph_candidate_generation/probe_c3_remove_replace_feasibility.py`
- Probe report: `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_report.json`
- Probe summary: `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_summary.md`

Context evidence:

- Eligible pool report: `docs/reconstruction/16_C3_eligible_replacement_pool_v1_report.md`
- C2 interpretation: `docs/reconstruction/12_C2_result_interpretation.md`
- Eligible pool: `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/eligible_replacement_candidates.jsonl`
- B0 graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Canonical allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`

## What The Probe Tested

The C3 feasibility probe tested remove-and-replace feasibility without writing any candidate graph.

| Probe metric | Value |
| --- | ---: |
| Target edges tested | 500 |
| C2 accepted deletion targets tested | 27 |
| Computed B0 bridge-like target edges tested | 473 |
| Replacement candidates loaded | 990 |
| Replacement pair tests performed | 495000 |

The probe report records that C2 rejected `would_disconnect_graph` targets were not individually recoverable: `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json` contains aggregate `would_disconnect_graph` counts, but not a per-target rejected triple list. Therefore the probe used the 27 recovered C2 accepted deletion targets plus computed B0 bridge-like `P31`/`P279`/`P131` target edges.

## Result

| Result metric | Value |
| --- | ---: |
| Safe deletions without replacement | 27 |
| Targets requiring replacement | 473 |
| Connectivity-critical targets with feasible replacement | 0 |
| Targets with at least one feasible replacement | 27 |
| Targets with no feasible replacement | 473 |
| Total feasible swaps found | 20493 |

The feasible swaps were found for deletion-safe target edges. The probe found no eligible-pool replacement for any of the 473 tested connectivity-critical bridge-like target edges.

## Interpretation

Full bridge-rescue C3 is not recommended with eligible pool v1.

Verified fact:

- `targets_requiring_replacement_with_feasible_replacement = 0` in `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_report.json`.

Evidence-based inference:

- Eligible pool v1 does not solve the C2 connectivity blocker. C2 failed because many generic deletions would disconnect the graph; this probe found that the current eligible replacement pool could not rescue any of the tested bridge-like target-generic deletions.

Feasible swaps exist only for deletion-safe targets:

- `target_deletions_already_safe_without_replacement = 27`
- `targets_with_at_least_one_feasible_replacement = 27`
- `targets_requiring_replacement = 473`
- `targets_requiring_replacement_with_feasible_replacement = 0`

Therefore bounded safe-edge swaps must not be framed as solving the C2 connectivity blocker.

## Caveat

The probe examples are independent. The same replacement edge cannot be reused blindly in a real generator. A real swap generator would need to update relation counts, duplicate state, graph connectivity, and candidate availability after every accepted swap.

The probe report explicitly states that it did not write a candidate graph and records top feasible swaps per target, not an optimized global swap sequence.

## Recommendation

Do not implement full C3 bridge-rescue using eligible pool v1.

Optional next step:

- Implement a bounded safe-edge swap experiment only as exploratory `C3a`, if the research question is whether deletion-safe generic edges can be replaced with underfilled or near-target relations.

Constraints for any optional `C3a`:

- It must be registered as exploratory, not final.
- It must not be claimed as solving bridge-like connectivity blockage.
- It must use the standard graph candidate evaluator before any accept/reject decision.
- It must not add a row to `docs/reconstruction/graph_candidates.tsv` until a graph candidate, evaluator report, and decision exist.

## Thesis Safety

No thesis final-graph claim follows from this probe.

Safe claim:

- A controlled feasibility probe found that eligible pool v1 did not provide feasible replacements for the tested connectivity-critical bridge-like `P31`/`P279`/`P131` target edges.

Unsafe claim:

- C3 exists as a generated graph.
- C3 improves B0, C1, or C2.
- C3 solves the C2 connectivity blocker.
- The thesis final graph should be updated based on this probe.

Registry decision:

- No `docs/reconstruction/graph_candidates.tsv` row should be added for this probe because no graph candidate was generated.
