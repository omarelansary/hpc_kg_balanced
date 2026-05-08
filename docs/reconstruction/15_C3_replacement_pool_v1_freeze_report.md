# C3 Replacement Pool v1 Freeze Report

Status: frozen local replacement pool created. This is not a C3 graph candidate. C3 has not been run, no graph was generated, and `docs/reconstruction/graph_candidates.tsv` was not edited.

## What Was Created

Created directory:

```text
artifacts/frozen_candidate_pools/C3_replacement_pool_v1/
```

Created files:

| File | Role | SHA256 |
| --- | --- | --- |
| `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/source_manifest.json` | Source, policy, command, and hash manifest | `2a662543fbc3895e8048a84c1a0db05a1aa14ba2a95562fdd7cefa58d397c6f9` |
| `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/replacement_candidates.jsonl` | Normalized deduplicated replacement candidate pool | `ec9024a0f76dc3d3259c19f66b2f9384d0239da701a96a8e2611946b00e8d7fe` |
| `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/pool_profile.json` | Machine-readable pool profile and counts | `2629396633110027b95e7578b43c81b22832603f2d9a36d2da7c7a2561a5a29d` |
| `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/hashes.tsv` | Hash table for pool outputs, source artifacts, B0, and allocation | `9bf4d84c501bdbc4593e44bf9d867bfa39cd772b9402789108eeda88d5f754cb` |

Builder script:

- `tools/graph_candidate_generation/build_c3_replacement_pool.py`

Extraction command:

```bash
python tools/graph_candidate_generation/build_c3_replacement_pool.py
```

Evidence:

- `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/source_manifest.json`
- `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/pool_profile.json`
- `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/hashes.tsv`

## Source Files Used

C3 replacement pool v1 uses Stage11/Stage12 local frozen evidence only.

