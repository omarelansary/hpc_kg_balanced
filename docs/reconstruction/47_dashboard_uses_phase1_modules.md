# Dashboard Delegation To Phase I Modules

## Summary

`src/statistics/hop_pattern_analysis_dashboard.py` now delegates duplicated pure Phase I logic to the reusable modules under:

`src/kg_pipeline/phase1/`

The dashboard itself remains the Streamlit UI and historical exploration surface. Its layout, widgets, default paths, thresholds, download buttons, Phase 4 realization UI, WDQS/SPARQL code, MongoDB code, and graph-realization code were not redesigned in this change.

## Delegated Logic

The dashboard imports and delegates these functions to `src/kg_pipeline/phase1/pattern_evidence.py`:

- `is_pid`
- `load_pair_counts`
- `prepare_inverse_table`
- `wilson_interval`
- `load_composition_verified_compact`

It delegates these functions to `src/kg_pipeline/phase1/pattern_groups.py`:

- `classify_composition_patterns`
- `_unique_preserve`
- `build_pattern_groups`

It delegates these functions to `src/kg_pipeline/phase1/genericity_matrix.py`:

- `build_square_adjacency_matrix`
- `build_weight_matrix`
- `extract_relation_submatrix`
- `matrix_to_nested_json_dict`

It delegates allocation execution to `src/kg_pipeline/phase1/allocation_export.py`:

- `run_phase3_allocation`

The dashboard retains compatibility wrappers with the original function names. This keeps existing call sites and Streamlit cache decorators stable while moving formula ownership into reusable pure modules.

## Logic Remaining In The Dashboard

The following remain in `hop_pattern_analysis_dashboard.py`:

- Streamlit page layout
- sidebar controls and manual threshold selection
- metrics, captions, tables, heatmaps, and download buttons
- property domain/range display helpers
- allocation diagnostics display
- Phase 4 connected-realization UI
- JSONL/MongoDB/Wikidata SPARQL source selection for Phase 4
- `WikidataSparqlTripleSource`
- MongoDB and live WDQS realization code

Those parts are UI or historical/prototype realization code. They are not promoted into the reusable Phase I modules by this change.

## Validation Run

Validation commands:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m py_compile \
  src/statistics/hop_pattern_analysis_dashboard.py \
  src/kg_pipeline/phase1/pattern_evidence.py \
  src/kg_pipeline/phase1/pattern_groups.py \
  src/kg_pipeline/phase1/genericity_matrix.py \
  src/kg_pipeline/phase1/allocation_export.py \
  scripts/reconstruction/check_phase1_dashboard_extraction.py
```

```bash
python scripts/reconstruction/check_phase1_dashboard_extraction.py
```

```bash
bash scripts/reconstruction/check_required_artifacts.sh --run-validate-only
```

The golden-master check verifies that the extracted modules still reproduce the canonical patched-v3 Phase I relation groups and allocation evidence:

- symmetric = 18
- anti_symmetric = 66
- inverse = 44
- composition = 26
- allocation relation sets match
- allocation rows match
- genericity matrix relation set matches

## Non-Goals

This change does not:

- query WDQS
- call an LLM
- generate a graph
- modify graph/data artifacts
- change dashboard thresholds or defaults
- change allocation math
- refactor Phase II graph construction
- prove the missing exact Streamlit export session

It only makes the dashboard use the reusable pure Phase I modules introduced in Phase I-A.
