# H4-B Inverse-Pair Rule-Completion Opportunity Audit

## 1. Purpose

H4-B audits labelled inverse-pair rule-completion for underfilled verified patterns. It is an opportunity and planning audit only: it is not canonical observed evidence, not KGE evaluation, and not graph generation.

H4-B.0 decides whether inverse completion is safe enough to implement. Any H4-B edge generated later must be labelled `synthetic_rule_completion` with inverse-pair provenance. It must not be framed as a canonical observed triple.

## 2. Why H4-B Exists

B0 is connected and relation-complete, but imbalanced. It remains the current frozen connected baseline rather than a final balanced solution.

C6 observed-only repair was marginal and cannot synthesize missing rule-derived evidence. H4-A showed that labelled rule-completion can eliminate one pattern deficit, but the strict base-support rerun remains `diagnostic_only` because total surplus worsens.

The H4.0 audit found `22` verified inverse pairs, `44` oriented inverse rules, and `3,854` missing inverse-completion opportunities. H4-B is therefore the next rule-completion subcase to audit, but it is riskier than symmetry because pair orientation and false positives matter.

## 3. Inverse Rule Semantics

For an inverse pair `(r1, r2)`, the two orientations are distinct:

- `r1_to_r2`: `h --r1--> t` implies `t --r2--> h`.
- `r2_to_r1`: `h --r2--> t` implies `t --r1--> h`.

Each orientation must be counted separately. Confidence may differ by orientation, although the preserved H4.0 evidence records pair-level empirical confidence, so this audit does not invent orientation-specific confidence values.

Missing inverse edges generated later are `synthetic_rule_completion`, not canonical observed triples.

## 4. Evidence Required Before Generation

For each oriented inverse rule, generation requires:

- relation pair identifiers `r1` and `r2`;
- verification or confidence source;
- support counts if available;
- whether both relations are in the allocated relation set;
- B0 counts for source and target inverse relation;
- eta targets for source and target inverse relation;
- relation deficits and surpluses;
- pattern memberships;
- orientation-specific missing opportunities;
- whether generated edges would exceed relation or pattern deficits.

The inverse evidence was found in local Phase I/H4.0 artifacts. Its limitations are important: the exact Streamlit export session is incomplete, the inverse LLM branch is not treated as source evidence, and empirical pair confidence is not logical truth.

## 5. Opportunity Counts

This audit used only local frozen artifacts:

