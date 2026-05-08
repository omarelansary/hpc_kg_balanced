# Graph Candidate Registry

## Purpose

This registry defines how graph outputs are tracked before any future output is called a new stage or promoted as thesis-final. It is designed to prevent later investigations from becoming ambiguous "Stage14" artifacts without metrics, hashes, and provenance.

Authoritative machine-readable registry:

`docs/reconstruction/graph_candidates.tsv`

Candidate reports:

`docs/reconstruction/graph_candidate_reports/`

Evaluator:

`tools/graph_candidate_evaluation/evaluate_graph_candidate.py`

## Candidate ID Rules

| ID Type | Meaning | Current Use |
| --- | --- | --- |
| `B0` | Frozen baseline graph | Stage12 largest component before Stage13 pruning |
| `C1` | First candidate after baseline | Stage13 `aggressive_but_guarded` pruned graph |
| `C2`, `C3`, `C4`, ... | Future graph candidates | Any later investigation, refinement, pruning, repair, or construction output |

Rules:

1. A future output gets the next `C*` ID when it is evaluated with `tools/graph_candidate_evaluation/evaluate_graph_candidate.py`.
2. A file must not be called "Stage14" only because it is later than Stage13.
3. A new stage name requires a reproducible process description, command or log, input graph hash, allocation hash, evaluator report, and human decision note.
4. A candidate can be exploratory, rejected, active, or promoted, but it must keep its original candidate ID.

## Current Registered Candidates

| Candidate | Label | Graph | Allocation | Status | Decision |
| --- | --- | --- | --- | --- | --- |
| `B0` | Stage12 largest component | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv` | `src/Pruning graph/bidirectional_allocation_results5k.json` | frozen baseline | Baseline for comparisons |
| `C1` | Stage13 aggressive_but_guarded | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl` | `src/Pruning graph/bidirectional_allocation_results5k.json` | active candidate | Strongest current candidate, not final |

## Evaluation Command Pattern

```bash
python tools/graph_candidate_evaluation/evaluate_graph_candidate.py \
  --candidate-id C2 \
  --label 'short human label' \
  --graph path/to/candidate_graph.csv_or_jsonl \
  --allocation 'src/Pruning graph/bidirectional_allocation_results5k.json' \
  --output-report docs/reconstruction/graph_candidate_reports/C2_short_label.report.json
```

The evaluator writes:

- one JSON report at `--output-report`
- one Markdown summary beside the report using the `.summary.md` suffix, unless `--output-summary` is supplied

The evaluator reads graph and allocation files and writes reports only. It must not modify graph or allocation inputs.

## Duplicate-Safe Evaluation Rules

Verified evaluator policy after the duplicate-safety patch:

1. The evaluator parses all graph rows and records `raw_total_rows`.
2. It de-duplicates `(h, r, t)` triples and records `unique_triples`.
3. It records `duplicate_triple_count = raw_total_rows - unique_triples`.
4. It records both `raw_relation_counts` and `unique_relation_counts`.
5. Allocation metrics use `unique_relation_counts`, not raw row counts.
6. Entity counts and weak components are computed from unique triples.

Thesis-safety rule:

If a future candidate has `duplicate_triple_count > 0`, the duplicate count must be reported in the candidate decision note. The eta comparison remains based on unique triples by default, so duplicate rows cannot inflate allocation fulfillment.

## Allocation Extraction Rules

Verified allocation JSON structure for `src/Pruning graph/bidirectional_allocation_results5k.json`:

- top-level keys: `allocations`, `config`, `eta_per_group`, `pattern_groups`, `relations_universe`
- allocation rows contain `pattern`, `relation`, `eta_expected`, and `eta_integer`
- `pattern_groups` maps each pattern family to relation IDs

Evaluator extraction policy:

1. Eta field precedence is `eta_integer`, then `eta`, then `eta_expected`.
2. Allocation relations are unique relations with positive extracted eta.
3. Per-relation expected eta sums all positive allocation rows for that relation.
4. Pattern-level expected eta sums positive allocation rows by pattern.
5. Pattern-level observed counts are apportioned across a relation's positive pattern rows in proportion to row eta, avoiding double-counting multi-pattern relations.

## Promotion Rules

A candidate may be promoted to "recommended final candidate" only if all of the following are true:

1. It has a row in `docs/reconstruction/graph_candidates.tsv`.
2. It has a JSON report and Markdown summary under `docs/reconstruction/graph_candidate_reports/`.
3. Its graph SHA256 and allocation SHA256 are recorded.
4. Its report includes `raw_total_rows`, `unique_triples`, and `duplicate_triple_count`.
5. It uses the same canonical allocation as B0/C1, or the allocation change is explicitly justified.
6. It preserves weak connectivity: `weak_component_count = 1` and `largest_weak_component_ratio = 1.0`.
7. It preserves allocated relation coverage: `allocated_relations_observed = allocation_relation_count` and `zero_allocated_relations = 0`.
8. It has a parent candidate ID and parent graph hash.
9. It has an evidence path to a script, command, log, or manifest.
10. A human decision explicitly says why it supersedes C1.

## Rules For Calling Something A New Stage

A future output may be called a new stage only after these are available:

1. A stable stage objective that differs from Stage13 pruning.
2. A reproducible command, script, or manifest.
3. Input graph path and hash.
4. Allocation path and hash.
5. Output graph path and hash.
6. Evaluation report from the standard evaluator.
7. Duplicate status from the evaluator.
8. Clear status relative to B0 and C1.

Without these, the output should be registered as `C2`, `C3`, `C4`, etc., not as a new stage.
