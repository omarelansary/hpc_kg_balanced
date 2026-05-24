# C4 Branch Decision Audit

## Decision Summary

Recommended decision: do not generate a C4 graph under the current evidence.

C4 should remain negative/probe evidence unless a new candidate source can produce replacements that are simultaneously:

- cut-crossing for the tested B0 bridge cuts,
- allocated under the canonical 5k allocation,
- non-duplicate with respect to B0,
- surplus-improving when paired with removal of a target `P31`, `P279`, or `P131` bridge edge,
- and compatible with the hard graph constraints.

Under strict allocated-only replacement, a graph generator is not justified.

## Evidence Inputs

- C4 config:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/configs/config.template.json`
- C4 probe report:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/probe_report.json`
- C4.1 replacement-pool bridge-cut audit:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/replacement_pool_bridge_cut_audit.json`
- C4.2 local cut-crossing candidate search:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/local_cut_crossing_candidate_search.json`
- Candidate registry:
  `artifacts/final_graph/selected_final_graph/rebuild/candidate_registry.v1.json`

## 1. What C4 Tested

C4 was scaffolded as `C4_bridge_aware_replace_add`, using B0 as the parent graph and the canonical 5k allocation. The configured strategy is `bridge_aware_remove_replace_controlled_addition`, with live WDQS and LLM use disabled.

The bounded C4 probe tested the first 200 surplus target-generic bridge targets from:

- `P31`
- `P279`
- `P131`

It loaded 990 eligible replacement candidates from the frozen C3 eligible pool and tested independent remove/replace feasibility. The probe required weak connectivity to remain one component, no duplicate triples, no zero allocated relations, and all 139 allocated relations still observed.

Probe outcome:

| Measure | Count |
| --- | ---: |
| Target edges tested | 200 |
| Deletion-safe targets | 0 |
| Connectivity-critical targets | 200 |
| Replacement candidates loaded | 990 |
| Feasible safe deletions | 0 |
| Connectivity-critical targets with feasible replacement | 0 |
| Greedy non-reuse candidate count | 0 |

The C4 probe did not produce a graph candidate.

## 2. Why the Original Replacement Pool Failed

C4.1 audited the eligible replacement pool against the same tested bridge cuts.

Key counts:

| Measure | Count |
| --- | ---: |
| Tested bridge targets | 200 |
| Replacement rows loaded | 990 |
| Replacement rows with both endpoints in B0 | 612 |
| Replacement rows with one endpoint in B0 | 378 |
| Replacement rows crossing any tested cut | 0 |
| Cut-crossing allocated rows | 0 |
| Cut-crossing balance-improving rows | 0 |

The original replacement pool failed primarily because of bridge-cut crossing coverage. It was not empty, and many rows had both endpoints in B0, but none connected the two sides of any tested bridge cut. Because no replacement crossed a cut, later filters such as allocation status and balance delta were not the decisive blockers for the eligible pool.

## 3. What Broader Local Frozen Evidence Added

C4.2 broadened the search to local frozen candidate sources:

- Stage12 graph output,
- Stage11 graph output,
- Stage2 candidate shards,
- frozen candidate pools.

It excluded triples already present in B0 and required both endpoints to be in B0.

Key counts:

| Measure | Count |
| --- | ---: |
| Cuts tested | 200 |
| Cut-crossing candidate rows found | 629 |
| Unique cut-crossing candidates | 625 |
| Allocated cut-crossing candidate rows | 106 |
| Unique allocated cut-crossing candidates | 102 |
| Surplus-reducing candidate-cut pairs | 546 |
| Allocated surplus-reducing candidate-cut pairs | 0 |
| Unallocated surplus-reducing candidate-cut pairs | 546 |

C4.2 changes the diagnosis: frozen local evidence does contain bridge-cut-spanning triples, but the surplus-reducing cut-crossing candidates are unallocated. Allocated cut-crossing candidates exist, but they do not improve surplus under the strict remove/replace objective.

Stage11 and Stage12 graph outputs do not add novel replacement evidence because relevant graph-output rows are already in B0.

## 4. Strict Allocated-Only Generator Decision

A strict C4 graph generator is not justified from the current evidence.

Under the current hard constraints, a replacement must be allocated and balance-improving. C4.2 found zero allocated surplus-reducing candidate-cut pairs across the first 200 tested cuts. Generating a graph from the current pool would therefore either reproduce the zero-feasibility outcome or require changing the rules.

Do not generate a C4 graph from the current evidence.

## 5. What Would Be Required to Continue C4

Continuing C4 requires one of the following changes:

1. A new allocated cut-aware candidate source.
   Candidate collection would need to search specifically across the two components exposed by each target bridge removal and restrict to allocated relations likely to reduce surplus or preserve deficit.

2. A rule change permitting unallocated bridge evidence as auxiliary connectivity support.
   This would no longer be strict allocated-only replacement. It would need a separate candidate ID and evaluation policy because it changes the relation coverage objective.

3. A non-canonical exploratory live search.
   Live WDQS could search for cut-crossing evidence, but any result would be non-canonical until frozen, hashed, audited, and made reproducible locally.

4. A branch away from replacement toward controlled relation addition.
   If replacement cannot reduce surplus without breaking connectivity, a future branch could test whether carefully bounded additions improve connectivity support before later pruning.

## 6. Possible Next Branches

| Option | Classification | Decision |
| --- | --- | --- |
| A. Stop strict C4 replacement branch | Recommended now | Keep C4 as negative/probe evidence. Do not generate a graph under current evidence. |
| B. Build a new allocated cut-aware pool source | Possible future work | Only worth doing if candidate generation can be kept frozen, audited, and allocation-constrained. |
| C. Allow unallocated bridge evidence as auxiliary connectivity support | Possible new branch | Requires explicit rule change and separate candidate identity; not strict C4. |
| D. Run live WDQS exploratory search | Non-canonical exploration | Must be labelled exploratory until results are frozen and audited. |
| E. Switch to relation-addition branch | Possible next experimental family | Should be designed as controlled addition/auxiliary-connectivity, not as evidence that C4 succeeded. |

## Recommendation

Do not continue the strict C4 bridge-aware replacement branch with the current frozen evidence.

C4 should be recorded as negative/probe evidence:

- the eligible replacement pool had no cut-crossing candidates for the tested bridge cuts;
- broader frozen local evidence had cut-crossing candidates, but strict allocated surplus-improving replacements were absent;
- no graph candidate was generated;
- no registry update is warranted.

Continue only if a new candidate source can produce allocated, cut-crossing, surplus-improving replacements. Otherwise, move to a controlled relation-addition or auxiliary-connectivity branch with explicit constraints and a new candidate identity.
