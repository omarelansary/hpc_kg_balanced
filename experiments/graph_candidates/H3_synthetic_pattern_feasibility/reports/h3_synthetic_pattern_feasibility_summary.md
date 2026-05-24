# H3 Synthetic Pattern Feasibility Audit

Status: read-only feasibility audit. No graph candidate was generated.

## Scope

H3 tests whether verified Phase I structural patterns can synthesize cut-crossing bridge alternatives. Synthetic pattern-derived triples are not observed Wikidata triples and must remain explicitly labelled.

## Inputs

- B0 graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- Hop support: `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl`
- Composition verification: `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl`

## Tested Cuts

- Target relations: `P131, P279, P31`
- Tested bridge cuts: `200`
- Baseline surplus: `6702.0`
- Baseline deficit: `2019.0`

## Verified Pattern Rules

- Symmetric rules: `18`
- Inverse oriented rules: `44`
- Composition rules: `13`

## Candidate Counts

- Total synthetic candidates: `0`
- By pattern type: `{}`
- Allocated synthetic candidates: `0`
- Unallocated synthetic candidates: `0`
- Underfilled-pattern candidates: `0`
- Surplus-reducing candidates: `0`
- Deficit-neutral candidates: `0`
- Preferred-threshold candidates: `0`
- Fallback-threshold candidates: `0`
- Below fallback / low-confidence candidates: `0`
- Candidate already observed in local evidence: `0`
- Feasibility conclusion: `h3_not_promising_no_candidates`

## Risk Classification

`{}`

## Interpretation

H3 did not find promising synthetic candidates under the bounded frozen-evidence audit.

## Safe Claims

- The audit can state whether pattern-derived synthetic candidates were found under frozen evidence.
- Synthetic candidates are explicitly marked `synthetic_pattern_derived`.
- No WDQS query, LLM call, or graph generation was performed.

## Unsafe Claims

- Do not claim synthetic triples are factual Wikidata facts.
- Do not claim an H3 graph is valid before graph generation and evaluation.
- Do not claim LLM verification.
- Do not update the candidate registry from this feasibility audit alone.
