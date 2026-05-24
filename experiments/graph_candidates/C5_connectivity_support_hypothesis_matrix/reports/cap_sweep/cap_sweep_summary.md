# C5-H2 Auxiliary Cap Sweep

Recommendation: `continue_with_diversity_penalty`

| Cap | Status | Aux edges | Surplus delta | Deficit delta | Full WCC | Canonical WCC | P17 count | P17 share |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | `passed_policy` | 10 | -10.0 | 0.0 | 1 | 9 | 3 | 0.300 |
| 25 | `passed_policy` | 25 | -25.0 | 0.0 | 1 | 24 | 14 | 0.560 |
| 50 | `passed_policy` | 50 | -50.0 | 0.0 | 1 | 49 | 39 | 0.780 |
| 100 | `passed_policy` | 100 | -100.0 | 0.0 | 1 | 99 | 79 | 0.790 |
| 151 | `passed_policy` | 151 | -151.0 | 0.0 | 1 | 149 | 89 | 0.589 |

## Interpretation

All passing caps remain auxiliary-dependent; improvement is small relative to B0 surplus and P17 concentration remains high.

The sweep supports preserving C5-H2 as experimental evidence, but it does not support a registry update yet.
Auxiliary edges remain unallocated observed support and are not canonical benchmark triples.
