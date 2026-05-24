# C5-H2 Candidate Decision

Decision: `pending_further_cap_sweep`

C5-H2 generated a policy-passing experimental auxiliary-connectivity graph candidate at cap 50.

## Result

| Metric | Value |
| --- | ---: |
| Auxiliary edges selected | 50 |
| Canonical edges removed | 50 |
| Canonical surplus delta | -50.0 |
| Canonical deficit delta | 0.0 |
| Full graph weak components | 1 |
| Canonical-only weak components | 49 |
| Full graph triples | 24,683 |
| Canonical allocated triples | 24,633 |
| Auxiliary unallocated observed edges | 50 |
| Unallocated auxiliary relation count | 11 |

## Interpretation

C5-H2 improves B0's canonical surplus by 50 without increasing deficit, but the improvement is small relative to B0's total surplus of 6,702.

The full graph remains connected only because auxiliary unallocated observed edges are included. Without those auxiliary edges, the canonical-only graph has 49 weak components. Therefore C5-H2 is not a canonical allocation-faithful replacement for B0.

The auxiliary relation distribution is heavily concentrated in P17, with 39 of 50 auxiliary edges using that relation. This needs further cap and diversity analysis before any registry update.

## Decision

Do not register C5-H2 yet.

Preserve the generated reports and graph artifact hashes. Continue only with a cap sweep and explicit comparison of:

- canonical surplus and deficit;
- full graph connectivity;
- canonical-only connectivity;
- auxiliary relation concentration;
- auxiliary edge count;
- benchmark-claim implications.

## Registry

`candidate_registry.v1.json` must remain unchanged until a human decision accepts a specific C5-H2 candidate after the cap sweep.

## Guardrails

- No WDQS query was made.
- No LLM call was made.
- No synthetic triples were created.
- C5-H2 auxiliary edges are not canonical benchmark triples.
