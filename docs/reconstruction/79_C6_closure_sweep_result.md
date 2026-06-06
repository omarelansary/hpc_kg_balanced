# C6 Closure Sweep Result

## 1. Purpose

This document summarizes the C6 closure sweep after C6 infrastructure validation. It is not a KGE result document and not a final benchmark selection document. The sweep evaluates whether observed canonical allocated additions, followed by strict safe deletion where enabled, can improve B0 while preserving the hard structural constraints.

## 2. Inputs and Scope

- Starting graph: B0 / connected realization, `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`.
- Candidate source: frozen Stage2 shards under `archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards/`.
- Allocation source: `src/Pruning graph/bidirectional_allocation_results5k.json`.
- Supporting context: `docs/reconstruction/77_pre_kge_branch_status_lock.md`, `docs/reconstruction/78_C6_observed_canonical_densification_design.md`, and `artifacts/final_graph/selected_final_graph/rebuild/pre_kge_branch_status_lock.json`.
- No WDQS, LLM, KGE, or SLURM execution was used for this sweep summary.
- C6 uses observed canonical allocated candidate triples only. C6-D allows semi-internal candidates, but still requires canonical allocated relations and no auxiliary, synthetic, live, WDQS, or LLM evidence.
- Generated outputs stayed under `experiments/graph_candidates/C6_observed_canonical_densification/runs/`.

## 3. Acceptance Criteria

Hard constraints:

- weak component count `1`;
- `139/139` allocated relation coverage;
- duplicate-free graph;
- observed canonical allocated triples only;
- no hidden auxiliary or synthetic edges;
- generated artifacts confined to the C6 run directory.

Improvement criteria:

- lower surplus than B0;
- lower or non-worse deficit than B0;
- composition surplus not worse, if available;
- density non-worse or improved, if available;
- no original-entity loss, if checked;
- no deficit-increasing deletions under strict config.

## 4. Run Summary Table

Reference B0: `24,683` triples, surplus `6,702`, deficit `2,019`, weak component count `1`, relation coverage `139/139`, duplicate triple count `0`, composition surplus `6,266.934`, symmetric deficit `1,378.903`, and `1.1274` triples per entity.

| run_id / label | mode | adds | deletes | triples | surplus | delta_surplus_vs_B0 | deficit | delta_deficit_vs_B0 | WCC | coverage | decision | interpretation |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| B0 | frozen connected baseline | 0 | 0 | 24,683 | 6,702 | 0 | 2,019 | 0 | 1 | 139/139 | reference_baseline | Current provisional connected baseline. |
| C6-A internal strict addition | strict internal addition only | 274 | 0 | 24,957 | 6,959 | +257 | 2,002 | -17 | 1 | 139/139 | addition_only | Diagnostic only; additions improve deficit slightly but worsen surplus. |
| C6-B strict add-delete cap 250 | strict internal add then capped safe delete | 274 | 250 | 24,707 | 6,709 | +7 | 2,002 | -17 | 1 | 139/139 | diagnostic_only | Diagnostic only; bounded deletion nearly returns to B0 surplus but does not beat it. |
| C6-C full deletion pass | strict internal add then full safe delete | 274 | 450 | 24,507 | 6,509 | -193 | 2,002 | -17 | 1 | 139/139 | marginal_observed_variant | Best observed C6 configuration under the tested strict sweep; marginal variant worth preserving only if artifact review is desired. |
| C6-D semi-internal bounded | semi-internal bounded add then capped safe delete | 376 | 250 | 24,809 | 6,805 | +103 | 1,996 | -23 | 1 | 139/139 | diagnostic_only | Diagnostic only; deficit improves but surplus worsens and `100` new entities are introduced. |

## 5. Run-by-Run Interpretation

### C6-A Internal Strict Addition

C6-A tested internal-only observed canonical additions with no deletion. It accepted `274` additions, all internal, and preserved weak component count `1`, relation coverage `139/139`, and duplicate-free status. Its additions were dominated by anti-symmetric pattern memberships (`215`), inverse memberships (`69`), and a small symmetric signal (`1`). The top added relations were `P4149` (`49`), `P3461` (`44`), `P527` (`38`), `P1312` (`29`), and `P10624` (`25`).

