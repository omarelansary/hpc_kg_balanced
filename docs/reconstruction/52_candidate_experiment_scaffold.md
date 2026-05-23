# Phase II-D Candidate Experiment Scaffold

This phase adds a standard scaffold command for future graph-candidate experiments.

CLI:

`scripts/graph_candidates/init_candidate_experiment.py`

## Purpose

The scaffold creates a planned experiment directory with stable metadata templates. It does not generate a graph, run pruning, run evaluation, or update the candidate registry.

Default experiment root:

`experiments/graph_candidates/`

Candidate directory:

`experiments/graph_candidates/<candidate-id>/`

## Created Layout

The CLI creates:

- `outputs/`
- `reports/`
- `logs/`
- `configs/`
- `manifest.template.json`
- `README.md`

The intended future graph output path is:

`outputs/graph.jsonl`

## CLI Arguments

Required:

- `--candidate-id`
- `--label`
- `--strategy`

Optional:

- `--parent-candidate-id`
- `--out-root`
- `--allocation`
- `--parent-graph`
- `--registry`
- `--force`

Defaults:

- `--out-root experiments/graph_candidates`
- `--allocation "src/Pruning graph/bidirectional_allocation_results5k.json"`
- `--registry artifacts/final_graph/selected_final_graph/rebuild/candidate_registry.v1.json`

## Parent Resolution

If `--parent-graph` is provided, the scaffold records that path and computes its SHA256.

If `--parent-graph` is not provided and `--parent-candidate-id` exists in the registry, the scaffold uses the parent candidate's `graph_path` and computes its SHA256.

If no parent graph can be resolved, `parent_graph_path` and `parent_graph_sha256` are left null and the manifest notes that the parent graph was unresolved.

## Manifest Template

`manifest.template.json` uses schema:

`kg-candidate-experiment-manifest-template-v1`

It records:

- candidate ID;
- label;
- strategy;
- parent candidate ID;
- parent graph path/hash when resolvable;
- allocation path/hash;
- registry path;
- intended outputs;
- `status: planned_not_generated`;
- notes that no graph was generated, evaluation should run after graph creation, and registry updates require a later human decision.

## README Template

The generated `README.md` states that the candidate is `planned_not_generated`, explains where future graph output should be placed, provides an evaluator command using `scripts/graph_candidates/evaluate_candidate.py`, and reminds the user to write `decision.md` before updating the registry.

## Smoke Test

The smoke test creates:

`tmp/candidate_scaffold_smoke/C4_bridge_aware_replace/`

with parent `B0` resolved from the registry.

Expected hashes:

- parent graph SHA256: `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9`
- allocation SHA256: `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

The smoke output is under `tmp/` and is not intended for commit.

## Boundary

This scaffold does not:

- generate graph candidates;
- modify graph/data artifacts;
- query WDQS;
- call LLMs;
- run evaluation;
- update `candidate_registry.v1.json`;
- replace historical experiment directories.

Future candidates should be registered only after a graph exists, standard evaluation reports exist, and a human decision is recorded.