| Source | Stage | Type | SHA256 |
| --- | --- | --- | --- |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/events.jsonl` | Stage11 | events | `d1f7d5ee50d3a0d602d6f026ffdb0b8129cd9e8c34dd59b43d87d2e7fa0247f8` |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/state.json` | Stage11 | state | `5fd9191eefbfa0c0826b6f8c5dfc94b3185cbc803d0f433b86015c9c1bed75e8` |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/events.jsonl` | Stage12 | events | `6f3b52a5bb2e620e5e13082fbb2a5fd2b353759bebc377d3a07dc43f71568527` |
| `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/state.json` | Stage12 | state | `fe0458cc5c465713a8a8353a0d388ea5677bdbbb196a7028ad9d7d2fa80c4cf1` |

Reference inputs:

| Input | SHA256 |
| --- | --- |
| B0 graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` |
| Canonical allocation: `src/Pruning graph/bidirectional_allocation_results5k.json` | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` |

Extraction policy recorded in `source_manifest.json`:

- Trial9 excluded.
- Live WDQS excluded.
- Candidates already present in B0 excluded.
- Stage11/Stage12 only.
- Raw Stage11/Stage12 files are not intended as future C3 generator inputs.
- No graph generation performed.

## Why Trial9 Was Excluded

Trial9 was excluded because the C3 replacement-pool audit found that Trial9 relation-absence repair candidates are linked to the older allocation file `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json`, not the canonical 5k allocation used for B0/C1/C2. The audit also recorded a Trial9 trial2 graph-output conflict: `repaired_graph.jsonl` currently has the same hash/count as `new_triples_added.jsonl`, while `summary.json` reports a larger graph output.

Evidence:

- `docs/reconstruction/14_C3_replacement_pool_audit.md`
- `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial1/summary.json`
- `data/connectedgraph/trial9/repair_relation_allocated_absence_eta_expected_trial2/summary.json`

## Pool Counts

| Metric | Value |
| --- | ---: |
| Total source records inspected | 291345 |
| Raw candidate triples extracted | 1179079 |
| Unique candidate triples before B0 exclusion | 886605 |
| Candidates excluded because already in B0 | 15439 |
| Final candidate count | 871166 |
| Path group count | 451 |
| Skipped source fields | 0 |

Evidence: `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/pool_profile.json`.

## Distribution Highlights

By source stage:

| Source stage | Candidates |
| --- | ---: |
| `stage11` | 852900 |
| `stage12` | 18266 |

By provenance type:

| Provenance type | Candidates |
| --- | ---: |
| `state_query_cache` | 842244 |
| `event_bridge_triples` | 28223 |
| `event_path_triples` | 699 |

By B0 endpoint overlap:

| Endpoint overlap | Candidates |
| --- | ---: |
| `both` | 15383 |
| `one` | 283921 |
| `none` | 571862 |

By allocation status under the canonical 5k allocation and B0 counts:

| Status | Candidates |
| --- | ---: |
| `underfilled` | 6171 |
| `near_target` | 2180 |
| `overfilled` | 236548 |
| `unallocated` | 626267 |

Target-generic candidate count:

| Relation group | Candidates |
| --- | ---: |
| `P31` / `P279` / `P131` combined | 193375 |

Top relation counts:

| Relation | Candidates |
| --- | ---: |
| `P31` | 139677 |
| `P166` | 33887 |
| `P131` | 30033 |
| `P17` | 28787 |
| `P1412` | 26330 |
| `P279` | 23665 |
| `P1343` | 18729 |
| `P19` | 14676 |
| `P5753` | 14647 |
| `P921` | 14247 |

## Suitability For C3

Evidence-based assessment: the pool is suitable as a frozen local input for designing a C3 remove-and-replace generator, but it is not by itself a high-quality replacement policy.

Reasons it is suitable:

- It is local and hashable.
- It uses Stage11/Stage12 evidence directly linked to the B0 construction lineage.
- It excludes candidates already present in B0.
- It records provenance fields for source artifact, stage, event/state origin, source record index, classification label where available, accepted flag where available, path role, path group, endpoint overlap, and allocation status.
- It avoids live WDQS and excludes Trial9 from v1.

Reasons it still requires careful C3 filtering:

- Most candidates are from `state_query_cache`, which has weaker classification provenance than event bridge/path records.
- 626267 candidates are unallocated under the canonical 5k allocation.
- 236548 candidates are already overfilled relations under B0 counts.
- 193375 candidates are `P31`, `P279`, or `P131`, which are the relations C3 is trying to reduce, not generally add.
- 571862 candidates have no endpoint overlap with B0. These may introduce disconnected new structure unless grouped and evaluated carefully.

## Limitations

This pool does not prove that C3 will improve B0/C1/C2 metrics. It only freezes local candidate evidence so the future C3 generator can be reproducible.

Known limitations:

- No live WDQS validation was performed.
- Query-cache records lack full event-level classification labels.
- Event records can represent multiple lifecycle stages; the builder deduplicates by h/r/t and keeps the strongest available provenance according to deterministic ranking.
- Path grouping is preserved only where event `path_triples` provide record-level grouping. State-level `added_path_triples` are flattened in the source and therefore do not preserve original path groups.
- Relation allocation status is computed against B0 counts and canonical 5k eta: `underfilled` if observed is below eta, `near_target` if observed equals eta, `overfilled` if observed is above eta, and `unallocated` if the relation is absent from the allocation.

## Validation

Completed validation:

- `python -m py_compile tools/graph_candidate_generation/build_c3_replacement_pool.py`
- `python -m json.tool artifacts/frozen_candidate_pools/C3_replacement_pool_v1/source_manifest.json`
- `python -m json.tool artifacts/frozen_candidate_pools/C3_replacement_pool_v1/pool_profile.json`
- Read all 871166 lines of `replacement_candidates.jsonl` as JSON.

## Next Step

Plan the C3 generator to consume:

```text
artifacts/frozen_candidate_pools/C3_replacement_pool_v1/replacement_candidates.jsonl
```

Do not run C3 yet. The next design step should define replacement selection rules that strongly prefer underfilled or near-target allocated relations, avoid adding `P31`/`P279`/`P131`, reject duplicate triples, verify weak connectivity after add/remove swaps, and run the standard graph candidate evaluator before any accept/reject decision.