- B0 graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- H4.0 opportunity audit: `artifacts/final_graph/selected_final_graph/rebuild/h4_labelled_rule_completion_opportunity_audit.json`
- frozen Stage2 candidate shards: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards/*.jsonl`

Totals:

| Metric | Value |
| --- | ---: |
| Verified inverse pairs | 22 |
| Oriented rules | 44 |
| Missing inverse opportunities | 3854 |
| Already observed in frozen Stage2 candidates | 80 |
| Rule-completion required | 3774 |
| Deficit-capped additions | 223 |
| Add-all additions | 3774 |
| Target relations already overfilled | 2 |
| Opportunities targeting overfilled relations | 158 |
| Composition-heavy opportunities | 226 |
| Rules with confidence below 0.8 | 12 |
| Rules with no deficit-capped room | 5 |
| Estimated synthetic ratio, deficit-capped | 0.008954 |
| Estimated synthetic ratio, add-all | 0.132621 |

The full oriented-rule table is recorded in `artifacts/final_graph/selected_final_graph/rebuild/h4_b_inverse_completion_opportunity_audit.json`. The highest add-all opportunities are:

| Orientation | Confidence | Source count | Target count | Target deficit | Missing inverse | Observed frozen | Rule-completion required | Deficit-capped | Risk flags |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| P2743_to_P13177 | 0.970518 | 445 | 408 | 21 | 391 | 0 | 391 | 21 | none |
| P13177_to_P2743 | 0.970518 | 408 | 445 | 23 | 354 | 0 | 354 | 23 | none |
| P1268_to_P10607 | 0.889925 | 271 | 95 | 4 | 226 | 0 | 226 | 4 | composition_heavy_relation_involved |
| P5607_to_P8289 | 0.684045 | 180 | 105 | 4 | 179 | 0 | 179 | 4 | confidence_below_0_8 |
| P1625_to_P6439 | 0.713311 | 170 | 102 | 5 | 170 | 0 | 170 | 5 | confidence_below_0_8 |
| P3729_to_P3730 | 0.813498 | 147 | 143 | 7 | 107 | 0 | 107 | 7 | none |
| P568_to_P567 | 0.751810 | 222 | 223 | 8 | 105 | 0 | 105 | 8 | confidence_below_0_8 |
| P1445_to_P1434 | 0.963656 | 106 | 104 | 6 | 105 | 0 | 105 | 6 | none |
| P8289_to_P5607 | 0.684045 | 105 | 180 | 9 | 104 | 0 | 104 | 9 | confidence_below_0_8 |
| P1434_to_P1445 | 0.963656 | 104 | 106 | 4 | 103 | 0 | 103 | 4 | none |
| P3730_to_P3729 | 0.813498 | 143 | 147 | 2 | 103 | 0 | 103 | 2 | none |
| P6439_to_P1625 | 0.713311 | 102 | 170 | 8 | 102 | 0 | 102 | 8 | confidence_below_0_8 |

The `80` missing inverse opportunities already observed in frozen Stage2 candidates should not be generated as H4-B synthetic edges. They belong to the observed-candidate evidence regime. H4-B rule-completion counts therefore use the remaining `3,774` required rule-derived opportunities.

## 6. Risk Controls

Required controls before H4-B generation:

- orientation-specific accounting for `r1_to_r2` and `r2_to_r1`;
- do not invent orientation-specific confidence where only pair-level confidence is preserved;
- deficit-capped mode before add-all stress tests;
- explicit target-overfilled relation policy;
- exclude frozen-observed inverse candidates from synthetic generation;
- preserve base triples for retained synthetic inverse edges by default;
- label every generated edge as `synthetic_rule_completion` with `rule_type = inverse_pair_completion`;
- do not delete synthetic edges by default;
- post-completion safe-delete must preserve base support by default.

## 7. Proposed H4-B Modes

Planned only, not executed:

| Mode | Description | Decision role |
| --- | --- | --- |
| H4-B1 | Deficit-capped inverse completion, targeting underfilled inverse relations only. | Conservative candidate attempt. |
| H4-B2 | Add-all inverse completion. | Upper-bound stress test, not final by default. |
| H4-B3 | Add-all inverse completion plus strict base-support safe-delete. | Tests whether inverse completion creates redundancy for surplus deletion. |
| H4-B4 | High-confidence-only inverse completion if confidence scores are accepted. | Tests whether stricter evidence improves reliability. |

## 8. Acceptance Criteria for Future H4-B Runs

Hard constraints:

- WCC remains `1`;
- allocated relation coverage remains `139/139`;
- duplicate triples remain `0`;
- all H4-B edges are labelled `synthetic_rule_completion`;
- canonical and synthetic edges are separable;
- base-support preservation is enabled by default;
- no hidden synthetic edges.

Improvement criteria:

- deficit decreases meaningfully;
- density improves;
- total surplus does not worsen badly in conservative mode;
- composition dominance does not worsen unless explicitly justified;
- H4-B3 reports whether safe deletion becomes possible.

## 9. Unsafe Claims

H4-B cannot claim:

- generated inverse edges are observed facts;
- inverse confidence is logical truth;
- KGE behavior is known;
- add-all mode is final;
- global optimality;
- H4-B edges are canonical observed triples.

## 10. Recommendation

Recommendation: `implement_H4_B1_first`.

Reason: the audit found `3,854` missing oriented inverse opportunities and `223` deficit-capped rule-completion additions after excluding `80` frozen-observed candidates. H4-B1 is small enough to test conservatively. Add-all completion would add `3,774` synthetic edges, has an estimated synthetic edge ratio of `0.132621`, includes low-confidence orientations, and targets some overfilled or composition-heavy relations. H4-B2/B3 should remain stress tests, and H4-B4 depends on accepting a confidence threshold.