The run improved total deficit from `2,019` to `2,002`, but surplus worsened from `6,702` to `6,959`. Composition surplus remained `6,266.934`, because composition additions were forbidden while composition was overfilled. C6-A is diagnostic only because addition-only cannot reduce existing surplus.

### C6-B Strict Add-Delete Cap 250

C6-B used the same strict additions as C6-A and then applied capped safe deletion. It accepted `250` deletions while preserving weak component count `1`, relation coverage `139/139`, duplicate-free status, and the original B0 entity universe. Deletions were dominated by `P1312` (`37`), `P10624` (`25`), `P1889` (`24`), `P131` (`20`), and `P279` (`20`).

The final surplus was `6,709`, which is `7` worse than B0, while deficit improved by `17`. Composition surplus dropped to `6,172.934`, but the capped deletion pass was not enough to beat B0 overall. C6-B is diagnostic only.

### C6-C Internal Full Deletion Pass

C6-C used the same strict internal additions as C6-A/B and then removed the `250` smoke cap by processing the safe deletion list until no further valid deletion remained under the strict guards. It accepted `450` deletions, preserved weak component count `1`, relation coverage `139/139`, duplicate-free status, and original B0 entities, and rejected deficit-increasing deletions.

C6-C reduced surplus from `6,702` to `6,509` (`-193`) and deficit from `2,019` to `2,002` (`-17`). It also reduced triples from `24,683` to `24,507` (`-176`). Composition surplus decreased from `6,266.934` to `6,159.705`; triples per entity decreased from `1.1274` to `1.1194`, so density did not improve. The top deleted relations were `P527` (`102`), `P4149` (`49`), `P3461` (`44`), `P1312` (`37`), and `P10624` (`25`).

C6-C is the strongest observed-only configuration from this sweep, but its improvement is modest. It is a marginal variant worth preserving only if artifact review is desired, not automatically final and not a promoted candidate.

### C6-D Semi-Internal Bounded

C6-D allowed internal plus semi-internal candidates with a small new-entity budget, while retaining canonical allocated relations and the strict no-composition-overfilled policy. It accepted `376` additions, including `274` internal and `102` semi-internal additions, using `100` new entities. The additions were dominated by `P2959` (`98`), followed by the same internal-heavy relations seen in C6-A/B/C. Pattern memberships were anti-symmetric (`215`), inverse (`71`), and symmetric (`103`).

After capped safe deletion, C6-D improved deficit from `2,019` to `1,996`, but surplus worsened from `6,702` to `6,805`. It remained connected, relation-complete, and duplicate-free. The added semi-internal entities make it less clean than C6-C, and the surplus regression prevents promotion.

## 6. C6-C Candidate Assessment

C6-C is the best observed C6 configuration under the tested strict sweep. It modestly improves both surplus and deficit while preserving the key hard constraints:

- B0 surplus `6,702` -> C6-C surplus `6,509`, delta `-193`.
- B0 deficit `2,019` -> C6-C deficit `2,002`, delta `-17`.
- B0 triples `24,683` -> C6-C triples `24,507`, delta `-176`.
- weak component count remains `1`.
- allocated relation coverage remains `139/139`.
- duplicate triple count remains `0`.
- composition surplus improves from `6,266.934` to `6,159.705`.
- triples per entity decreases from `1.1274` to `1.1194`, so density is slightly worse by this metric.

C6-C does not achieve a new hard constraint beyond B0. It preserves B0's hard constraints and modestly improves surplus and deficit, but density worsens and exact balance remains unresolved. C6-C is not globally optimal, not a perfect balance solution, and not a final benchmark KG. It is not strong enough to replace B0 by itself. It should be preserved or reviewed only if a human wants artifact review for a marginal observed-only variant, and it should not replace B0 until the branch status lock and candidate registry decision are explicitly updated.

## 7. Observed Symmetric Reverse-Completion Bottleneck

