# Stage 2 Partial Sweep Presentation Assessment

Scope: read-only assessment of the completed outputs under `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage2_branch_sweep_20260424_095629`. No graph was regenerated, no branch was rerun, and no thesis LaTeX was modified.

## Executive Conclusion

- Recommendation: `Use only in backup`
- One-sentence defense wording: `A post-hoc Stage 2 continuation from the locked Stage 1 structural_softening graph preserved weak connectivity, full 139/139 allocated-relation coverage, and duplicate-free triples in two completed branches, but both branches substantially increased total quota deficit and therefore did not change the final selection of B0.`
- One-sentence limitation wording: `The Stage 2 sweep remained partial because backbone_fringe_trim timed out, and the completed outputs were not promoted into the registered graph-candidate set, so they should be framed as exploratory continuation evidence rather than as a new defended result.`
- Does Stage 2 change the selected final graph decision? `No`

## 1. Candidate Status

The two completed Stage 2 branches are technically evaluator-valid graph artifacts:

- they are duplicate-free
- they remain in one weakly connected component
- they observe all `139/139` allocated relations
- they have zero allocated-relation absence

However, they are **not** currently formal thesis graph candidates:

- they are not listed in `docs/reconstruction/graph_candidates.tsv`
- they are not registered in the existing B0/C1/C2 decision records
- the sweep itself is incomplete because `backbone_fringe_trim` timed out and produced no required outputs

Safe classification:

- `core_density_first`: evaluator-valid graph artifact, but only exploratory partial output for presentation purposes
- `core_two_path_first`: evaluator-valid graph artifact, but only exploratory partial output for presentation purposes
- `backbone_fringe_trim`: failed branch, not usable

## 2. Evidence Table

| Artifact | Status | Graph path | SHA256 | Triples | Entities | Relations | Weak comps | Coverage | Zero allocated absent | Duplicate triples | Total deficit | Total surplus | P31 | P279 | P131 | Notes |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `B0` | selected final graph | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` | 24683 | 21893 | 139 | 1 | 139/139 | 0 | 0 | 2019 | 6702 | 5957 (+5719) | 750 (+523) | 353 (+174) | Final selected graph |
| `C1` | nonselected registered candidate | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl` | `e01d7137c1dbcd790082825a025cade7198a957b3c936f0d9b5b3f0b33780b73` | 24223 | 21893 | 139 | 1 | 139/139 | 0 | 0 | 2359 | 6582 | 5953 (+5715) | 748 (+521) | 344 (+165) | Registered comparison candidate |
| `C2` | rejected registered candidate | `experiments/graph_candidates/C2_targeted_generic_pruning/outputs/pruned_graph.jsonl` | `a017ac53fe6ead1f81b26a3cd4c10679eb14036aad40144039d1ed2185d53da0` | 24656 | 21893 | 139 | 1 | 139/139 | 0 | 0 | 2019 | 6675 | 5952 (+5714) | 744 (+517) | 337 (+158) | Rejected after threshold failure |
| `core_density_first` | completed Stage 2 branch | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage2_branch_sweep_20260424_095629/core_density_first/stage2_graph.jsonl` | `14f9bb9bfb576dd1f00dec8f9e95a2f6e8e17fee6464d84f4547f2d4d791d65a` | 21850 | 19393 | 139 | 1 | 139/139 | 0 | 0 | 4689 | 6539 | 5930 (+5692) | 738 (+511) | 344 (+165) | Completed but not registered candidate |
| `core_two_path_first` | completed Stage 2 branch | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage2_branch_sweep_20260424_095629/core_two_path_first/stage2_graph.jsonl` | `fcc5a715bb650b03a660e57a766cf6c2c224ef195d882ffb272a821f21193eac` | 21850 | 19393 | 139 | 1 | 139/139 | 0 | 0 | 4694 | 6544 | 5934 (+5696) | 739 (+512) | 344 (+165) | Completed but not registered candidate |
| `backbone_fringe_trim` | failed Stage 2 branch | none | none | none | none | none | none | none | none | none | none | none | none | none | none | SLURM timeout after 2 days |

## 3. What Stage 2 Preserved

For both completed Stage 2 branches:

- weak connectivity: preserved (`1` weak component, largest weak component ratio `1.0`)
- allocated relation coverage: preserved (`139/139`)
- zero allocated relation absence: preserved (`0`)
- duplicate-free triples: preserved (`0`)

So the Stage 2 issue is **not** structural invalidity. The issue is the allocation tradeoff.

## 4. Allocation Tradeoff Against the Canonical 5k Allocation

Both completed branches reduce generic surplus modestly relative to `B0` and `C1`, but they do it by removing a large amount of quota mass:

- `B0`: deficit `2019`, surplus `6702`
- `C1`: deficit `2359`, surplus `6582`
- `C2`: deficit `2019`, surplus `6675`
- `core_density_first`: deficit `4689`, surplus `6539`
- `core_two_path_first`: deficit `4694`, surplus `6544`

Interpretation:

- compared with `B0`, each completed Stage 2 branch reduces surplus by only about `163` or `158`
- but compared with `B0`, each completed Stage 2 branch worsens deficit by about `2670` or `2675`
- compared with `C1`, each completed Stage 2 branch reduces surplus by only `43` or `38`
- but compared with `C1`, each completed Stage 2 branch worsens deficit by about `2330` or `2335`

