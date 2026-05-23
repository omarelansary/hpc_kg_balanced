# C4.2 Local Cut-Crossing Candidate Search

## Purpose

C4.1 showed that the eligible C3 replacement pool did not contain candidates crossing any of the first 200 tested B0 bridge cuts. C4.2 broadens the evidence search to additional frozen local sources to determine whether cut-crossing triples exist elsewhere in preserved artifacts.

This is a read-only evidence search. It does not generate a graph, does not modify B0, and does not update `candidate_registry.v1.json`.

## Inputs

The search uses:

- B0 parent graph:
  `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- C4 config:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/configs/config.template.json`
- C4.1 bridge-cut audit:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/replacement_pool_bridge_cut_audit.json`

Frozen local candidate sources scanned:

- Stage12 graph output:
  `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/graph_output.jsonl`
- Stage11 graph output:
  `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl`
- Stage2 candidate shards:
  `archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards/*.jsonl`
- Frozen candidate pools:
  `artifacts/frozen_candidate_pools/**/*.jsonl`

Generated reports:

- `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/local_cut_crossing_candidate_search.json`
- `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/local_cut_crossing_candidate_search.md`

## Method

The script `tools/graph_candidate_generation/c4_search_local_cut_crossing_candidates.py` recomputes the same first 200 surplus target-generic bridge cuts used by the C4 probe and C4.1 audit. For each cut, it indexes the smaller side of the bridge cut and then scans frozen local candidate triples.

Candidate rows are counted only as cut-crossing evidence when:

- both candidate endpoints are in B0,
- the candidate triple is not already present in B0,
- the endpoints fall on opposite sides of at least one tested bridge cut.

For each cut-crossing candidate, the search records whether the relation is allocated and computes the surplus/deficit delta for replacing the tested target edge with the candidate edge.

## Bounded Search Result

The bounded search used:

```bash
python tools/graph_candidate_generation/c4_search_local_cut_crossing_candidates.py \
  --max-target-edges 200 \
  --force
```

Summary:

| Measure | Count |
| --- | ---: |
| Cuts tested | 200 |
| Cut-crossing candidate rows found | 629 |
| Unique cut-crossing candidates | 625 |
| Allocated cut-crossing candidate rows | 106 |
| Unique allocated cut-crossing candidates | 102 |
| Surplus-reducing candidate-cut pairs | 546 |
| Unique surplus-reducing candidates | 523 |
| Allocated surplus-reducing candidate-cut pairs | 0 |
| Unallocated surplus-reducing candidate-cut pairs | 546 |
| Candidate-cut pairs that would increase deficit | 0 |

Source scan counts:

| Source | Rows scanned | Both endpoints in B0 | Already in B0 | Cut-crossing rows | Allocated crossing rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen candidate pools | 872,156 | 15,995 | 0 | 625 | 102 |
| Stage2 candidate shards | 81,958 | 18,239 | 17,941 | 4 | 4 |
| Stage11 graph output | 24,670 | 24,638 | 24,638 | 0 | 0 |
| Stage12 graph output | 24,715 | 24,683 | 24,683 | 0 | 0 |

## Interpretation

The primary result is `only_unallocated_cut_crossing_candidates_reduce_surplus`.

Unlike the eligible replacement-pool-only audit, the broader local search did find cut-crossing triples. However, the candidates that reduce surplus are unallocated relations and therefore are not valid replacements under the current hard constraints. The allocated cut-crossing candidates found in Stage2 shards and frozen pools do not reduce surplus when paired with removal of the tested P31/P279/P131 bridge targets.

Stage11 and Stage12 graph outputs do not provide new bridge-replacement evidence because the relevant rows are already present in B0 and are excluded from candidate counts.

## Implication

C4.2 narrows the blocker. The problem is not simply that local frozen artifacts contain no bridge-cut-spanning edges. Some cut-crossing evidence exists. The blocker is that the cut-crossing evidence which would improve surplus is outside the canonical allocation relation set, while allocated cut-crossing evidence does not improve surplus.

Future bridge-aware strategies would need one of the following before graph generation is justified:

- a cut-aware candidate source restricted to allocated underfilled or near-target relations,
- a human-approved relaxation that permits adding currently unallocated bridge evidence,
- or a different objective that treats connectivity-preserving unallocated evidence separately from relation-quota balance.

This remains probe evidence only. No C4 graph candidate has been generated.
