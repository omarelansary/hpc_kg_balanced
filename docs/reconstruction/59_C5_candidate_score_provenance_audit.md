# C5.1 Candidate Score Provenance Audit

## Purpose

This audit checks whether the feasible C5-H2 auxiliary candidates can be ranked using older Phase II candidate scores.

C5-H2 is not a graph candidate. It is a probe-only branch that found observed, unallocated auxiliary edges that could preserve connectivity while pruning surplus canonical B0 edges. The key question is whether those auxiliary candidates came from scored historical candidate spaces, and whether the old scores are meaningful for a future C5-H2 generator.

## Inputs

- C5 H1/H2 probe report: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/c5_h1_h2_probe_report.json`
- C4.2 local cut-crossing search: `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/local_cut_crossing_candidate_search.json`
- C5 config: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/config.template.json`
- Stage2 candidate shards: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards/*.jsonl`
- Stage4 core graph evidence: `archive/hetzner_version/runs/prod_refine_20260315_180520/stage04_core_graph/`
- Frozen candidate pools: `artifacts/frozen_candidate_pools/`
- Archived Phase II pipeline: `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py`

## Method

The audit script rebuilds the H2 feasible candidate-cut rows using the same bounded settings recorded by the C5 H1/H2 probe, then maps each candidate back to its source path and JSONL line number where available.

For each row it records:

- source path and line number;
- available score-like fields;
- available provenance fields;
- whether the triple is already in B0;
- whether the triple was selected by Stage4;
- whether the triple comes from previously unselected candidate space.

It also scans broader candidate sources to identify score fields present in local evidence, even if those fields are not present on the specific H2 feasible rows.

## Source Schema Findings

| Source group | Files scanned | Rows scanned | Score fields observed |
| --- | ---: | ---: | --- |
| `stage02_candidate_shards` | 139 | 81,958 | `genericity_score`, `hub_penalty`, `quality_score`, `shortcut_risk` |
| `stage04_core_graph` | 2 | 37,026 | `attachability_score`, `bridge_score`, `component_merge_score`, `first_realization_bonus`, `genericity_penalty`, `hub_penalty`, `noise_penalty`, `relation_need_score`, `score` |
| `frozen_candidate_pools` | 2 | 872,156 | `path_group_score`, `path_group_size`, `score` |

These fields confirm that historical scored candidate spaces exist. They do not establish that the C5-H2 auxiliary rows themselves carry an old Phase II ranking score.

## H2 Candidate Findings

| Check | Result |
| --- | ---: |
| Feasible H2 candidate-cut pairs audited | 546 |
| H2 pairs with old Phase II numeric score fields | 0 |
| H2 pairs without old Phase II numeric score fields | 546 |
| H2 pairs with provenance fields | 546 |
| H2 pairs selected by Stage4 | 0 |
| H2 pairs selected into B0 | 0 |
| H2 pairs from previously unselected candidate space | 546 |

All H2 feasible rows mapped to `frozen_candidate_pools`, specifically the C3 replacement pool evidence. The exact H2 rows expose provenance fields such as:

- `candidate_id`
- `duplicate_provenance_count`
- `endpoint_overlap_with_b0`
- `provenance_type`
- `relation_allocation_status`
- `source_artifact`
- `source_event_type`
- `source_record_index`
- `source_sha256`
- `source_stage`

The H2 rows do not expose Stage2 or Stage4 numeric score fields such as `quality_score`, `genericity_score`, `relation_need_score`, `bridge_score`, or `score`.

## Interpretation

The current H2 feasible auxiliary candidates are observed local evidence, but they are not directly scored by the old Phase II Stage2/Stage4 scoring semantics.

The provenance fields are still useful. `duplicate_provenance_count`, `source_stage`, `provenance_type`, and `source_sha256` can support auditability and secondary ranking signals. They should not be treated as equivalent to historical graph-construction scores.

## Reuse Assessment

Classification: `no_score_for_h2_candidates`

Old Phase II scores should not be reused as the primary C5-H2 ranking criterion. A future C5-H2 generator should define a new ranking function that explicitly accounts for:

- bridge-cut support;
- auxiliary-edge provenance;
- duplicate-provenance strength;
- canonical allocation separation;
- pruning benefit;
- target relation surplus reduction;
- hard constraints after auxiliary-add-then-prune.

## Safe Claims

- Local scored candidate spaces exist in Stage2, Stage4, and frozen candidate pool artifacts.
- The 546 feasible C5-H2 candidate-cut pairs are observed, unallocated auxiliary candidates from frozen local evidence.
- All 546 audited H2 pairs map to previously unselected candidate space and are absent from Stage4/B0.
- The H2 rows carry provenance fields, but no old Phase II numeric ranking scores.
- A future C5-H2 generator should not rank primarily by old Phase II scores.

## Unsafe Claims

- Do not claim the H2 candidates were selected or scored by Stage4.
- Do not claim `duplicate_provenance_count` is a graph-construction score.
- Do not claim old Phase II scoring semantics are confirmed reusable for C5-H2.
- Do not claim a C5 graph candidate exists.

## Outputs

- Script: `tools/graph_candidate_generation/c5_audit_candidate_score_provenance.py`
- JSON report: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/c5_candidate_score_provenance_audit.json`
- Markdown report: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/c5_candidate_score_provenance_audit.md`

## Guardrails

- No WDQS query was made.
- No LLM call was made.
- No graph candidate was generated.
- `candidate_registry.v1.json` was not updated.