This is not a favorable thesis tradeoff under the current decision logic.

## 5. Density / Size Comparison

Derived density metrics:

| Graph | Triples minus entities | Triples per entity | Entities per triple | Average participation |
| --- | ---: | ---: | ---: | ---: |
| `B0` | 2790 | 1.127438 | 0.886967 | 2.254876 |
| `C1` | 2330 | 1.106427 | 0.903810 | 2.212853 |
| `C2` | 2763 | 1.126205 | 0.887938 | 2.252409 |
| `core_density_first` | 2457 | 1.126695 | 0.887551 | 2.253390 |
| `core_two_path_first` | 2457 | 1.126695 | 0.887551 | 2.253390 |

Important consequence:

- the completed Stage 2 branches are denser than `C1`
- but they are not materially denser than `B0` or `C2`
- they achieve this by shrinking to `19,393` entities and `21,850` triples, which substantially increases allocation deficit

So Stage 2 is not producing a new dominant candidate frontier. It is mostly trading away quota mass while keeping the core graph connected.

## 6. Difference Between the Two Completed Stage 2 Branches

The two completed Stage 2 branches are extremely close:

- same triples: `21850`
- same entities: `19393`
- same connectivity: `1` weak component
- same relation coverage: `139/139`
- same zero allocated relation absence: `0`
- same duplicate count: `0`

The only meaningful difference visible in the preserved reports is:

- `core_two_path_first` kept a slightly higher `two_path_count` (`20845` vs `20806`)
- but it also ended with slightly worse allocation totals (`deficit 4694`, `surplus 6544`) than `core_density_first` (`deficit 4689`, `surplus 6539`)

This is too small to support a new main-claim branch before the presentation.

## 7. Governance / Decision-Record Status

Current repo decision state:

- `B0`, `C1`, and `C2` are the registered graph candidates
- `C3_probe_v1` is explicitly evidence only, not a graph candidate
- the Stage 2 completed branches are not registered in `docs/reconstruction/graph_candidates.tsv`
- no Stage 2 branch decision record currently connects them into the defended B0/C1/C2 selection chain

Therefore, even though the completed Stage 2 outputs are valid graph artifacts, they are not yet thesis-level candidate artifacts in the same governance sense as `B0`, `C1`, and `C2`.

## 8. Answers to the Presentation Questions

### Q1. Are the two completed Stage 2 branches valid graph candidates or only exploratory partial outputs?

They are evaluator-valid graph artifacts, but for presentation purposes they should be treated as **exploratory partial outputs**, not as formal graph candidates.

### Q2. Do they preserve weak connectivity, 139 relation coverage, zero allocated relation absence, and duplicate-free triples?

Yes, both completed branches preserve all four conditions.

### Q3. What are their canonical allocation metrics?

- `core_density_first`: surplus `6539`, deficit `4689`, allocated relations observed `139`, zero allocated relations `0`, `P31=5930 (+5692)`, `P279=738 (+511)`, `P131=344 (+165)`
- `core_two_path_first`: surplus `6544`, deficit `4694`, allocated relations observed `139`, zero allocated relations `0`, `P31=5934 (+5696)`, `P279=739 (+512)`, `P131=344 (+165)`

### Q4. How do they compare against B0, C1, and C2?

They remain structurally valid, but they are substantially smaller and much more deficit-heavy than `B0`, `C1`, and `C2`, while only modestly improving surplus.

### Q5. Did either completed Stage 2 branch clearly improve the final decision?

No.

### Q6. Can either branch be safely mentioned in the main presentation?

Not as a new result. At most they can be mentioned in backup as negative or ongoing continuation evidence.

### Q7. If yes, what exact sentence is safe?

Safe backup sentence:

`A post-hoc Stage 2 continuation from the locked structural_softening base preserved connectedness and full allocated-relation coverage, but the completed deletion-only branches increased total quota deficit too strongly to justify replacing the selected B0 graph.`

### Q8. If no, what exact sentence should frame it as ongoing/partial work?

`We also tested a partial Stage 2 continuation beyond structural_softening; two completed non-synthetic branches stayed connected and coverage-complete, but because they remained exploratory and worsened allocation deficit substantially, they are reported only as ongoing continuation evidence and not as new graph candidates.`

### Q9. Should backbone_fringe_trim be rerun before presentation?

No. It timed out after two days, and the two completed branches already show that the current Stage 2 deletion-only continuation does not overturn the B0/C1/C2 decision frontier. A pre-presentation rerun is high-risk and low-yield.

### Q10. What is the strongest presentation-safe conclusion from Stage 2?

The strongest safe conclusion is:

`Deletion-only Stage 2 continuation can preserve connectedness and complete allocated-relation coverage on top of the structural_softening base, but in the completed runs it did so only by discarding too much allocation mass, so it does not change the selected final graph decision.`

## 9. Final Recommendation

- Use in main slides: `No`
- Use only in backup: `Yes`
- Do not mention at all: `No`, unless slide time is extremely tight

Practical recommendation:

- keep `B0` as the defended final graph
- if asked about “what you tried next,” mention Stage 2 only as brief backup evidence
- do not present Stage 2 as a new candidate set or a near-miss replacement for `B0`
