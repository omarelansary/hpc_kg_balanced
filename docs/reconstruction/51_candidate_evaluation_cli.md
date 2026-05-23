# Phase II-C Candidate Evaluation CLI

This phase adds a standard command-line interface for evaluating an existing graph candidate with the reusable evaluator foundation under `src/kg_pipeline/evaluation/`.

CLI:

`scripts/graph_candidates/evaluate_candidate.py`

## Purpose

The CLI gives future graph-candidate experiments a common report writer. It evaluates an existing CSV or JSONL graph against an allocation JSON and writes a consistent report package:

- `report.json`
- `summary.md`
- `relation_quota_report.tsv`
- `pattern_balance_report.tsv`
- `manifest.json`

It does not generate, prune, repair, or modify graph artifacts.

## Inputs

Required arguments:

- `--candidate-id`
- `--graph`
- `--allocation`
- `--out-dir`

Optional arguments:

- `--label`
- `--parent-candidate-id`
- `--registry`
- `--force`
- `--no-write`

If `--registry` is provided, the CLI records a lightweight registry lookup in `report.json`. The registry lookup is metadata only; it does not replace path/hash validation by the dedicated registry check.

## Output Files

`report.json` contains the dictionary returned by:

`src.kg_pipeline.evaluation.candidate_report.evaluate_candidate`

with additional fields:

- `generated_by`
- `candidate_id`
- `label`
- `parent_candidate_id`
- optional `registry_lookup`

`summary.md` provides a compact human-readable summary of:

- triples, entities, and relations;
- connectivity;
- duplicate triples;
- allocation surplus and deficit;
- zero allocated relations;
- pattern-level expected/observed balance;
- caveats.

`relation_quota_report.tsv` has columns:

- `relation`
- `expected`
- `observed`
- `surplus`
- `deficit`
- `status`

`pattern_balance_report.tsv` has columns:

- `pattern`
- `expected`
- `observed`
- `surplus`
- `deficit`

`manifest.json` records:

- schema version;
- candidate ID;
- label;
- parent candidate ID;
- graph path/hash;
- allocation path/hash;
- output paths;
- generator script path;
- notes that no graph was generated, no graph was modified, no WDQS query was made, and no LLM call was made.

## Overwrite Behavior

The CLI refuses to overwrite any output file unless `--force` is provided.

In `--no-write` mode, it computes the evaluation and prints a compact summary but writes no files and does not create the output directory.

## Difference From Historical Evaluator

The historical evaluator remains:

`tools/graph_candidate_evaluation/evaluate_graph_candidate.py`

This new CLI does not replace it yet. The new CLI uses the reusable evaluation modules introduced in Phase II-A and writes a richer standard output package for future experiments. Compatibility with historical B0/C1/C2 evaluator reports is checked separately by:

`scripts/reconstruction/check_candidate_evaluation_compatibility.py`

## Relation To Candidate Registry

The candidate registry foundation is:

`artifacts/final_graph/selected_final_graph/rebuild/candidate_registry.v1.json`

The registry records known graph candidates and probe-only evidence. This CLI can optionally read that registry to include metadata in the report, but candidate registration remains a separate step. Future candidate workflows should:

1. generate or materialize a graph candidate in a controlled experiment directory;
2. evaluate it with this CLI;
3. inspect the report package;
4. then add or update the registry entry only after a decision exists.

Probe-only evidence such as `C3_probe_v1` should not be evaluated with this CLI as a graph candidate because no graph candidate exists.

## Smoke-Test Command

Read-only calculation:

```bash
python scripts/graph_candidates/evaluate_candidate.py \
  --candidate-id B0_smoke \
  --label "B0 smoke evaluation" \
  --graph "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv" \
  --allocation "src/Pruning graph/bidirectional_allocation_results5k.json" \
  --out-dir tmp/evaluate_candidate_cli_smoke/B0 \
  --no-write
```

Temporary report package:

```bash
python scripts/graph_candidates/evaluate_candidate.py \
  --candidate-id B0_smoke \
  --label "B0 smoke evaluation" \
  --graph "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv" \
  --allocation "src/Pruning graph/bidirectional_allocation_results5k.json" \
  --out-dir tmp/evaluate_candidate_cli_smoke/B0 \
  --force
```

The smoke-test output is intentionally under `tmp/` and is not intended for commit.

