# H4-B1 Deficit-Capped Inverse Completion Result

## Purpose

H4-B1 tests labelled deficit-capped inverse-pair rule-completion. It is not canonical observed KG construction and does not run KGE. Every generated edge is labelled `synthetic_rule_completion` with `rule_type = inverse_pair_completion`.

H4-B1 uses the H4-B.0 inverse opportunity audit and applies only the conservative B1 policy: target underfilled inverse relations, exclude frozen-observed candidates, require pair-level confidence at or above `0.8`, and stop at target relation deficit. H4-B2 add-all, H4-B3 safe-delete, and H4-C composition completion were not implemented or run.

## Run

Run path: `/tmp/H4_labelled_rule_completion/runs/h4_B1_deficit_capped_20260607T091533Z`

Run location status: `temporary_not_durable`

The repository experiment path was not writable in this execution context, so runtime graph outputs were written under `/tmp`. These outputs are temporary validation artifacts and are not durable committed graph artifacts.

## Selection Summary

| Field | Value |
| --- | ---: |
| Missing inverse opportunities from audit | 3854 |
| Recomputed missing inverse triples | 3854 |
| Skipped because already frozen-observed | 80 |
| Skipped below confidence threshold | 1243 |
| Skipped target overfilled | 158 |
| Skipped target no deficit room | 45 |
| Skipped after deficit cap ordering | 2170 |
| Eligible before deficit cap | 2328 |
| Generated synthetic inverse edges | 158 |

The H4-B.0 audit reported `223` raw deficit-capped opportunities, but H4-B1 generated `158` edges after applying the default confidence threshold and excluding frozen-observed inverse candidates. The generated count is therefore the strict B1 realized count, not the raw H4-B.0 opportunity count.

## Metric Comparison

| Graph/run | Triples | Entities | Triples/entity | WCC | Relations | Duplicates | Total surplus | Total deficit | Inverse deficit | Symmetric deficit | Composition surplus | Synthetic edges |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 | 24683 | 21893 | 1.127438 | 1 | 139/139 | 0 | 6702.000000 | 2019.000000 | 175.782501 | 1378.902831 | 6266.933965 | 0 |
| C6-C observed-only | 24507 | 21893 | 1.119399 | 1 | 139/139 | 0 | 6509 | 2002 | n/a | 1377.903 | 6159.705 | 0 |
| H4-A1 deficit-capped symmetric | 24812 | 21893 | 1.133330 | 1 | 139/139 | 0 | 6702 | 1890 | n/a | 1249.903 | 6266.934 | 129 |
| H4-A3 strict base-support symmetric | 26926 | 21893 | 1.229891 | 1 | 139/139 | 0 | 8754 | 1828 | n/a | 0 | 6384.563 | 2668 |
| H4-B1 deficit-capped inverse | 24841 | 21893 | 1.134655 | 1 | 139/139 | 0 | 6702.000000 | 1861.000000 | 58.339113 | 1348.194595 | 6266.933965 | 158 |

## H4-B1 Result

H4-B1 generated `158` labelled synthetic inverse edges. It preserved WCC `1`, `139/139` allocated relation coverage, and duplicate-free status. It improved total deficit from `2019` to `1861` and inverse deficit from `175.782501` to `58.339113`. It improved triples/entity density from `1.127438` to `1.134655`. Total surplus did not increase (`6702` before and after).

The run also slightly reduced symmetric deficit through multi-pattern relation apportioning, but that is not the primary H4-B1 objective. Composition surplus did not change.

## Claim Boundary

Safe claims:

- H4-B1 generated only labelled `synthetic_rule_completion` inverse-pair edges.
- No generated H4-B1 edge was already present in frozen Stage2 observed candidates.
- The temporary validation run preserved WCC `1`, `139/139` coverage, and duplicate-free status.
- H4-B1 reduced total and inverse deficit under the strict B1 filters.

Unsafe claims:

- H4-B1 edges are canonical observed triples.
- H4-B1 proves generated inverse triples are true Wikidata facts.
- H4-B1 proves KGE behavior.
- H4-B1 is globally optimal.
- H4-B1 is final without human artifact review and durable artifact preservation.

## Decision

Final H4-B1 decision state: `synthetic_augmented_candidate_for_review`.

This means H4-B1 is strong enough to preserve for human review as a labelled synthetic augmentation result, but it is not a final KG, not canonical observed evidence, not a registry update, and not KGE evidence. The current graph outputs are temporary `/tmp` validation outputs, so artifact promotion would require rerunning or preserving outputs in a durable location with hashes.
