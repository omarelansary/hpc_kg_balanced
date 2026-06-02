# C5-H2 Expanded Auxiliary Saturation Audit

Recommendation: `continue_to_best_auxiliary_candidate_generation`

This audit expands C5-H2 from the earlier bounded cut-crossing evidence to all B0 surplus bridge-removal targets found under current frozen local evidence.
It does not write graph JSONL outputs and does not update the candidate registry.

## Target Universe

- Surplus bridge targets: `9369`
- Surplus non-bridge targets: `636`
- Non-surplus bridge targets: `9799`
- Surplus relations considered: `24`

## Expanded Frozen Source Scan

- Rows scanned: `1003499`
- Candidate triples parsed: `1003499`
- Observed unallocated candidate rows: `9475`
- Cut-crossing candidate-target pairs: `52626`
- Unique auxiliary candidates: `8073`
- Unique supported targets: `4429`
- Targets without support: `4940`

## Upper Bounds

- Simple min bound: `4429`
- Bipartite matching upper bound: `4216`

## Strategy Results

| Strategy | Aux | Surplus Delta | Deficit Delta | Canonical WCC | P17 Share | Max Relation Share | B0 Surplus Reduced | Stop | Thresholds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `baseline_current_ranking_no_cap` | 3650 | -3650 | 0 | 3478 | 0.473 | 0.473 | 54.461% | `source_exhausted` | `false` |
| `relation_diversity_penalty_light_no_cap` | 3643 | -3643 | 0 | 3471 | 0.341 | 0.341 | 54.357% | `source_exhausted` | `true` |
| `relation_diversity_penalty_strong_no_cap` | 3643 | -3643 | 0 | 3471 | 0.341 | 0.341 | 54.357% | `source_exhausted` | `true` |
| `max_per_aux_relation_10_no_cap` | 996 | -996 | 0 | 920 | 0.010 | 0.010 | 14.861% | `source_exhausted` | `true` |
| `max_per_aux_relation_20_no_cap` | 1384 | -1384 | 0 | 1284 | 0.014 | 0.014 | 20.651% | `source_exhausted` | `true` |
| `p17_cap_25_percent_no_cap` | 2627 | -2627 | 0 | 2501 | 0.113 | 0.140 | 39.197% | `source_exhausted` | `true` |
| `fragmentation_penalty_light_no_cap` | 3650 | -3650 | 0 | 3478 | 0.473 | 0.473 | 54.461% | `source_exhausted` | `false` |

## Decision

At least one expanded frozen-source strategy crosses the surplus, constraint, and relation-diversity thresholds.

## Best Observed Strategy

- Strategy: `relation_diversity_penalty_light_no_cap`
- Selected auxiliary edges: `3643`
- Canonical surplus delta: `-3643.0`
- B0 surplus reduction: `54.357%`
- Canonical deficit delta: `0.0`
- Full graph weak components: `1`
- Canonical-only weak components: `3471`
- Max auxiliary relation share: `0.341`

## Evidence Strength

This result is stronger than the earlier 200-cut bounded C5-H2 saturation audit because it scans all surplus B0 bridge targets available under the current frozen source boundary.
It is still not a global impossibility proof: live WDQS, new source construction, synthetic edges, and unimplemented multi-objective generators remain outside scope.
No WDQS query, LLM call, SLURM submission, synthetic triple generation, graph candidate output, or registry update was performed.
