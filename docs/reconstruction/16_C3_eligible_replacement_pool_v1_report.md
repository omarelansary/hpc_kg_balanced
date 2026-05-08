# C3 Eligible Replacement Pool v1 Report

Status: ranked eligible subset created. This is not C3 output, no graph candidate was generated, no live WDQS query was made, and `docs/reconstruction/graph_candidates.tsv` was not edited.

## Why The Full Pool Is Too Noisy

The full frozen pool is reproducible but too broad for direct C3 consumption.

Evidence from `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/pool_profile.json`:

| Full-pool metric | Value |
| --- | ---: |
| Final candidates | 871166 |
| Unallocated candidates | 626267 |
| Overfilled-relation candidates | 236548 |
| `P31` / `P279` / `P131` target-generic candidates | 193375 |
| Candidates with no B0 endpoint overlap | 571862 |
| `state_query_cache` candidates | 842244 |

These categories are risky for C3 because C3 is intended to replace connectivity-supporting generic edges with balance-improving alternatives. Consuming the full pool blindly would make it easy to add unallocated relations, add already-overfilled relations, add more `P31`/`P279`/`P131`, or introduce disconnected new structure.

## Created Files

Created directory:

```text
artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/
```

Created files:

| File | Role | SHA256 |
| --- | --- | --- |
| `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/eligible_replacement_candidates.jsonl` | Ranked eligible replacement candidates | `5440075235b69bd9586c602371ad80202fe805c9d27235efb4de5e90796d061e` |
| `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/eligible_pool_profile.json` | Machine-readable eligible subset profile | `69211bc06ce343e72aa4bab12d2b4967ed80304bf7430a18adf610be8718e960` |
| `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/eligible_hashes.tsv` | Hash table for eligible outputs and source pool inputs | `6dbb059b94f4042dd5934d19c1373d40f8ef8ac86e5827571acf89d10595eb49` |

Filtering script:

- `tools/graph_candidate_generation/filter_c3_replacement_pool.py`

Command run:

```bash
python tools/graph_candidate_generation/filter_c3_replacement_pool.py
```

## Source Inputs

| Source | SHA256 |
| --- | --- |
| `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/replacement_candidates.jsonl` | `ec9024a0f76dc3d3259c19f66b2f9384d0239da701a96a8e2611946b00e8d7fe` |
| `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/pool_profile.json` | `2629396633110027b95e7578b43c81b22832603f2d9a36d2da7c7a2561a5a29d` |

`eligible_hashes.tsv` omits a self-hash row because a stable self-referential hash for the file that contains its own hash is not feasible. The actual SHA256 of `eligible_hashes.tsv` after creation is reported above.

## Eligible Filtering Policy

Hard include:

- `endpoint_overlap_with_b0` in `both`, `one`
- `relation_allocation_status` in `underfilled`, `near_target`
- `is_target_generic_relation == false`
- relation not in `P31`, `P279`, `P131`
- `h`, `r`, and `t` present and non-empty

Hard exclude:

- `endpoint_overlap_with_b0 == none`
- `relation_allocation_status` in `overfilled`, `unallocated`
- `is_target_generic_relation == true`
- relation in `P31`, `P279`, `P131`

Provenance policy:

- Keep `event_bridge_triples`.
- Keep `event_path_triples`.
- Keep `state_added_core_triples` and `state_added_path_triples` if present.
- Exclude `state_query_cache` unless the candidate is `underfilled` and has `endpoint_overlap_with_b0 == both`.

Ranking policy:

| Condition | Score contribution |
| --- | ---: |
| `relation_allocation_status == underfilled` | +100 |
| `relation_allocation_status == near_target` | +40 |
| `endpoint_overlap_with_b0 == both` | +30 |
| `endpoint_overlap_with_b0 == one` | +10 |
| `provenance_type` is event bridge/path | +30 |
| `provenance_type` is state added core/path | +20 |
| `provenance_type == state_query_cache` | -20 |
| grouped path with more than one eligible edge | -50 |
| relation is `P31`/`P279`/`P131` | -1000 |
| relation is overfilled or unallocated | -1000 |

Each eligible row has `score`, `path_group_size`, and `path_group_score`.

## Eligible Pool Counts

