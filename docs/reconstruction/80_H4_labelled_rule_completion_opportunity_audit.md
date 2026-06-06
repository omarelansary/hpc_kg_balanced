# H4 Labelled Rule-Completion Opportunity Audit

## 1. Purpose

H4 tests labelled rule-derived completion for underfilled verified patterns. It is a different evidence regime from C6: C6 reuses frozen observed candidate triples, while H4 would derive new edges from verified structural rules and label those edges explicitly.

This is not canonical observed evidence and not KGE evaluation. H4.0 is an opportunity audit and design step only. It does not generate a graph, add synthetic triples, update the candidate registry, query WDQS, call an LLM, or run KGE.

## 2. Why H4 Exists

B0 is the current frozen connected baseline. It preserves weak connectivity, covers `139/139` allocated relations, and is duplicate-free, but it remains imbalanced and sparse.

C6 observed-only frozen candidate reuse produced only marginal improvement. The best observed C6 run, C6-C, reduced surplus from `6,702` to `6,509` and deficit from `2,019` to `2,002`, while preserving connectivity and relation coverage. That is useful diagnostic evidence, but not a strong final solution.

C6 also cannot fix most symmetric reverse deficit because observed reverse candidates are nearly absent from the frozen Stage2 shards. The C6 symmetric audit found `2,669` missing reverse triples for B0 symmetric-relation triples, but only `1` of those missing reverse triples appeared in frozen Stage2 candidates and only `1` was accepted by C6.

Therefore the next evidence regime, if synthetic or rule-derived edges are allowed, is labelled rule-derived completion.

## 3. Evidence Regimes

| Regime | Meaning | H4 status |
| --- | --- | --- |
| `canonical_observed` | Edge is already in the selected observed KG or accepted as an observed canonical allocated candidate. | Not the label for H4-created edges. |
| `frozen_observed_candidate` | Edge appears in preserved local candidate evidence. | C6 source regime; useful for comparison. |
| `auxiliary_observed` | Observed but not canonical allocated support edge. | C5-H2 source regime; not H4 rule completion. |
| `synthetic_rule_completion` | Edge is derived from a verified pattern rule and observed base evidence, but the derived edge itself is not observed. | Required H4 label if generated later. |
| `live_observed` | Edge collected from a live source such as WDQS after the frozen evidence cutoff. | Out of scope for H4.0. |
| `LLM_suggested` | Edge suggested or ranked by an LLM. | Out of scope and not acceptable as fact evidence. |

If H4 later generates outputs, the generated edges must use `synthetic_rule_completion` or an equivalent rule-completion label. They must not be recorded as `canonical_observed`.

## 4. H4 Subcases

| Subcase | Pattern family | Rule form | Target deficit | Evidence required | Risk level | Can generate automatically? | Required provenance label | Current status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H4-A | Symmetry | `x --r--> y` implies `y --r--> x` | Symmetric underfill and missing reverse edges | Verified symmetric relation, observed source edge, duplicate check | Lowest H4 risk, but still synthetic | Yes, after policy acceptance | `synthetic_rule_completion:symmetric_reverse` | First implementation candidate |
| H4-B | Inverse | `x --r1--> y` implies `y --r2--> x` for verified inverse pair | Inverse underfill and missing reciprocal inverse edges | Verified inverse pair confidence, observed source edge, pair orientation, false-positive controls | Medium | Not before controls are designed | `synthetic_rule_completion:inverse_pair` | Opportunity computed; generation deferred |
| H4-C | Composition | `x --r1--> y` and `y --r2--> z` implies `x --r3--> z` | Composition or relation-specific shortcut underfill | Verified composition rule, observed chain, rule confidence, target compatibility | High | Not before stricter controls are designed | `synthetic_rule_completion:composition_shortcut` | Opportunity computed; generation deferred |
| H4-D | Completion then safe-delete | Apply labelled completion, recompute structure, then test strict safe deletion | Surplus edge removability after added redundancy | Completed H4-A/B/C outputs and locked safe-delete policy | Medium to high | Only after labelled completion exists | Mixed labels, preserving rule provenance | Planned only |

Anti-symmetry does not define an automatic reverse-completion rule. Additions for anti-symmetric relations require observed evidence or a separate relation-specific justification.

## 5. Opportunity Counts

The audit used only local frozen artifacts:

