# C5-H2 Marginal Utility Decision

## Decision

Preserve C5-H2 as diagnostic evidence only.

Do not update `candidate_registry.v1.json` from the C5-H2 cap sweep or diversity reranking evidence.

## Basis

C5-H2 produces policy-passing auxiliary-connectivity candidates, but the marginal utility is too small for registry recommendation:

- Cap 50 removes `50` surplus edges, which is `0.746%` of B0 surplus `6,702`.
- Cap 151 removes `151` surplus edges, which is `2.253%` of B0 surplus `6,702`.
- Every tested cap has auxiliary cost `1.000` auxiliary edge per surplus edge removed.
- Canonical-only fragmentation grows almost one-for-one with auxiliary count.
- Diversity reranking fixes P17 concentration at cap 50 but not auxiliary dependence or scale.

## Selected Diversity Package

The selected package:

`experiments/graph_candidates/C5_H2_diversity_light_cap50/`

is useful evidence and may be preserved as an experimental package. Its recommended status remains:

`experimental_candidate_pending_artifact_preservation`

This package should not be registered unless a later human decision accepts auxiliary unallocated edges as an experimental candidate class and preserves the referenced graph JSONL artifacts.

## Next Branch

If frontier exploration continues, move to an H3 synthetic-pattern feasibility audit. H3 must keep synthetic pattern-derived triples explicitly labelled and separate from observed canonical or auxiliary edges.

## Safe Claim

C5-H2 demonstrates an observed-auxiliary connectivity mechanism, and diversity reranking can reduce P17 concentration without surplus cost.

## Unsafe Claim

C5-H2 should not be described as a canonical allocation-faithful replacement for B0 or as a material endpoint-quality improvement.