| Metric | Value |
| --- | ---: |
| Total input candidates | 871166 |
| Total eligible candidates | 990 |
| Warning if eligible count too small | none |

Primary exclusion counts are mutually exclusive and sum to the excluded candidate total:

| Primary exclusion reason | Count |
| --- | ---: |
| `endpoint_overlap_none` | 571862 |
| `relation_allocation_status_overfilled` | 122529 |
| `relation_allocation_status_unallocated` | 171659 |
| `state_query_cache_policy_exclusion` | 4126 |

All-reason exclusion counts are not mutually exclusive:

| Exclusion reason | Count |
| --- | ---: |
| `endpoint_overlap_none` | 571862 |
| `relation_allocation_status_unallocated` | 626267 |
| `relation_allocation_status_overfilled` | 236548 |
| `is_target_generic_relation` | 193375 |
| `relation_is_P31_P279_or_P131` | 193375 |
| `state_query_cache_policy_exclusion` | 841668 |

## Eligible Distribution

By source stage:

| Source stage | Candidates |
| --- | ---: |
| `stage11` | 785 |
| `stage12` | 205 |

By provenance:

| Provenance type | Candidates |
| --- | ---: |
| `state_query_cache` | 576 |
| `event_bridge_triples` | 210 |
| `event_path_triples` | 204 |

By endpoint overlap:

| Endpoint overlap | Candidates |
| --- | ---: |
| `both` | 612 |
| `one` | 378 |

By allocation status:

| Allocation status | Candidates |
| --- | ---: |
| `underfilled` | 759 |
| `near_target` | 231 |

Top eligible relations:

| Relation | Count |
| --- | ---: |
| `P5277` | 194 |
| `P2959` | 69 |
| `P2500` | 68 |
| `P2499` | 52 |
| `P1445` | 52 |
| `P1753` | 47 |
| `P3403` | 42 |
| `P2935` | 36 |
| `P4329` | 32 |
| `P3032` | 29 |

Score distribution:

| Score | Candidates |
| --- | ---: |
| 80 | 230 |
| 100 | 1 |
| 110 | 576 |
| 140 | 148 |
| 160 | 35 |

Path groups:

| Metric | Value |
| --- | ---: |
| Unique path groups | 204 |
| Rows with path group | 204 |
| Path groups of size 1 | 204 |

## Sufficiency For C3 Generator Design

Evidence-based assessment: eligible_v1 is sufficient for designing a first C3 remove-and-replace generator, but it is intentionally conservative.

Why it is sufficient:

- It reduces the candidate set from 871166 to 990 rows.
- It removes all `P31`, `P279`, and `P131` candidates.
- It removes all overfilled and unallocated relation candidates.
- It removes all candidates with no B0 endpoint overlap.
- It keeps candidates with explicit event provenance and a restricted subset of `state_query_cache` candidates.
- It adds deterministic scores and path group annotations.

Why it may still be insufficient for a successful C3 graph:

- Only 990 candidates remain.
- 576 eligible candidates still come from `state_query_cache`, which has weaker provenance than event bridge/path records.
- The eligible subset is relation-balance oriented; it does not prove that any candidate can replace a bridge-like generic edge while preserving weak connectivity.
- All 204 eligible path groups have size 1 after filtering, so this subset may not contain many multi-edge replacement paths.

## Validation

Completed validation:

- `python -m py_compile tools/graph_candidate_generation/filter_c3_replacement_pool.py`
- `python -m json.tool artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/eligible_pool_profile.json`
- Parsed all 990 eligible JSONL rows as JSON.
- Verified `score`, `path_group_size`, and `path_group_score` exist on every eligible row.
- Verified no `P31`, `P279`, or `P131` rows exist.
- Verified no overfilled or unallocated rows exist.
- Verified no `endpoint_overlap_with_b0 == none` rows exist.
- Verified `eligible_hashes.tsv` rows match actual file hashes.

## Next Step

Design the C3 generator against:

```text
artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/eligible_replacement_candidates.jsonl
```

Do not run C3 yet. The generator design should test add-before-remove swaps, verify weak connectivity after each proposed replacement, reject duplicate triples, preserve all 139 allocated relations, and then use the standard graph candidate evaluator before any accept/reject decision.
