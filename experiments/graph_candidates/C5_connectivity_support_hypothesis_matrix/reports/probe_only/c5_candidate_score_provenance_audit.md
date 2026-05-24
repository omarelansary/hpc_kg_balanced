# C5.1 Candidate Score Provenance Audit

Status: read-only score/provenance audit. No graph candidate was generated.

## H2 Score Coverage

- H2 feasible candidate-cut pairs: `546`
- H2 pairs with old Phase II numeric score fields: `0`
- H2 pairs without old Phase II numeric score fields: `546`
- H2 pairs with score or provenance fields: `546`
- H2 pairs selected by Stage4: `0`
- H2 pairs selected into B0: `0`
- H2 pairs from previously unselected candidate space: `546`

## Score And Provenance Fields Found

| Field | Count |
| --- | ---: |
| `accepted` | 546 |
| `candidate_id` | 546 |
| `classification_label` | 546 |
| `duplicate_provenance_count` | 546 |
| `endpoint_overlap_with_b0` | 546 |
| `in_b0` | 546 |
| `is_primary_source` | 546 |
| `is_target_generic_relation` | 546 |
| `notes` | 546 |
| `path_group_id` | 546 |
| `path_role` | 546 |
| `provenance_type` | 546 |
| `relation_allocation_status` | 546 |
| `source_artifact` | 546 |
| `source_event_type` | 546 |
| `source_record_index` | 546 |
| `source_sha256` | 546 |
| `source_stage` | 546 |

## Source Counts

| Source | H2 Pairs | H2 Pairs With Numeric Score |
| --- | ---: | ---: |
| `frozen_candidate_pools` | 546 | 0 |

## Reuse Assessment

- Classification: `no_score_for_h2_candidates`
- Safe to rank C5-H2 by old score: `False`
- Reason: The H2 candidates do not expose old Phase II numeric score fields in their source rows. They expose provenance fields such as duplicate_provenance_count, source_stage, and provenance_type.

Old Phase II scores should not be used as the primary C5-H2 ranking criterion. Existing fields are useful provenance, but C5-H2 needs bridge-cut support, auxiliary-edge accounting, relation-allocation separation, duplicate-provenance handling, and pruning benefit as explicit ranking factors.

## Notes

- No WDQS query was made.
- No LLM call was made.
- No graph candidate was generated.
- `candidate_registry.v1.json` was not updated.
