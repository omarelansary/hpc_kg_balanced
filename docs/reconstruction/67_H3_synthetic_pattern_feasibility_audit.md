# H3 Synthetic Pattern Feasibility Audit

## Purpose

H3 tests whether verified Phase I structural patterns can synthesize bridge alternatives that cross the same B0 bridge cuts used by C4/C5.

This is a feasibility audit only. It does not generate a graph candidate, update the candidate registry, query WDQS, call an LLM, or create unmarked synthetic triples.

## Method

The audit uses the bounded C4/C5 bridge target space:

- target relations: `P31`, `P279`, `P131`
- maximum target edges: `200`
- tested bridge cuts: `200`

It loads B0, the canonical 5k allocation, patched v3 hop support, and v3 compact composition verification. It rebuilds the verified Phase I pattern rule sets under the canonical dashboard thresholds with Wilson filtering disabled.

Verified pattern rules available to H3:

| Pattern type | Rule count | Rule source |
| --- | ---: | --- |
| symmetric | 18 | empirical self-pair loop confidence |
| inverse | 44 oriented rules | empirical bidirectional inverse confidence |
| composition | 13 rules | compact sampled shortcut verification |

The audit then scans frozen local evidence sources for observed source edges that could support synthetic candidates:

- B0 parent graph
- Stage11 graph output
- Stage12 graph output
- Stage2 candidate shards
- frozen candidate pools

Every proposed candidate would be labelled `synthetic_pattern_derived`. Candidate triples are not treated as observed Wikidata facts.

## Candidate Criteria

For a synthetic candidate to be counted, it must:

- be derived from a verified symmetric, inverse, or composition rule;
- have observed source edge evidence in B0 or frozen local candidate sources;
- cross one of the tested bridge cuts;
- not already exist in B0;
- record whether the derived relation is allocated or unallocated;
- record whether replacing the target edge would reduce surplus or increase deficit;
- record the relevant support/confidence from the verified Phase I rule.

## Results

No synthetic candidates were found under the bounded frozen-evidence audit.

| Count | Value |
| --- | ---: |
| Tested cuts | 200 |
| Observed triples loaded for relations of interest | 25,670 |
| Relations of interest | 84 |
| Synthetic candidates | 0 |
| Allocated synthetic candidates | 0 |
| Unallocated synthetic candidates | 0 |
| Underfilled-pattern synthetic candidates | 0 |
| Surplus-reducing synthetic candidates | 0 |
| Deficit-neutral synthetic candidates | 0 |
| Preferred-threshold candidates | 0 |
| Fallback-threshold candidates | 0 |
| Low-confidence candidates | 0 |

Rejection summary:

| Rejection reason | Count |
| --- | ---: |
| missing observed source edges for symmetric rules | 18 |
| missing observed source edges for inverse rules | 44 |
| missing observed source edges for composition rules | 13 |

The report artifacts are:

- `experiments/graph_candidates/H3_synthetic_pattern_feasibility/reports/h3_synthetic_pattern_feasibility_report.json`
- `experiments/graph_candidates/H3_synthetic_pattern_feasibility/reports/h3_synthetic_pattern_feasibility_summary.md`
- `experiments/graph_candidates/H3_synthetic_pattern_feasibility/reports/h3_synthetic_pattern_examples.tsv`

## Comparison To C5-H2

C5-H2 found observed unallocated auxiliary edges that can preserve connectivity while removing surplus canonical bridge edges, but C5-H2 was weak at scale and remained auxiliary-dependent.

H3 does not improve on C5-H2 under the current bounded frozen-evidence audit because it finds no verified pattern-derived cut-crossing candidates. The result is therefore weaker than C5-H2 as an immediate graph-generation branch.

## Feasibility Conclusion

Conclusion: `h3_not_promising_no_candidates`

H3 should not proceed to graph generation from this bounded audit. The next useful step, if H3 is revisited, would be to broaden the source-edge search scope or change the bridge-cut target set, while preserving the same guardrails:

- no unmarked synthetic triples;
- no claim that synthetic triples are factual Wikidata facts;
- no registry update without graph generation, evaluation, artifact preservation, and human decision.

## Safe Claims

- The bounded H3 audit found no synthetic pattern-derived bridge alternatives under frozen local evidence.
- The audit checked verified symmetric, inverse, and composition rules from the reconstructed Phase I pipeline.
- Synthetic candidates would have been explicitly marked `synthetic_pattern_derived`.
- No WDQS query, LLM call, or graph generation was performed.

## Unsafe Claims

- Do not claim synthetic triples are factual Wikidata facts.
- Do not claim H3 generated a valid graph candidate.
- Do not claim LLM verification was used.
- Do not claim H3 supersedes C5-H2 or B0.
- Do not update `candidate_registry.v1.json` from this feasibility audit.