- B0 graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- patched hop support: `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl`
- compact composition verification: `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl`
- Stage2 candidate shards: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards/*.jsonl`

### H4-A Symmetric Reverse Completion

Totals:

| Metric | Value |
| --- | ---: |
| Verified symmetric relations | 18 |
| B0 symmetric-relation triples | 4,051 |
| Reciprocal pairs already present in B0 | 691 |
| Missing reverse triples | 2,669 |
| Missing reverse triples found in frozen Stage2 candidates | 1 |
| Missing reverse triples requiring rule completion | 2,668 |
| Underfilled symmetric relations | 15 |
| Rule-completion opportunities on underfilled symmetric relations | 1,709 |
| Deficit-capped H4-A additions on underfilled symmetric relations | 129 |

The deficit-capped count is much smaller than the raw missing-reverse count because some highly missing symmetric relations are already over their relation quota, while some heavily underfilled relations have few or no reverse-completion opportunities in B0.

| Relation | eta | B0 count | deficit | reciprocal pairs | missing reverse | observed in Stage2 | rule completion required | deficit-capped additions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| P2152 | 329 | 54 | 275 | 27 | 0 | 0 | 0 | 0 |
| P1639 | 249 | 236 | 13 | 37 | 162 | 1 | 161 | 13 |
| P1322 | 261 | 249 | 12 | 121 | 7 | 0 | 7 | 7 |
| P5278 | 226 | 215 | 11 | 0 | 215 | 0 | 215 | 11 |
| P4545 | 339 | 59 | 280 | 27 | 5 | 0 | 5 | 5 |
| P3403 | 236 | 225 | 11 | 0 | 225 | 0 | 225 | 11 |
| P461 | 189 | 352 | 0 | 21 | 310 | 0 | 310 | 0 |
| P2743 | 334 | 445 | 0 | 102 | 241 | 0 | 241 | 0 |
| P13177 | 292 | 408 | 0 | 0 | 408 | 0 | 408 | 0 |
| P8865 | 230 | 129 | 101 | 62 | 5 | 0 | 5 | 5 |
| P1560 | 208 | 198 | 10 | 0 | 198 | 0 | 198 | 10 |
| P2959 | 199 | 197 | 2 | 0 | 197 | 0 | 197 | 2 |
| P3032 | 243 | 232 | 11 | 0 | 232 | 0 | 232 | 11 |
| P2155 | 318 | 207 | 111 | 100 | 7 | 0 | 7 | 7 |
| P6185 | 316 | 301 | 15 | 86 | 129 | 0 | 129 | 15 |
| P1420 | 211 | 201 | 10 | 0 | 201 | 0 | 201 | 10 |
| P514 | 497 | 38 | 459 | 17 | 4 | 0 | 4 | 4 |
| P399 | 323 | 305 | 18 | 91 | 123 | 0 | 123 | 18 |

H4-A has a real opportunity signal, but it must be controlled. Adding every missing reverse would increase several already overfilled symmetric relations. The first implementation should prioritize underfilled symmetric relations and stop at relation-level or pattern-level caps.

### H4-B Inverse-Pair Completion

The empirical dashboard evidence identifies `22` inverse pairs, or `44` oriented rules. The B0 graph contains `3,854` missing oriented inverse-completion opportunities under these rules.

Top inverse-pair opportunities by estimated additions:

| Pair | Confidence | Support | Missing r1->r2 | Missing r2->r1 | Estimated additions |
| --- | ---: | ---: | ---: | ---: | ---: |
| P13177 / P2743 | 0.970518 | 2,509 | 354 | 391 | 745 |
| P5607 / P8289 | 0.684045 | 7,353 | 179 | 104 | 283 |
| P1268 / P10607 | 0.889925 | 1,446 | 226 | 50 | 276 |
| P1625 / P6439 | 0.713311 | 240 | 170 | 102 | 272 |
| P568 / P567 | 0.751810 | 1,515 | 105 | 106 | 211 |

H4-B is not ready for generation yet. The empirical inverse evidence is useful, but inverse-pair completion needs pair-orientation controls, relation-specific false-positive checks, and a policy for whether to fill both directions or only deficit-reducing directions.

### H4-C Composition Shortcut Completion

The compact composition verification evidence yields `13` verified composition rules under the canonical dashboard thresholds with Wilson disabled. Exact B0 chain scanning found only `24` missing shortcut opportunities across those rules, all from `P3833 o P12994 -> P279`.

| Rule | Confidence | Base support | Exact B0 chains | Missing shortcuts | Estimated additions |
| --- | ---: | ---: | ---: | ---: | ---: |
| P4353 o P131 -> P1001 | 0.993939 | 165 | 0 | 0 | 0 |
| P2670 o P16 -> P16 | 0.990385 | 225 | 0 | 0 | 0 |
| P5277 o P2670 -> P31 | 0.966667 | 1,999 | 0 | 0 | 0 |
| P8308 o P461 -> P8308 | 0.964286 | 56 | 0 | 0 | 0 |
| P7209 o P279 -> P793 | 0.955556 | 137 | 0 | 0 | 0 |
| P2670 o P16 -> P361 | 0.947115 | 225 | 0 | 0 | 0 |
| P3833 o P12994 -> P279 | 0.853403 | 191 | 24 | 24 | 24 |
| P2353 o P131 -> P131 | 0.811321 | 212 | 0 | 0 | 0 |
| P10374 o P279 -> P31 | 0.752941 | 87 | 0 | 0 | 0 |
| P1158 o P931 -> P1158 | 0.714286 | 84 | 0 | 0 | 0 |
| P466 o P1268 -> P127 | 0.710000 | 917 | 0 | 0 | 0 |
| P814 o P1889 -> P31 | 0.673333 | 4,128 | 0 | 0 | 0 |
| P13210 o P366 -> P31 | 0.653333 | 2,225 | 0 | 0 | 0 |

H4-C is higher risk than H4-A because shortcut confidence is empirical, not logical truth. It is also not an obvious first target because composition is already the dominant surplus pattern in B0.

### H4-D Completion Then Safe-Delete

H4-D does not compute graph changes in H4.0. It can only run after H4-A/B/C generates labelled rule-completion edges and recomputes structure. The intended test is whether labelled completion creates redundancy that allows strict safe deletion of surplus canonical edges while preserving connectivity, `139/139` relation coverage, duplicate-free status, and edge provenance separation.

## 6. Safety and Acceptance Criteria

Hard constraints for any future H4-generated candidate:

- weak component count remains `1` unless explicitly relaxed;
- `139/139` allocated relation coverage remains;
- duplicate triples remain `0`;
- every rule-derived edge is labelled;
- canonical observed and rule-derived edges are separable;
- no hidden synthetic edges;
- all generated edges have base evidence and rule id;
- train/valid/test split policy treats rule-derived edges explicitly if KGE is later run.

Improvement criteria:

- reduce symmetric deficit and/or other underfilled pattern deficits;
- do not increase composition dominance unless composition is the target and justified;
- improve or preserve density if possible;
- after completion, test whether safe deletion of surplus edges becomes possible.

## 7. Risks

- Empirical pattern confidence is not logical truth.
- Domain/range compatibility is not fact truth.
- Synthetic edges can inflate KGE results.
- Reverse completion may add false facts if a relation is not truly symmetric in every case.
- Inverse completion requires correct pair orientation and relation-specific false-positive controls.
- Composition shortcuts are higher risk than symmetric reverse completion.
- H4 results must be evaluated separately from canonical observed graphs.

## 8. Implementation Plan, Not Yet Executed

Planned future scripts, not created in H4.0:

- `scripts/graph_candidates/h4_common.py`
- `scripts/graph_candidates/h4_opportunity_audit.py`
- `scripts/graph_candidates/h4_generate_rule_completion.py`
- `scripts/graph_candidates/h4_post_completion_safe_delete.py`
- `scripts/graph_candidates/h4_run_sweep.sh`

Planned future outputs:

- `h4_opportunity_audit.json`
- `h4_generated_edges.csv`
- `h4_generated_graph.jsonl`
- `h4_generated_graph.csv`
- `h4_post_completion_delete_report.json`

## 9. Decision Gate

H4-A is allowed to proceed only after:

- verified symmetric relations are identified;
- confidence and source evidence are recorded;
- the edge label schema is defined;
- the opportunity count is large enough to matter under deficit-aware caps;
- risks are accepted explicitly.

H4-B and H4-C are allowed only after confidence evidence, orientation policy, and false-positive controls are identified. H4-D must wait until labelled H4-A/B/C completion edges exist.

## 10. Recommendation

Recommendation: implement H4-A symmetric reverse completion first as a labelled, deficit-aware, rule-completion probe, not as canonical observed graph construction.

Reason: H4-A has the strongest direct audit signal. The C6 audit found `2,669` missing reverse triples and only `1` observed reverse in frozen Stage2 candidates, so observed-only C6 cannot address the symmetric reverse-completion bottleneck. H4-A should start with underfilled symmetric relations and relation-level caps, then evaluate whether safe deletion becomes possible. H4-B and H4-C have computable opportunity counts, but they require additional controls before generation. H4-D should wait until labelled completion edges exist.
