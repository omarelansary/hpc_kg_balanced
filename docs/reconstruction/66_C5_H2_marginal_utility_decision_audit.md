# C5-H2 Marginal Utility Decision Audit

## Purpose

This audit evaluates whether C5-H2 should be registered, preserved as diagnostic evidence, continued as a diversity-aware candidate, or stopped before H3.

C5-H2 is an experimental auxiliary-connectivity branch. It adds observed unallocated auxiliary edges, removes surplus canonical B0 bridge edges, and computes canonical allocation surplus/deficit over canonical allocated edges only.

## Inputs

- `docs/reconstruction/63_C5_H2_cap_sweep.md`
- `docs/reconstruction/64_C5_H2_diversity_reranking_probe.md`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/cap_sweep/cap_sweep_report.json`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/diversity_reranking/diversity_reranking_report.json`
- `experiments/graph_candidates/C5_H2_diversity_light_cap50/` when present locally

Reference values:

- B0 triples: `24,683`
- B0 surplus: `6,702`
- B0 weak components: `1`

## Cap-Normalized Utility

Definitions:

- `surplus_reduction_ratio = abs(canonical_surplus_delta) / 6702`
- `auxiliary_cost_per_surplus_removed = auxiliary_edges_selected / abs(canonical_surplus_delta)`
- `canonical_fragmentation_per_auxiliary_edge = (canonical_only_weak_components - 1) / auxiliary_edges_selected`

| Cap | Aux edges | Surplus delta | Surplus reduction ratio | Auxiliary cost per surplus removed | Canonical-only WCC | Fragmentation per auxiliary edge | P17 share |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 10 | -10 | 0.149% | 1.000 | 9 | 0.800 | 0.300 |
| 25 | 25 | -25 | 0.373% | 1.000 | 24 | 0.920 | 0.560 |
| 50 | 50 | -50 | 0.746% | 1.000 | 49 | 0.960 | 0.780 |
| 100 | 100 | -100 | 1.492% | 1.000 | 99 | 0.980 | 0.790 |
| 151 | 151 | -151 | 2.253% | 1.000 | 149 | 0.980 | 0.589 |

The exchange is linear: one auxiliary unallocated edge enables one surplus canonical edge removal. The maximum tested cap removes `151` surplus edges, which is only `2.253%` of B0 surplus.

## P17 Share by Strategy

| Strategy | Cap 25 | Cap 50 | Cap 100 | Cap 151 |
| --- | ---: | ---: | ---: | ---: |
| `baseline_current_ranking` | 0.560 | 0.780 | 0.790 | 0.589 |
| `p17_cap_25_percent` | 0.240 | 0.240 | 0.250 | 0.306 |
| `p17_cap_40_percent` | 0.400 | 0.400 | 0.400 | 0.458 |
| `max_per_aux_relation_10` | 0.400 | 0.200 | 0.111 | 0.111 |
| `max_per_aux_relation_20` | 0.560 | 0.400 | 0.200 | 0.185 |
| `relation_diversity_penalty_light` | 0.040 | 0.020 | 0.130 | 0.397 |
| `relation_diversity_penalty_strong` | 0.040 | 0.020 | 0.130 | 0.397 |

The diversity reranking solves the relation-concentration problem for cap 50. The selected light-penalty cap-50 result reduces P17 from `39/50` to `1/50` without changing the surplus delta.

## Questions Answered

### 1. Is cap 50 too narrow?

Yes. Cap 50 removes only `50 / 6702 = 0.746%` of B0 surplus while relying on `50` auxiliary unallocated edges. It is useful as mechanism evidence but too small to materially change endpoint quality.

### 2. Does cap 151 provide a meaningful improvement?

No for registry purposes. Cap 151 is the largest tested improvement, but it removes only `2.253%` of B0 surplus and increases canonical-only weak components to `149`. The additional scale mostly increases auxiliary dependence rather than producing a strong connectedness-vs-balance frontier improvement.

### 3. Does diversity reranking solve the P17 issue sufficiently?

Yes for relation concentration. Diversity reranking reduces cap-50 P17 share from `0.780` to `0.020` with no surplus cost.

No for endpoint quality. It does not change the linear one-auxiliary-edge-per-surplus-edge tradeoff and does not fix canonical-only fragmentation.

### 4. Does C5-H2 improve the connectedness-vs-balance frontier enough to register?

No. The branch demonstrates a real mechanism: observed unallocated auxiliary edges can preserve full graph connectivity while surplus canonical bridge edges are removed. However, the surplus reduction is below the `5%` threshold for registry recommendation, and canonical-only fragmentation grows almost one-for-one with auxiliary count.

### 5. What should happen to C5-H2?

Recommended decision: preserve C5-H2 as diagnostic evidence only.

The selected diversity-aware cap-50 package can remain as an experimental candidate package pending artifact preservation, but this audit does not recommend registry update. It is stronger than the baseline cap-50 package for relation diversity, but not strong enough as a final candidate.

### 6. Should the project stop before H3?

No. Under observed-evidence constraints, C5-H2 is insufficient as an endpoint candidate. The next branch should be an H3 synthetic-pattern feasibility audit if the goal remains to improve the connectedness-vs-balance frontier. H3 must explicitly label synthetic pattern-derived triples and evaluate them separately from observed canonical and auxiliary edges.

## Decision

| Option | Decision |
| --- | --- |
| Register C5-H2 as an experimental candidate | Not recommended |
| Preserve C5-H2 as diagnostic evidence only | Recommended |
| Continue with diversity-aware candidate package | Keep package as evidence, not registry candidate |
| Stop before H3 | Not recommended if frontier exploration continues |
| Move to H3 synthetic-pattern feasibility | Recommended next probe branch |

## Safe Claim

C5-H2 shows that frozen observed unallocated auxiliary edges can preserve full connectivity while removing surplus canonical bridge edges. Diversity reranking can remove the cap-50 P17 concentration issue without surplus cost.

## Unsafe Claims

- Do not claim C5-H2 is canonical allocation-faithful.
- Do not claim C5-H2 materially improves B0 endpoint quality.
- Do not claim cap 151 is a strong replacement for B0.
- Do not claim diversity reranking fixes auxiliary dependence.
- Do not update `candidate_registry.v1.json` from C5-H2 without a separate human decision and artifact-preservation decision.

## Guardrails

- No WDQS query was made.
- No LLM call was made.
- No synthetic triple generation was performed in C5-H2.
- `candidate_registry.v1.json` was not updated.
