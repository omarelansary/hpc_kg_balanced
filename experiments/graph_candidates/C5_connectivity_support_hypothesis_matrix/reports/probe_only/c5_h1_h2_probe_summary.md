# C5 H1/H2 Connectivity-Support Probe

Status: probe only. No graph candidate was generated.

## Pattern Priority

| Pattern | Deficit | Surplus | Observed | Expected |
| --- | ---: | ---: | ---: | ---: |
| `symmetric` | 1378.9028308028305 | 0.0 | 3621.0971691971695 | 5000.0 |
| `inverse` | 175.78250108152952 | 0.0 | 4824.2174989184705 | 5000.0 |
| `anti_symmetric` | 29.24863345853464 | 0.0 | 4970.751366541465 | 5000.0 |
| `composition` | 0.0 | 6266.933965342894 | 11266.933965342894 | 5000.0 |

## H1: Canonical Allocated Observed Replacement

H1 tests whether observed, allocated cut-crossing replacements can replace target-generic bridge edges while preserving hard constraints.

- Candidate-cut pairs tested: `109`
- Feasible H1 moves: `109`
- Balance-improving H1 moves: `0`
- Greedy H1 upper-bound count: `0`
- Greedy H1 surplus delta: `0.0`
- Greedy H1 deficit delta: `0.0`

## H2: Auxiliary Unallocated Observed Support

H2 tests whether observed unallocated cut-crossing edges can be added as auxiliary connectivity support, enabling later pruning of surplus generic bridge edges.

- Candidate-cut pairs tested: `546`
- Feasible H2 moves: `546`
- Auxiliary enables-prune moves: `546`
- Greedy H2 upper-bound count: `151`
- Greedy H2 surplus delta: `-151.0`
- Greedy H2 deficit delta: `0.0`

## Generator Decision

Recommendation: `h2_auxiliary_probe_supports_designing_a_constrained_auxiliary_branch`.

A strict H1 replacement generator is justified only if allocated, balance-improving moves exist. An H2 branch, if pursued, must keep auxiliary unallocated edges separate from canonical allocation accounting and must receive human approval before any graph generation.

## Notes

- No WDQS query was made.
- No LLM call was made.
- No synthetic triples were created.
- `outputs/graph.jsonl` was not written.
- `candidate_registry.v1.json` was not updated.
