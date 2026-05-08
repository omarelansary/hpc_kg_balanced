# Current Graph Decision State

## Current Baseline

Verified fact:

`B0` is the frozen baseline for candidate comparison:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`

Evidence:

- Registry row: `docs/reconstruction/graph_candidates.tsv`
- Evaluator report: `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`
- Previous decision matrix: `docs/reconstruction/07_final_graph_decision_matrix.md`

B0 evaluator metrics:

| Metric | Value |
| --- | ---: |
| Raw graph rows | 24683 |
| Total triples, unique allocation basis | 24683 |
| Unique triples | 24683 |
| Duplicate triple count | 0 |
| Unique entities | 21893 |
| Unique relations | 139 |
| Weak component count | 1 |
| Largest weak component ratio | 1.0 |
| Allocation relations | 139 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total expected eta | 20000 |
| Observed allocated triples | 24683 |
| Total deficit | 2019 |
| Total surplus | 6702 |

## Current Strongest Candidate

Inference requiring human confirmation:

`C1` is the current strongest candidate if the thesis accepts Stage13 pruning as part of the reported candidate-selection process:

`src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl`

Evidence:

- Registry row: `docs/reconstruction/graph_candidates.tsv`
- Evaluator report: `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`
- Direct Stage13 log: `logs/stage13_prune_revised_29012090.out`
- Stage13 branch summary: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/summary.csv`

C1 evaluator metrics:

| Metric | Value |
| --- | ---: |
| Raw graph rows | 24223 |
| Total triples, unique allocation basis | 24223 |
| Unique triples | 24223 |
| Duplicate triple count | 0 |
| Unique entities | 21893 |
| Unique relations | 139 |
| Weak component count | 1 |
| Largest weak component ratio | 1.0 |
| Allocation relations | 139 |
| Allocated relations observed | 139 |
| Zero allocated relations | 0 |
| Total expected eta | 20000 |
| Observed allocated triples | 24223 |
| Total deficit | 2359 |
| Total surplus | 6582 |

Human decision:

C1 is not final until explicitly promoted by the thesis author.

## What Stage13 Improves

Verified facts from evaluator reports:

| Metric | B0 | C1 | Change |
| --- | ---: | ---: | ---: |
| Raw graph rows | 24683 | 24223 | -460 |
| Unique triples, allocation basis | 24683 | 24223 | -460 |
| Total surplus | 6702 | 6582 | -120 |

Verified facts from Stage13 pruning report:

- C1 keeps `weak_component_count = 1`.
- C1 keeps `largest_component_ratio = 1.0`.
- C1 removes 460 triples.
- C1 completed 10 pruning rounds.
- C1 reports no guard triggered.

Evidence:

- `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`
- `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`
- `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.report.json`

## What Stage13 Worsens

Verified facts from evaluator reports:

| Metric | B0 | C1 | Change |
| --- | ---: | ---: | ---: |
| Total deficit | 2019 | 2359 | +340 |
| Observed allocated triples | 24683 | 24223 | -460 |
| Anti-symmetric apportioned observed count | 4970.751366541465 | 4686.711586529056 | -284.039780012409 |
| Inverse apportioned observed count | 4824.2174989184705 | 4770.980493216595 | -53.237005701875 |

Verified facts from previous decision docs:

- C1 has fewer fully fulfilled relations than B0 in the prior eta-analysis summaries: B0 has 41 and C1 has 23.
- C1 has fewer exactly fulfilled relations than B0 in the prior eta-analysis summaries: B0 has 17 and C1 has 8.

Evidence:

- `docs/reconstruction/07_final_graph_decision_matrix.md`
- `docs/reconstruction/graph_candidate_reports/B0_stage12_largest_component.report.json`
- `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json`

## Metric Mismatch Note

The new evaluator agrees with the previous decision docs on relation-level totals:

- triples
- duplicate count: both B0 and C1 have `duplicate_triple_count = 0`
- unique relations
- weak connectivity
- total expected eta
- observed allocated triples
- total deficit
- total surplus
- zero allocated relations

Pattern-level values differ slightly from earlier rounded summaries because the evaluator keeps fractional eta-weighted apportionment for multi-pattern relations. Earlier Stage12/Stage13 eta summaries show rounded integer pattern buckets. This is a reporting-method difference, not a graph-content difference.

Duplicate-handling conclusion:

The duplicate-safe evaluator did not change B0 or C1 relation-level eta metrics because neither graph contains duplicate triples. B0 has `raw_total_rows = unique_triples = 24683`; C1 has `raw_total_rows = unique_triples = 24223`.

Evidence:

- New reports: `docs/reconstruction/graph_candidate_reports/*.report.json`
- Existing matrix: `docs/reconstruction/07_final_graph_decision_matrix.md`

## What Cannot Be Claimed Yet

Unsafe claims:

1. Stage13 is the final thesis graph.
2. Offline Phase II execution produced B0 or C1.
3. The final graph is reproducible from frozen inputs.
4. Full inverse verification completed successfully.
5. Stage11/Stage12/Stage13 are native stages of the originally intended Phase II pipeline.

Evidence:

- Claim safety matrix: `docs/reconstruction/08_thesis_claim_safety_matrix.md`
- Phase mapping: `docs/reconstruction/02_phase_mapping.md`
- Open questions: `docs/reconstruction/05_open_questions.md`

## Replacement Criteria For Future C2/C3 Candidates

A future candidate must preserve all of these metrics to remain acceptable:

| Metric | Required Value |
| --- | ---: |
| Allocation SHA256 | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`, unless allocation change is explicitly justified |
| Weak component count | 1 |
| Largest weak component ratio | 1.0 |
| Unique relations | 139 or higher, with no lost allocated relation |
| Duplicate triple count | 0 preferred; if nonzero, duplicates must be reported and eta metrics must still use unique triples |
| Allocation relations observed | 139 |
| Zero allocated relations | 0 |
| Unique entities | Documented; any decrease must be justified |
| Graph SHA256 | Recorded in `graph_candidates.tsv` |
| Parent candidate ID and parent hash | Recorded in `graph_candidates.tsv` |
| Evaluator report | Present under `docs/reconstruction/graph_candidate_reports/` |

A future candidate must improve these exact C1 metrics to replace C1 as strongest candidate:

| Metric | C1 Value | Replacement Target |
| --- | ---: | ---: |
| Total deficit | 2359 | Lower than 2359 |
| Total surplus | 6582 | Lower than 6582 |
| Total triples | 24223 | Explain if higher or lower; lower alone is not sufficient |
| Anti-symmetric apportioned deficit | 313.28841347094385 | Lower than 313.28841347094385 |
| Inverse apportioned deficit | 229.01950678340472 | Lower than 229.01950678340472 |
| Symmetric apportioned deficit | 1378.9028308028305 | Lower than 1378.9028308028305 |
| Composition apportioned surplus | 6144.2107510571805 | Lower than 6144.2107510571805 |

Human decision required:

No future candidate should replace C1 only by improving one scalar metric. Replacement should preserve connectivity and relation coverage while improving the eta-balance profile in a documented way.
