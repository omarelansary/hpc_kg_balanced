# C5 Config Notes

This config is a branch specification, not a generator run.

## First Probe Boundary

The first C5 implementation should run in probe-only mode over:

- `H1`: verified allocated cut-crossing replacements.
- `H2`: verified unallocated cut-crossing auxiliary support followed by pruning tests.

It must not generate a graph during the first implementation.

## Disabled Sources

The template disables:

- live sources,
- WDQS,
- LLM calls,
- synthetic pattern-derived triples.

Synthetic pattern-derived triples are explicitly deferred to `H3`. Live WDQS is deferred to `H4` and remains non-canonical unless results are frozen and audited. LLM use is deferred to `H5` and may only rank already-fixed candidate sets, not verify or invent triples.

## Accounting Requirements

Reports must keep these categories separate:

- canonical allocated observed triples,
- auxiliary unallocated observed triples,
- synthetic pattern-derived triples,
- unverified synthetic triples.

Allocation surplus and deficit must be computed over canonical allocated triples only. Connectivity must be reported with all edges and after removing auxiliary or synthetic edges.

## Thresholds

Preferred and fallback support/confidence thresholds are deliberately unset in the template. A future probe must set:

- `preferred_support_min`,
- `preferred_confidence_min`,
- `fallback_support_min`,
- `fallback_confidence_min`.

Candidates below preferred thresholds but above fallback thresholds must be marked `lower_confidence`.

## Registry

Do not update `candidate_registry.v1.json` for this scaffold. Registry update requires a generated graph, a standard evaluator report, and a human decision.
