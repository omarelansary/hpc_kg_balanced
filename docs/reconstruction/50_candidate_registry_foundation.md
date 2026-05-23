# Phase II-B Candidate Registry Foundation

This implementation adds a reusable graph-candidate registry foundation for the controlled reconstruction and future candidate-comparison workflow.

The registry file is:

`artifacts/final_graph/selected_final_graph/rebuild/candidate_registry.v1.json`

The reusable helper module is:

`src/kg_pipeline/registry/candidate_registry.py`

The validation script is:

`scripts/reconstruction/check_candidate_registry.py`

## Why The Registry Exists

Candidate metadata was previously spread across:

- `docs/reconstruction/graph_candidates.tsv`;
- final graph decision documents;
- per-candidate experiment folders;
- reconstruction notes;
- hardcoded compatibility-check scripts.

The JSON registry creates one machine-readable index for graph candidates and evidence-only entries. It records graph paths, hashes, allocation linkage, report paths, report schemas, decisions, parent relationships, and evidence paths.

## Current Registry Entries

| Candidate | Role | Graph candidate | Decision |
| --- | --- | --- | --- |
| `B0` | `selected_baseline` | true | `selected_as_current_connected_reference_baseline` |
| `C1` | `active_candidate` | true | `not_selected_after_final_decision` |
| `C2` | `rejected_candidate` | true | `rejected_as_final_kept_as_exploratory_evidence` |
| `strict_balance_pruned_ablation` | `diagnostic_ablation` | true | `diagnostic_balance_first_stress_test_not_final` |
| `C3_probe_v1` | `probe_only` | false | `full_bridge_rescue_not_recommended_with_eligible_pool_v1` |

`C3_probe_v1` is explicitly not a graph candidate. It has a probe report and evidence paths, but no `graph_path` and no graph hash.

## Registry Schema

Top-level fields:

- `schema_version`: currently `kg-candidate-registry-v1`;
- `created_from`;
- `canonical_allocation_path`;
- `canonical_allocation_sha256`;
- `candidates`.

Each candidate row records:

- `candidate_id`;
- `label`;
- `role`;
- `is_graph_candidate`;
- `status`;
- `decision`;
- `parent_candidate_id`;
- `graph_path`;
- `graph_sha256`;
- `allocation_path`;
- `allocation_sha256`;
- `report_path`;
- `report_schema`;
- `report_sha256`;
- `evidence_paths`;
- `notes`.

## Helper Functions

`src/kg_pipeline/registry/candidate_registry.py` provides pure metadata helpers:

- `load_registry(path)`;
- `validate_registry_schema(registry)`;
- `candidate_by_id(registry, candidate_id)`;
- `graph_candidates(registry)`;
- `evidence_only_entries(registry)`;
- `required_artifact_paths(registry)`;
- `validate_candidate_paths_exist(registry)`;
- `validate_candidate_hashes(registry)`;
- `summarize_registry(registry)`.

These helpers do not generate graphs and do not evaluate graph metrics unless a caller separately invokes the reusable evaluator.

## Validation Behavior

`scripts/reconstruction/check_candidate_registry.py` verifies:

- registry schema validity;
- canonical allocation hash;
- graph/report/allocation hashes for existing graph candidates;
- B0 exists with role `selected_baseline`;
- `C3_probe_v1` exists and is not a graph candidate;
- standard evaluator report compatibility for B0, C1, and C2 using the reusable evaluator foundation.

The strict balance-pruned ablation is present in the registry but is skipped for standard evaluator comparison because its report schema is `pruner_final_snapshot`, not `standard_evaluator`.

Latest observed validation summary:

```text
Candidate registry check passed.
summary: candidates=5, graph_candidates=4, evidence_only=1
hashes_checked=15
comparison_status:
- B0: matched
- C1: matched
- C2: matched
- strict_balance_pruned_ablation: skipped_schema pruner_final_snapshot
evidence_only_entries:
- C3_probe_v1: full_bridge_rescue_not_recommended_with_eligible_pool_v1
```

## Relationship To `graph_candidates.tsv`

This registry does not replace `docs/reconstruction/graph_candidates.tsv` yet.

`graph_candidates.tsv` remains the historical reconstruction registry used by the thesis documentation. The JSON registry is a reusable foundation for future candidate orchestration and validation. A later migration can either:

- generate TSV rows from the JSON registry;
- keep the TSV as a human-readable historical table;
- or maintain both with a synchronization check.

No existing TSV row is modified by this phase.

## Relationship To Compatibility Checks

`docs/reconstruction/49_candidate_evaluation_compatibility.md` and `scripts/reconstruction/check_candidate_evaluation_compatibility.py` establish that the reusable evaluator matches B0, C1, and C2 historical standard evaluator reports.

The registry check reuses the same principle but drives candidate selection from `candidate_registry.v1.json` instead of a hardcoded candidate list. This is the intended direction for future graph-candidate checks.

## Future Candidate Additions

Future graph candidates should add one row with:

- a stable `candidate_id`;
- parent candidate ID;
- graph path and SHA256;
- allocation path and SHA256;
- report path and SHA256;
- report schema;
- status and decision;
- evidence paths.

Probe-only evidence should use `is_graph_candidate: false` and must not provide a graph path. A probe-only row must not be treated as a candidate graph or as a replacement for a standard evaluator report.

## Boundary

This phase does not:

- replace the existing TSV registry;
- replace the historical standalone evaluator;
- modify graph/data artifacts;
- run graph generation or pruning;
- query WDQS;
- call LLMs;
- claim that C3 exists as a graph candidate.

