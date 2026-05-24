# C5_H2_diversity_light_cap50

This directory packages the selected C5-H2 diversity-aware cap-50 result for human decision.

The package is derived from:

`experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/diversity_probe/relation_diversity_penalty_light/cap_50/`

It copies report files only. The graph JSONL outputs are not copied here; they are referenced by path and SHA256 in `manifest.json`.

## Status

- Candidate ID: `C5_H2_diversity_light_cap50`
- Parent candidate: `B0`
- Strategy: `relation_diversity_penalty_light`
- Cap: `50`
- Status: `pending_human_registry_decision`
- Recommended status: `experimental_candidate_pending_artifact_preservation`

## Key Metrics

- Candidate passed the C5-H2 policy.
- Auxiliary edges selected: `50`
- Canonical edges removed: `50`
- Canonical surplus delta: `-50.0`
- Canonical deficit delta: `0.0`
- Full graph weak components: `1`
- Canonical-only weak components: `49`
- P17 auxiliary count: `1/50`
- P17 share: `0.020`

## Interpretation

The diversity-aware reranking resolves the cap-50 P17 concentration problem observed in the baseline C5-H2 cap sweep. It preserves the cap-50 surplus improvement while reducing P17 from `39/50` auxiliary edges to `1/50`.

This remains an auxiliary-connectivity candidate. The auxiliary edges are observed in frozen local evidence but are unallocated, so they are not canonical benchmark triples and do not count toward canonical allocation surplus/deficit.

## Registry

Do not update `candidate_registry.v1.json` until:

- graph JSONL artifacts are preserved in Git LFS or external artifact storage;
- a human decision accepts this as an experimental candidate;
- the registry update records the auxiliary-edge caveat explicitly.
