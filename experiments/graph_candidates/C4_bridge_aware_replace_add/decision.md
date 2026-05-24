# C4 Bridge-Aware Replace/Add Decision

## Status

Decision: do not generate a C4 graph under the current evidence.

`C4_bridge_aware_replace_add` remains a planned/probe-only branch. It is not a graph candidate, and `candidate_registry.v1.json` should not be updated for C4 at this stage.

## Evidence

- Probe report:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/probe_report.json`
- Replacement-pool bridge-cut audit:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/replacement_pool_bridge_cut_audit.json`
- Local cut-crossing candidate search:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/local_cut_crossing_candidate_search.json`
- Reconstruction decision audit:
  `docs/reconstruction/56_C4_branch_decision_audit.md`

## Findings

The C4 probe tested 200 surplus target-generic bridge targets from `P31`, `P279`, and `P131`. All 200 tested targets were connectivity-critical, and no feasible replacement was found from the eligible replacement pool.

C4.1 showed that the eligible replacement pool contained 990 rows, including 612 rows with both endpoints in B0, but none crossed any tested bridge cut. The original pool failed on bridge-cut crossing coverage.

C4.2 broadened the search to local frozen evidence. It found 629 cut-crossing candidate rows and 625 unique cut-crossing candidates, including 106 allocated cut-crossing rows. However, zero allocated candidate-cut pairs were surplus-reducing. The surplus-reducing cut-crossing evidence was unallocated.

## Decision

Do not implement a strict C4 graph generator from the current evidence.

Strict C4 replacement requires allocated, cut-crossing, non-duplicate, surplus-improving replacements that preserve the B0 hard constraints. Current frozen evidence does not provide such candidates for the tested bridge cuts.

## Next Branch Options

| Option | Decision |
| --- | --- |
| Stop strict C4 replacement branch | Recommended now. |
| Build a new allocated cut-aware pool source | Possible only if frozen and audited before graph generation. |
| Allow unallocated bridge evidence as auxiliary connectivity support | Possible new branch, but not strict C4. |
| Run live WDQS exploratory search | Exploratory only; non-canonical unless frozen and audited. |
| Switch to controlled relation addition | Plausible next experimental branch if constraints are specified first. |

## Guardrails

- No graph candidate has been generated.
- `outputs/graph.jsonl` should not exist for C4.
- `candidate_registry.v1.json` should not be updated for C4.
- C4 evidence should be described as negative/probe evidence, not as a candidate result.
