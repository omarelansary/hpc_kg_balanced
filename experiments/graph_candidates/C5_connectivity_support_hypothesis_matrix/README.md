# C5 Connectivity-Support Hypothesis Matrix

Status: `planned_not_generated`

C5 is a branch scaffold for testing connectivity-support hypotheses after C4 strict allocated-only bridge-aware replacement closed as negative/probe evidence.

No graph has been generated. `outputs/graph.jsonl` should not exist. The candidate registry must not be updated until a graph exists, a standard evaluator report exists, and a human decision is recorded.

## Scope

C5 is not strict C4. C4 tested allocated replacement directly and did not find a feasible source under current evidence. C5 separates several hypotheses:

- H1: allocated observed cut-crossing replacements,
- H2: observed unallocated auxiliary support followed by pruning tests,
- H3: synthetic pattern-derived support,
- H4: live WDQS observed evidence,
- H5: LLM ranking of fixed candidate sets only.

The first implementation should be probe-only over H1 and H2. Synthetic pattern-derived triples are not enabled in the first implementation.

## Guardrails

- Do not query WDQS.
- Do not call LLMs.
- Do not generate a graph from this scaffold.
- Do not update `candidate_registry.v1.json`.
- Keep auxiliary unallocated evidence separate from canonical allocated triples.
- Keep synthetic pattern-derived evidence separate from observed evidence.

## Files

- `manifest.template.json`: branch-level scaffold manifest.
- `configs/config.template.json`: probe/generator configuration template.
- `configs/README.md`: configuration notes and first-probe boundary.

## Evidence Base

C5 is motivated by:

- `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/probe_report.json`
- `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/replacement_pool_bridge_cut_audit.json`
- `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/local_cut_crossing_candidate_search.json`
- `docs/reconstruction/56_C4_branch_decision_audit.md`
