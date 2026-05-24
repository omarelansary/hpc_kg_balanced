# C5-H2 Constrained Auxiliary-Connectivity Generator

## Purpose

This document records the first C5-H2 constrained generator implementation.

C5-H2 is an experimental auxiliary-connectivity branch. It tests whether observed unallocated auxiliary edges can create enough connectivity redundancy to remove surplus canonical B0 bridge edges while preserving hard constraints.

This is different from C4. C4 tested strict allocated-only bridge-aware replacement and was closed as negative/probe evidence under the available frozen candidate pool. C5-H2 explicitly allows observed unallocated auxiliary edges, but only as separately accounted connectivity support.

## Inputs

- C5 config: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/config.template.json`
- C5-H2 policy: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/h2_generator_policy.template.json`
- C5 H1/H2 probe report: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/c5_h1_h2_probe_report.json`
- C5.1 score provenance audit: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/c5_candidate_score_provenance_audit.json`
- C4.2 local cut-crossing search: `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/local_cut_crossing_candidate_search.json`
- Parent graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Canonical allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`

## Implementation

Script:

`tools/graph_candidate_generation/c5_generate_h2_auxiliary_connectivity_candidate.py`

The generator:

1. Loads and validates the C5 config and C5-H2 policy.
2. Requires live sources, WDQS, LLM, and synthetic triples to be disabled.
3. Rebuilds the feasible H2 move list from frozen local evidence using the C5 probe logic.
4. Uses only `canonical_allocated_observed` and `auxiliary_unallocated_observed` edge classes.
5. Ranks moves deterministically by hard feasibility, surplus reduction, cut crossing, provenance strength, source metadata, non-reuse constraints, and stable lexical tie-breakers.
6. Greedily selects up to `--max-auxiliary-edges`.
7. After each selected move, rechecks full graph connectivity, duplicate safety, canonical relation coverage, zero allocated relations, and deficit/surplus constraints.
8. Writes full graph, canonical-only, auxiliary-only, and removed-canonical edge files.
9. Evaluates both full graph and canonical-only graph views.

Old Phase II scores are not primary ranking inputs. C5.1 found no old Phase II numeric score fields on the H2 candidate rows.

## Generated Outputs

- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/graph.jsonl`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/canonical_edges.jsonl`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_edges.jsonl`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/removed_canonical_edges.jsonl`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/report.json`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/summary.md`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/relation_quota_report.tsv`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/pattern_balance_report.tsv`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/manifest.json`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/auxiliary_edge_report.tsv`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/removed_edge_report.tsv`

## Result With Cap 50

The bounded generation run used:

```bash
python tools/graph_candidate_generation/c5_generate_h2_auxiliary_connectivity_candidate.py \
  --config experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/config.template.json \
  --policy experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/h2_generator_policy.template.json \
  --max-auxiliary-edges 50 \
  --force
```

Result:

- Acceptance classification: `c5_h2_candidate_passed_policy`
- Auxiliary edges selected: `50`
- Canonical edges removed: `50`
- Canonical surplus delta: `-50.0`
- Canonical deficit delta: `0.0`
- Full graph weak components: `1`
- Canonical-only weak components: `49`
- Canonical allocated triples: `24,633`
- Auxiliary unallocated observed edges: `50`
- Full graph triples: `24,683`
- Canonical allocated relation coverage: `139`
- Zero allocated relations: `0`
- Duplicate triples: `0`
- Unallocated auxiliary relation count: `11`

Auxiliary relation distribution:

| Relation | Count |
| --- | ---: |
| `P17` | 39 |
| `P2853` | 2 |
| `P1056` | 1 |
| `P1412` | 1 |
| `P1552` | 1 |
| `P166` | 1 |
| `P21` | 1 |
| `P27` | 1 |
| `P30` | 1 |
| `P360` | 1 |
| `P915` | 1 |

## Accounting Caveat

Auxiliary edges are observed in frozen local evidence, but they are unallocated. They are not canonical benchmark triples.

Canonical allocation surplus and deficit must be computed over `canonical_edges.jsonl` only. Full graph connectivity is computed over `graph.jsonl`, which includes auxiliary edges. The canonical-only graph has `49` weak components after the selected bridge-edge removals, so the auxiliary edges are structurally necessary for the generated full graph to remain connected.

## Registry Status

`candidate_registry.v1.json` is not updated by the generator. Registry update requires a human decision after reviewing the generated graph, reports, and candidate status.

## Guardrails

- No WDQS query was made.
- No LLM call was made.
- No synthetic triples were created.
- Historical graph/data artifacts outside the C5 experiment directory were not modified.
