# C5-H2 Diversity Light Cap-50 Candidate Decision

## Purpose

This note records the selected C5-H2 diversity-aware cap-50 result as a clean candidate package for human decision. The selected package is:

`experiments/graph_candidates/C5_H2_diversity_light_cap50/`

The package is derived from the diversity reranking probe artifact:

`experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/diversity_probe/relation_diversity_penalty_light/cap_50/`

## Selected Result

- Candidate ID: `C5_H2_diversity_light_cap50`
- Parent candidate: `B0`
- Strategy: `relation_diversity_penalty_light`
- Cap: `50`
- Acceptance classification: `c5_h2_candidate_passed_policy`
- Recommended status: `experimental_candidate_pending_artifact_preservation`

## Metrics

| Metric | Value |
| --- | ---: |
| Auxiliary edges selected | 50 |
| Canonical edges removed | 50 |
| Canonical surplus delta | -50.0 |
| Canonical deficit delta | 0.0 |
| Full graph weak components | 1 |
| Canonical-only weak components | 49 |
| Full graph triples | 24,683 |
| Canonical-only triples | 24,633 |
| Auxiliary relation count | 48 |
| P17 count | 1 |
| P17 share | 0.020 |

## Hashes

Graph JSONL outputs are referenced, not copied into the selected package:

| Output | SHA256 |
| --- | --- |
| `graph.jsonl` | `17c082efa49384f0f162b37551d7f7c8a221e73e2cdd7e726a1e018db8ead540` |
| `canonical_edges.jsonl` | `efa6ed429e4328744a6049148f82dd7134d9f195cf768a3417a8dd5a5e85576b` |
| `auxiliary_edges.jsonl` | `802f280163984859a78d649565174673e39719d50d9f1c00eb03ecac732cf12a` |
| `removed_canonical_edges.jsonl` | `a2a28dfae6b9d42977e3f9ba30825d20480f6da024abfbd36c84653c83992590` |

Copied report hashes are recorded in `experiments/graph_candidates/C5_H2_diversity_light_cap50/manifest.json`.

## Decision Rationale

The selected diversity-aware cap-50 result preserves the cap-50 surplus improvement from the baseline C5-H2 candidate while fixing the P17 concentration problem. Baseline cap 50 used `39/50` P17 auxiliary edges; the diversity-aware result uses `1/50`, with no surplus cost and no deficit increase.

The result remains auxiliary-dependent. The full graph is connected with auxiliary edges, but canonical-only connectivity has `49` weak components. The auxiliary edges are observed in frozen local evidence but unallocated, so they are not canonical benchmark triples and do not count toward canonical allocation surplus/deficit.

## Registry Decision

Do not update `candidate_registry.v1.json` yet.

Registry update should wait until:

- graph JSONL outputs are preserved in external artifact storage or Git LFS;
- the auxiliary-edge status is accepted by human decision;
- the registry row can explicitly distinguish canonical allocated observed edges from auxiliary unallocated observed edges.

## Safe Claim

C5-H2 diversity-aware reranking produced an experimental auxiliary-connectivity candidate that preserves full connectivity with 50 observed unallocated auxiliary edges, removes 50 surplus canonical bridge edges, reduces canonical surplus by 50 without increasing canonical deficit, and lowers cap-50 P17 auxiliary concentration from `39/50` to `1/50`.

## Unsafe Claims

- Do not claim this is a canonical allocation-faithful graph.
- Do not claim auxiliary unallocated edges are canonical benchmark triples.
- Do not claim this supersedes B0 without a registry decision.
- Do not claim exact end-to-end generation reproducibility beyond the frozen local evidence and generator outputs recorded here.