A read-only audit of B0 symmetric-relation triples, the frozen Stage2 candidate shards, and the C6-A census/additions found:

- B0 symmetric-relation triples: `4,051`.
- Missing reverse triples for B0 symmetric-relation triples: `2,669`.
- Missing reverse triples found in frozen Stage2 candidates: `1`.
- Missing reverse triples accepted by C6-A: `1`.

This means C6 did not fail to improve symmetry because the scoring under-prioritized eligible observed reverse completions. The observed frozen reverse-completion evidence is nearly absent. Under the C6 definition, missing reverse triples outside frozen observed candidate shards cannot be added; adding them would require a separate labelled rule-completion or synthetic branch.

Implication: a symmetric-first C6 rerun under the same observed/internal/frozen constraints is not justified. If synthetic or rule-derived edges are allowed, the next direction should be H4 labelled rule-completion for underfilled verified patterns, not another C6 observed-only run.

The first H4 target should be symmetric reverse-completion because the C6 audit found `2,669` missing reverse triples and only `1` observed reverse in frozen Stage2 candidates. This motivates symmetry as the first and safest H4 subcase, not the whole H4 scope.

H4 should explicitly separate pattern-specific rule-completion subcases:

- Symmetry: possible reverse completion.
- Inverse: possible inverse-pair completion.
- Composition: possible shortcut completion.
- Anti-symmetry: no automatic reverse completion; additions require observed evidence or separate relation-specific justification.

H4 must label every added edge by rule type and evidence regime. H4 edges are not canonical observed triples.

A later H4-D configuration should test the sequential effect: apply labelled rule-completion first, recompute structure, then rerun strict safe deletion to check whether surplus edges become removable.

## 8. Why C6-A/B/D Are Not Promoted

- C6-A addition-only worsened surplus by `+257` despite improving deficit by `-17`. It cannot remove existing overrepresented edges, so it remains diagnostic.
- C6-B capped deletion improved deficit by `-17` and composition surplus, but final total surplus was still `+7` worse than B0. The `250` deletion cap was not enough to make it a candidate.
- C6-D improved deficit by `-23`, but surplus worsened by `+103` and the run introduced `100` new entities. It is useful diagnostic evidence for semi-internal additions, but less clean than C6-C.

## 9. Safe Claims and Unsafe Claims

Safe claims:

- C6 infrastructure can perform controlled observed canonical additions and safe deletion.
- C6-C is the best observed C6 run in this sweep.
- C6-C modestly improves B0 surplus and deficit while preserving weak component count `1` and relation coverage `139/139`.
- Observed frozen reverse-completion evidence is insufficient for C6 to solve the symmetric deficit.
- C6 does not solve exact balance.

Unsafe claims:

- C6-C is globally optimal.
- C6-C is the final benchmark KG.
- C6 solves composition surplus completely.
- C6 proves no better candidate exists.
- C6 KGE behavior is known.
- C6 tested H4 labelled rule-completion for underfilled verified patterns.

## 10. Decision Recommendation

Decision recommendation: `close_C6_observed_only_for_now`.

C6-C should be treated as a marginal observed-only variant because it is the only tested C6 run that improves both surplus and deficit while preserving the hard constraints. The effect is modest, density worsens, and C6 cannot address most symmetric reverse-completion gaps because the frozen observed candidate evidence is absent. C6 is closed for now as an observed-only branch under the frozen candidate evidence. Do not commit generated C6 graph outputs yet. Do not update the candidate registry without a separate human artifact-promotion decision.

## 11. Next Actions

1. Commit C6 infrastructure/code only, if not already committed.
2. Keep generated run outputs uncommitted.
3. Do not promote C6-C unless a separate human artifact review explicitly decides to preserve and register it.
4. Open H4 labelled rule-completion for underfilled verified patterns if synthetic or rule-derived edges are allowed.
5. Update `docs/reconstruction/77_pre_kge_branch_status_lock.md` only if a future candidate decision or H4 plan changes the branch map.
6. If any C6-derived graph is used for KGE, lock KG artifact path/hash and KGE protocol first.
