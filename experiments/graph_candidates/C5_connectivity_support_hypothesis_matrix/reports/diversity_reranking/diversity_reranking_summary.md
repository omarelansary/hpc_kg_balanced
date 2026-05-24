# C5-H2 Diversity Reranking Probe

Recommendation: `use_diversity_penalty_candidate`

| Strategy | Cap | Status | Aux | Surplus delta | Deficit delta | Canonical WCC | P17 | P17 share |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline_current_ranking` | 25 | `passed_policy` | 25 | -25.0 | 0.0 | 24 | 14 | 0.560 |
| `baseline_current_ranking` | 50 | `passed_policy` | 50 | -50.0 | 0.0 | 49 | 39 | 0.780 |
| `baseline_current_ranking` | 100 | `passed_policy` | 100 | -100.0 | 0.0 | 99 | 79 | 0.790 |
| `baseline_current_ranking` | 151 | `passed_policy` | 151 | -151.0 | 0.0 | 149 | 89 | 0.589 |
| `p17_cap_25_percent` | 25 | `passed_policy` | 25 | -25.0 | 0.0 | 24 | 6 | 0.240 |
| `p17_cap_25_percent` | 50 | `passed_policy` | 50 | -50.0 | 0.0 | 48 | 12 | 0.240 |
| `p17_cap_25_percent` | 100 | `passed_policy` | 100 | -100.0 | 0.0 | 98 | 25 | 0.250 |
| `p17_cap_25_percent` | 151 | `passed_policy` | 121 | -121.0 | 0.0 | 119 | 37 | 0.306 |
| `p17_cap_40_percent` | 25 | `passed_policy` | 25 | -25.0 | 0.0 | 24 | 10 | 0.400 |
| `p17_cap_40_percent` | 50 | `passed_policy` | 50 | -50.0 | 0.0 | 48 | 20 | 0.400 |
| `p17_cap_40_percent` | 100 | `passed_policy` | 100 | -100.0 | 0.0 | 98 | 40 | 0.400 |
| `p17_cap_40_percent` | 151 | `passed_policy` | 131 | -131.0 | 0.0 | 129 | 60 | 0.458 |
| `max_per_aux_relation_10` | 25 | `passed_policy` | 25 | -25.0 | 0.0 | 24 | 10 | 0.400 |
| `max_per_aux_relation_10` | 50 | `passed_policy` | 50 | -50.0 | 0.0 | 48 | 10 | 0.200 |
| `max_per_aux_relation_10` | 100 | `passed_policy` | 90 | -90.0 | 0.0 | 88 | 10 | 0.111 |
| `max_per_aux_relation_10` | 151 | `passed_policy` | 90 | -90.0 | 0.0 | 88 | 10 | 0.111 |
| `max_per_aux_relation_20` | 25 | `passed_policy` | 25 | -25.0 | 0.0 | 24 | 14 | 0.560 |
| `max_per_aux_relation_20` | 50 | `passed_policy` | 50 | -50.0 | 0.0 | 48 | 20 | 0.400 |
| `max_per_aux_relation_20` | 100 | `passed_policy` | 100 | -100.0 | 0.0 | 98 | 20 | 0.200 |
| `max_per_aux_relation_20` | 151 | `passed_policy` | 108 | -108.0 | 0.0 | 106 | 20 | 0.185 |
| `relation_diversity_penalty_light` | 25 | `passed_policy` | 25 | -25.0 | 0.0 | 25 | 1 | 0.040 |
| `relation_diversity_penalty_light` | 50 | `passed_policy` | 50 | -50.0 | 0.0 | 49 | 1 | 0.020 |
| `relation_diversity_penalty_light` | 100 | `passed_policy` | 100 | -100.0 | 0.0 | 98 | 13 | 0.130 |
| `relation_diversity_penalty_light` | 151 | `passed_policy` | 151 | -151.0 | 0.0 | 149 | 60 | 0.397 |
| `relation_diversity_penalty_strong` | 25 | `passed_policy` | 25 | -25.0 | 0.0 | 25 | 1 | 0.040 |
| `relation_diversity_penalty_strong` | 50 | `passed_policy` | 50 | -50.0 | 0.0 | 49 | 1 | 0.020 |
| `relation_diversity_penalty_strong` | 100 | `passed_policy` | 100 | -100.0 | 0.0 | 98 | 13 | 0.130 |
| `relation_diversity_penalty_strong` | 151 | `passed_policy` | 151 | -151.0 | 0.0 | 149 | 60 | 0.397 |

## Interpretation

A diversity-aware strategy substantially reduces P17 concentration with acceptable surplus cost.

This is a probe-only reranking experiment. It does not update the registry and does not make C5-H2 a canonical allocation-faithful candidate.
