# C4 Probe-Only Bridge-Aware Replace/Add Generator

## Purpose

`tools/graph_candidate_generation/c4_probe_bridge_aware_replace_add.py` is a probe-only utility for the planned `C4_bridge_aware_replace_add` experiment. It tests whether frozen local replacement evidence can support balance-improving remove/replace or controlled-addition moves from B0 without violating hard graph constraints.

This is not a graph generator. It does not write `outputs/graph.jsonl`, does not update `candidate_registry.v1.json`, and does not modify B0.

## Inputs

The probe reads:

- `experiments/graph_candidates/C4_bridge_aware_replace_add/configs/config.template.json`
- B0 parent graph from the config:
  `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Canonical allocation from the config:
  `src/Pruning graph/bidirectional_allocation_results5k.json`
- Frozen eligible replacement pool:
  `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/eligible_replacement_candidates.jsonl`

The config currently names `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_replacement_candidates.jsonl`. The probe first checks that configured path, then checks the restored `eligible_v1/` location and records the resolution in `probe_report.json`. If neither exists, it fails with:

```text
replacement pool missing; restore optional C3 replacement pool artifact or run a no-pool diagnostic mode if implemented
```

## Probe Logic

The probe computes baseline B0 metrics with the reusable candidate evaluator, identifies surplus target-generic edges in `P31`, `P279`, and `P131`, and classifies each tested target edge as:

- `deletion_safe`: removing the edge does not break weak connectivity.
- `connectivity_critical`: removing the edge would split the weak component.

For deletion-safe target edges, the probe checks whether removal reduces surplus without creating a zero allocated relation or increasing deficit.

For connectivity-critical target edges, the probe tests eligible replacement edges by adding the replacement and removing the target edge as an independent feasibility test. A feasible move must preserve:

- `weak_component_count = 1`
- `zero_allocated_relations = 0`
- `duplicate_triple_count = 0`
- `allocated_relations_observed = 139`

The probe rejects duplicate replacement triples, unallocated replacement relations, replacement endpoints outside B0, and replacements that do not reconnect the bridge cut. It records independent feasible moves and a greedy non-reuse upper bound, but it does not claim those moves can be composed into a final graph.

## Outputs

The probe writes only:

- `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/probe_report.json`
- `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/probe_summary.md`

It refuses to overwrite these files unless `--force` is passed. `--dry-run` prints the resolved input paths and writes nothing.

## Validation Run

The bounded validation run used:

```bash
python tools/graph_candidate_generation/c4_probe_bridge_aware_replace_add.py \
  --config experiments/graph_candidates/C4_bridge_aware_replace_add/configs/config.template.json \
  --max-target-edges 200 \
  --max-replacement-candidates 1000 \
  --force
```

Observed baseline B0 metrics:

- Unique triples: 24,683
- Unique entities: 21,893
- Unique relations: 139
- Weak components: 1
- Duplicate triples: 0
- Allocated relations observed: 139
- Zero allocated relations: 0
- Total surplus: 6,702
- Total deficit: 2,019

Observed probe result:

- Target edges tested: 200
- Replacement candidates loaded: 990
- Deletion-safe targets: 0
- Connectivity-critical targets: 200
- Feasible safe deletions: 0
- Connectivity-critical targets with feasible replacement: 0
- Greedy non-reuse candidate count: 0

The bounded run therefore did not find a C4 bridge-rescue move for the tested target edges. This is feasibility evidence only; it is not a candidate graph result.

## Limits

The probe is bounded by `--max-target-edges` and `--max-replacement-candidates`. It tests independent moves, not a globally optimized move sequence. It does not use WDQS, LLMs, or network sources, and it does not implement controlled relation addition beyond checking frozen replacement/addition triples from the eligible local pool.
