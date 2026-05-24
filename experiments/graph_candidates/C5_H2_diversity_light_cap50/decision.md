# C5-H2 Diversity Light Cap-50 Decision

## Decision Status

Recommended status: `experimental_candidate_pending_artifact_preservation`

Registry update: deferred.

## Evidence

The candidate is selected from the diversity reranking probe result:

`experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/diversity_probe/relation_diversity_penalty_light/cap_50/`

The selected result passed the C5-H2 policy:

- Auxiliary edges selected: `50`
- Canonical edges removed: `50`
- Canonical surplus delta: `-50.0`
- Canonical deficit delta: `0.0`
- Full graph weak components: `1`
- Canonical-only weak components: `49`
- P17 auxiliary count: `1/50`
- P17 share: `0.020`

## Rationale

The diversity reranking solved the cap-50 P17 concentration issue without reducing the cap-50 surplus benefit. The baseline cap-50 C5-H2 result used `39/50` P17 auxiliary edges, while this selected result uses `1/50`.

This is still not a canonical allocation-faithful graph. It depends on observed unallocated auxiliary edges to preserve full connectivity after removing surplus canonical bridge edges. Canonical-only connectivity remains fragmented.

## Caveats

- Auxiliary unallocated observed edges are not canonical benchmark triples.
- Canonical surplus and deficit are computed over canonical allocated triples only.
- The full graph is connected only when auxiliary edges are included.
- Graph JSONL outputs are not copied into this package and require artifact preservation before registry update.
- No WDQS query, LLM call, or synthetic triple generation was used.

## Decision

Keep as an experimental candidate package pending artifact preservation and human registry decision.
