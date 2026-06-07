# H4-A Labelled Symmetric Reverse-Completion Result

## Purpose

H4-A tests labelled symmetric reverse-completion as the first rule-completion subcase for underfilled verified patterns. It is not canonical observed KG construction. Every generated H4-A edge is labelled `synthetic_rule_completion` with `rule_type = symmetric_reverse_completion` and base-triple provenance.

The run asks whether rule-derived symmetric reverse edges can reduce symmetric underfill, improve graph density, preserve hard graph constraints, and make later strict safe deletion possible.

## Evidence Boundary

Starting graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`

Allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`

H4.0 audit: `docs/reconstruction/80_H4_labelled_rule_completion_opportunity_audit.md`

C6 showed that observed-only candidate reuse cannot repair most symmetric reverse deficit: `2,669` B0 symmetric reverse triples were missing, but only `1` was found in frozen Stage2 observed candidates. H4-A therefore tests labelled rule-completion, not observed candidate reuse.

## Superseded H4-A3 Result

The first H4-A3 output is superseded. It accepted `2,510` deletions and appeared to improve surplus, but the later correctness audit found that it deleted `2,396` B0 base triples while retaining their generated synthetic reverse edges. That exposed a base-support policy gap.

The superseded H4-A3 output must not be used as a candidate result, registry input, or artifact-promotion basis.

## Strict Base-Support Policy

Strict H4-A3 now preserves base triples for retained synthetic edges by default. For a generated edge `t,r,h`, the supporting base triple `h,r,t` must remain in the final graph unless an explicit diagnostic override is enabled.

The strict rerun used the default policy:

| Field | Value |
| --- | ---: |
| Accepted deletions | 425 |
| Rejected base-support deletions | 2,668 |
| Deleted base-support triples | 0 |
| Weak component count | 1 |
| Allocated relation coverage | 139/139 |
| Total surplus | 8,754 |
| Total deficit | 1,828 |
| Symmetric deficit | 0 |
| Decision | `diagnostic_only` |

The strict rerun outputs were written under `/tmp/H4_labelled_rule_completion/runs/`. They are temporary validation outputs, not durable committed graph artifacts. The repository run path was not writable in this execution context, so this document records the strict validation result but does not lock graph artifacts for promotion.

## Result Comparison

| Graph/run | Triples | Entities | Triples/entity | WCC | Relations | Duplicates | Total surplus | Total deficit | Symmetric deficit | Composition surplus | Synthetic edges | Synthetic ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| B0 | 24,683 | 21,893 | 1.127438 | 1 | 139 | 0 | 6,702 | 2,019 | 1,378.903 | 6,266.934 | 0 | 0.000000 |
| C6-C observed-only | 24,507 | 21,893 | 1.119399 | 1 | 139 | 0 | 6,509 | 2,002 | 1,377.903 | 6,159.705 | 0 | 0.000000 |
| H4-A1 deficit-capped | 24,812 | 21,893 | 1.133330 | 1 | 139 | 0 | 6,702 | 1,890 | 1,249.903 | 6,266.934 | 129 | 0.005199 |
| H4-A2 add-all | 27,351 | 21,893 | 1.249303 | 1 | 139 | 0 | 9,179 | 1,828 | 0 | 6,418.583 | 2,668 | 0.097547 |
| H4-A3 strict base-support safe-delete | 26,926 | 21,893 | 1.229891 | 1 | 139 | 0 | 8,754 | 1,828 | 0 | 6,384.563 | 2,668 | 0.099086 |

## Interpretation

H4-A1 is the conservative labelled completion run. It reduces symmetric and total deficit but does not reduce surplus.

H4-A2 is an upper-bound stress test. It eliminates symmetric deficit, but worsens total surplus and composition surplus.

Strict H4-A3 preserves the base support for retained synthetic edges. It eliminates symmetric deficit and preserves hard constraints, but it still worsens total surplus relative to B0 (`6,702` to `8,754`) and leaves composition surplus worse than B0. Under strict base-support preservation, H4-A is diagnostic evidence, not a candidate replacement for B0.

## Claim Boundaries

Safe claims:

- H4-A generated labelled `synthetic_rule_completion` edges only for verified symmetric relations.
- Strict H4-A3 preserved WCC `1`, `139/139` relation coverage, and duplicate-free status in the temporary validation run.
- Strict H4-A3 preserved all base triples supporting retained synthetic edges.
- H4-A eliminates symmetric deficit in add-all mode, but worsens total surplus under strict base-support preservation.

Unsafe claims:

- H4-A edges are canonical observed triples.
- H4-A proves generated reverse triples are true Wikidata facts.
- H4-A proves KGE behavior.
- H4-A is a final KG.
- H4-A is a registry candidate.
- Do not claim the superseded H4-A3 output is usable for artifact promotion.

## Decision

Final H4-A decision state: `diagnostic_only`.

H4-A is not canonical observed evidence, not a final KG, not a registry candidate, and not a KGE claim. It is useful diagnostic evidence showing that labelled symmetric rule-completion can remove symmetric deficit, but strict base-support preservation prevents the earlier apparent surplus improvement.

