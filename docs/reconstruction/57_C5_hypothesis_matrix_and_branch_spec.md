# C5 Connectivity-Support Hypothesis Matrix and Branch Spec

## Purpose

C5 is a planned experiment family for testing connectivity-support strategies after the strict C4 replacement branch closed as negative/probe evidence. C5 must test separate hypotheses rather than mixing provenance, operation type, relation allocation, and synthetic evidence assumptions in one generator.

No C5 graph has been generated. The C5 registry should not be updated until a graph exists, a standard evaluator report exists, and a human decision is recorded.

## Context From C4

C4 tested strict allocated-only bridge-aware replacement from B0. The C4 probe found zero feasible replacements for the first 200 tested target-generic bridge edges.

C4.1 showed that the eligible replacement pool had 612 rows with both endpoints in B0, but none crossed any tested bridge cut.

C4.2 broadened the search to local frozen evidence. It found 625 unique cut-crossing candidates and 102 unique allocated cut-crossing candidates. However, all 546 surplus-reducing candidate-cut pairs were unallocated; allocated cut-crossing evidence did not reduce surplus under the tested replacement delta.

This means the next branch must distinguish unallocated observed evidence from unverified or synthetic evidence.

## Candidate Identity

- Candidate ID: `C5_connectivity_support_hypothesis_matrix`
- Parent candidate ID: `B0`
- Strategy: `connectivity_support_hypothesis_matrix`
- Status: `planned_not_generated`
- First implementation mode: probe-only over `H1` and `H2`

## Conceptual Distinctions

- `unallocated` means the relation is outside the canonical 139 allocated relations.
- `unverified` means the triple itself is not observed in frozen evidence.
- `synthetic_pattern_derived` triples may be considered in a later branch, but must be explicitly marked and evaluated separately.

These concepts must not be collapsed. An observed unallocated triple is not the same as a synthetic or unverified triple.

## Tested Axes

### 1. Edge Provenance Axis

| Value | Meaning | First C5 Status |
| --- | --- | --- |
| `canonical_allocated_observed` | Observed triple whose relation is in the canonical 139 allocated relations. | Enabled for H1 probe. |
| `auxiliary_unallocated_observed` | Observed triple whose relation is outside the canonical allocation. | Enabled for H2 probe only as auxiliary evidence. |
| `synthetic_pattern_derived` | Triple inferred from verified structural patterns rather than directly observed. | Deferred. |
| `live_verified_observed` | Observed evidence found through a live WDQS run. | Deferred and non-canonical until frozen and audited. |
| `synthetic_unverified` | Triple invented or inferred without preserved observation or validated pattern rule. | Not allowed. |

### 2. Operation Axis

| Value | Meaning | First C5 Status |
| --- | --- | --- |
| `remove_replace` | Remove a target bridge edge and replace it with another edge. | Enabled for H1 only. |
| `auxiliary_add_then_prune` | Add auxiliary support first, then test whether surplus target bridge edges can be pruned. | Enabled for H2 probe. |
| `auxiliary_add_only` | Add support edges without pruning. | Deferred; must be evaluated separately because graph size increases. |
| `pattern_synthesis_then_prune` | Create pattern-derived support candidates, then test pruning. | Deferred. |

### 3. Pattern-Priority Axis

C5 must compute current B0 pattern deficits before deciding which pattern to prioritize. It must not hardcode symmetric-first or any other pattern-first policy unless the metrics show that pattern has the maximum deficit under the selected accounting scheme.

Candidate selection should support:

- compute current pattern deficits from B0,
- prioritize the most-deficit pattern first,
- report pattern-priority decisions in each probe output.

### 4. Threshold Axis

C5 should distinguish preferred thresholds from fallback thresholds:

- `preferred_support_min`
- `preferred_confidence_min`
- `fallback_support_min`
- `fallback_confidence_min`

Candidates below preferred thresholds but above fallback thresholds must be marked `lower_confidence`. They may not be silently mixed with preferred candidates.

### 5. Evaluation Axis

Every C5 report must separate:

- canonical allocated triples,
- auxiliary observed unallocated triples,
- synthetic pattern-derived triples,
- unverified synthetic triples,
- connectivity with all edges,
- connectivity after removing auxiliary or synthetic edges,
- allocation surplus/deficit over canonical allocated triples only,
- full graph size including auxiliary or synthetic edges.

## Hypotheses

### H1: Allocated Observed Replacement

Verified allocated underfilled-pattern cut-crossing replacements exist and improve balance.

Initial evidence from C4.2 does not support this for the first 200 tested cuts, because zero allocated surplus-reducing candidate-cut pairs were found. H1 remains the strict replacement hypothesis and should be the first probe guardrail.

### H2: Auxiliary Unallocated Observed Support

Verified unallocated cut-crossing auxiliary edges can create redundancy that allows later pruning of surplus generic bridge edges.

C4.2 found unallocated cut-crossing candidates that reduce surplus if paired with removal of target-generic bridge edges. H2 must test those edges as auxiliary connectivity support, not as canonical allocated replacements. Reports must compute connectivity with and without auxiliary edges and quota metrics over canonical allocated triples only.

### H3: Synthetic Pattern-Derived Support

Pattern-derived synthetic triples from verified symmetry, inverse, or composition rules can create bridge alternatives, but must be marked `synthetic_pattern_derived` and evaluated separately.

H3 is deferred. It requires an explicit pattern rule source, confidence/support thresholds, and separate accounting from observed evidence.

### H4: Live WDQS Observed Evidence

Live WDQS can find observed cut-crossing evidence not present in frozen local sources.

H4 is deferred and non-canonical unless the live search results are frozen, hashed, audited, and made reproducible from local evidence.

### H5: LLM Ranking Only

LLM should not verify or invent triples. At most, it may rank already-fixed candidate sets in a future exploratory branch with full prompt, model, and raw-response logging.

H5 is deferred and should not be part of the first C5 implementation.

## First Implementation Boundary

The first C5 implementation should be probe-only and limited to:

- `H1`: strict allocated observed cut-crossing replacement,
- `H2`: observed unallocated auxiliary support followed by pruning tests.

It should not enable:

- synthetic pattern-derived triples,
- live WDQS,
- LLM use,
- graph generation,
- registry update.

## Branch Options

| Branch | Meaning | Status |
| --- | --- | --- |
| C5-H1 | Probe allocated observed cut-crossing replacements. | Enabled first. |
| C5-H2 | Probe unallocated observed auxiliary support plus later pruning. | Enabled first. |
| C5-H3 | Probe synthetic pattern-derived support. | Deferred. |
| C5-H4 | Explore live WDQS observed cut-crossing support. | Deferred and non-canonical until frozen. |
| C5-H5 | LLM ranking of fixed candidate sets. | Deferred; no verification or invention. |

## Unsafe Claims

Do not claim:

- that C5 has generated a graph,
- that unallocated means unverified,
- that observed unallocated triples are synthetic,
- that synthetic pattern-derived triples are observed,
- that live WDQS evidence is canonical before freezing and audit,
- that LLM output verifies or invents graph triples,
- that symmetric candidates should be prioritized before computing current B0 pattern deficits.

## Recommendation

Create C5 as a hypothesis matrix scaffold and implement only probe-only H1/H2 checks first. A graph generator should be considered only after probe evidence identifies a candidate set that satisfies explicit provenance, threshold, connectivity, and evaluation constraints.
