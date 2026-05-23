# Phase I Dashboard Extraction Plan

## Purpose

This document plans the first implementation commit for extracting pure, reusable Phase I logic from:

`src/statistics/hop_pattern_analysis_dashboard.py`

The dashboard currently mixes several concerns:

- pure Phase I evidence loading and pattern computation
- relation-level pattern grouping
- bidirectional allocation execution
- allocation and genericity-matrix export payload construction
- Streamlit rendering and manual threshold exploration
- Phase 4 connected-realization UI
- live WDQS/SPARQL and MongoDB-backed graph realization code

The first extraction commit should separate the pure Phase I allocation/export logic from UI and live-source code without changing behavior.

## 1. Functions And Logic Safe To Extract

The following functions are pure or can become pure by removing only `@st.cache_data` decorators and Streamlit dependencies. They can be copied into reusable modules with behavior preserved.

| Current dashboard function or block | Proposed target | Why safe to extract |
|---|---|---|
| `is_pid` | `pattern_evidence.py` | Stateless validation helper for Wikidata property IDs. |
| `load_pair_counts` | `pattern_evidence.py` | Reads JSONL, aggregates hop-support counts, computes `conf_loop` and `conf_nonloop`; no UI behavior is required after removing `@st.cache_data`. |
| `prepare_inverse_table` | `pattern_evidence.py` | Builds forward/reverse/bidirectional inverse confidence table from a DataFrame. |
| Inline symmetric candidate filter in `main` | `pattern_groups.py` | Deterministic filter over `r1 == r2`, `total`, and `conf_loop`. |
| Inline anti-symmetric candidate filter in `main` | `pattern_groups.py` | Deterministic filter over `r1 == r2`, `total`, and `conf_nonloop`. |
| Inline inverse candidate filter in `main` | `pattern_groups.py` | Deterministic filter over `two_way_support_min` and `bidirectional_conf_min`. |
| `wilson_interval` | `pattern_evidence.py` | Stateless numerical helper for optional composition filtering. |
| `load_composition_verified_compact` | `pattern_evidence.py` | Reads compact composition-verification JSONL and computes sampled composition confidence. |
| Inline composition filter in `main` | `pattern_groups.py` | Deterministic filter over base support, examined chains, shortcut count, sampled confidence, optional Wilson lower bound, and optional focus relation. |
| `classify_composition_patterns` | `pattern_groups.py` | Pure DataFrame classification of accepted composition triples. |
| `_unique_preserve` | `pattern_groups.py` or small internal helper | Deterministic order-preserving uniqueness helper. |
| `build_pattern_groups` | `pattern_groups.py` | Converts candidate-level pattern evidence into relation-level groups. |
| `build_square_adjacency_matrix` | `genericity_matrix.py` | Builds relation adjacency matrix from filtered pair counts. |
| `build_weight_matrix` | `genericity_matrix.py` | Converts adjacency into supported weighting modes. |
| `extract_relation_submatrix` | `genericity_matrix.py` | Pure matrix slicing by relation set. |
| `matrix_to_nested_json_dict` | `genericity_matrix.py` | Serializes matrix into Stage1-compatible nested JSON shape. |
| `run_phase3_allocation` | `allocation_export.py` | Pure wrapper around `allocate_for_patterns` once dependencies and inputs are explicit. |
| Allocation result row construction currently inside `main` | `allocation_export.py` | Converts allocation results to stable row dictionaries; should be extracted to reproduce allocation JSON. |
| `result_payload` construction currently inside `main` | `allocation_export.py` | Builds exported allocation JSON payload from config, groups, universe, and allocation rows. |
| Genericity matrix export block currently inside `main` | `genericity_matrix.py` and `allocation_export.py` | Builds positive-eta relation set and nested matrix export from the same allocation output. |

Extraction should preserve current names where practical, but new modules should expose explicit parameterized functions rather than reading Streamlit widget state.

## 2. Functions And Blocks That Must Stay In The Dashboard

The following code should remain in `hop_pattern_analysis_dashboard.py` for now.

| Current code | Reason to keep in dashboard |
|---|---|
| `render_dataframe` and `_coerce_table_data` | Streamlit display and Arrow fallback behavior, not reusable pipeline logic. |
| `_fmt_sci` | Display formatting for UI tables; not needed for first golden-master exports. |
| dashboard `main` layout, controls, metrics, captions, heatmaps, tables, and download buttons | Manual exploration and UI state should call extracted functions later, not move into the reusable pipeline. |
| `load_property_domain_range_class_map` and `load_property_domain_range_types_map` | Pure, but not required for first allocation/genericity golden-master extraction; can be moved later with metadata utilities. |
| `_safe_entropy` and allocation diagnostic table logic | Diagnostic display support; not required for first export-reproduction boundary. |
| `_triples_to_jsonl_text` | Phase 4 graph realization export helper, not Phase I allocation/export logic. |
| `WikidataSparqlTripleSource` | Live WDQS/SPARQL source for historical/prototype Phase 4 realization. |
| Imports and use of `LocalTripleSource`, `RealizationConfig`, `TripleSource`, `build_relation_quotas`, `is_connected_undirected`, `load_triples_jsonl_index`, `realize_connected_graph`, and `MongoConfig` | Phase 4 connected-realization UI and historical graph construction branch. |
| MongoDB UI block and `pymongo` import inside `main` | Live/manual graph realization source, not frozen Phase I extraction. |
| Wikidata SPARQL UI block inside `main` | Live source mode; must not be promoted without separate audit and caching policy. |
| Phase 4 connected realization button and execution block | Historical/prototype graph realization UI; not the selected B0 construction chain. |

The dashboard should eventually be refactored to call the extracted modules for Phase I evidence and allocation. That dashboard patch should be a separate commit after golden-master tests pass.

## 3. Proposed New Module Paths

Create these package files:

```text
src/kg_pipeline/__init__.py
src/kg_pipeline/phase1/__init__.py
src/kg_pipeline/phase1/pattern_evidence.py
src/kg_pipeline/phase1/pattern_groups.py
src/kg_pipeline/phase1/genericity_matrix.py
src/kg_pipeline/phase1/allocation_export.py
```

### `pattern_evidence.py`

Responsibilities:

- property-ID validation
- hop-support JSONL loading and aggregation
- inverse confidence table construction
- Wilson interval helper
- compact composition-verification JSONL loading

Initial exported functions:

- `is_pid`
- `load_pair_counts`
- `prepare_inverse_table`
- `wilson_interval`
- `load_composition_verified_compact`

### `pattern_groups.py`

Responsibilities:

- apply canonical pattern filters to evidence DataFrames
- classify accepted composition triples
- build unique relation-level pattern groups

Initial exported functions:

- `filter_pair_universe`
- `select_symmetric_candidates`
- `select_anti_symmetric_candidates`
- `select_inverse_candidates`
- `filter_composition_candidates`
- `classify_composition_patterns`
- `build_pattern_groups`

### `genericity_matrix.py`

Responsibilities:

- build adjacency/support matrix from pair counts
- build supported weight matrices
- extract positive-eta relation submatrix
- serialize matrix for Phase II Stage1 genericity scoring

Initial exported functions:

- `build_square_adjacency_matrix`
- `build_weight_matrix`
- `extract_relation_submatrix`
- `matrix_to_nested_json_dict`

### `allocation_export.py`

Responsibilities:

- call `allocate_for_patterns`
- convert allocation results to stable rows
- build allocation export payload
- derive positive-eta relation set for genericity export

Initial exported functions:

- `run_phase3_allocation`
- `allocation_results_to_rows`
- `build_allocation_payload`
- `positive_eta_relations`

## 4. Golden-Master Checks To Create

The first implementation commit should include tests or a small validation script that proves the extracted modules reproduce the reconstructed dashboard behavior from frozen inputs.

Recommended test path:

```text
tests/phase1/test_dashboard_extraction_golden_master.py
```

If the repository does not yet have a test framework, create a lightweight script instead:

```text
scripts/reconstruction/check_phase1_dashboard_extraction_golden_master.py
```

Preferred first commit: use a test file if `pytest` is already available in the project; otherwise use the reconstruction check script to avoid adding dependency churn.

Golden-master checks:

1. Load patched v3 hop-support evidence.
2. Load v3 compact composition-verification evidence.
3. Apply canonical thresholds recorded in the canonical allocation artifact, with Wilson filtering disabled.
4. Reproduce relation-level pattern group counts:
   - symmetric = 18
   - anti_symmetric = 66
   - inverse = 44
   - composition = 26
5. Compare the sorted relation sets for each pattern against `src/Pruning graph/bidirectional_allocation_results5k.json`.
6. Build the adjacency support matrix over positive-eta relations.
7. Confirm the genericity matrix relation set matches the archived support matrix relation set.
8. Run allocation export with the recorded eta totals and allocation parameters.
9. Compare stable sorted allocation rows against the canonical 5k allocation after duplicate-row merging rules are applied.

The first commit should not require exact byte-for-byte JSON output matching because formatting and row ordering can change. It should compare normalized semantic records:

- pattern name
- relation ID
- eta fields
- pattern group relation sets
- genericity matrix relation keys

## 5. Frozen Inputs For Golden-Master Validation

Use these frozen inputs:

| Role | Path | Evidence status |
|---|---|---|
| Patched v3 hop-support input | `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl` | Reconstructed as the input family most consistent with the canonical 5k allocation. |
| V3 compact composition verification | `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl` | Confirmed compact sampled shortcut-verification output. |
| Canonical 5k allocation | `src/Pruning graph/bidirectional_allocation_results5k.json` | Downstream B0 allocation, SHA256 `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`. |
| Archived genericity support matrix | `archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json` | Stage1 support matrix, SHA256 `75794511aaa9ef72a7c63fd0d9a3c11969b72c4fa4bfb01237859b612f544041`. |

These inputs are not all tracked in normal Git. The golden-master check should print a clear skip or failure message when external evidence artifacts are missing, depending on whether it is run in developer mode or CI mode.

## 6. Exact First Implementation Commit Scope

Edit or create only these files in the first extraction implementation commit:

```text
src/kg_pipeline/__init__.py
src/kg_pipeline/phase1/__init__.py
src/kg_pipeline/phase1/pattern_evidence.py
src/kg_pipeline/phase1/pattern_groups.py
src/kg_pipeline/phase1/genericity_matrix.py
src/kg_pipeline/phase1/allocation_export.py
tests/phase1/test_dashboard_extraction_golden_master.py
```

If tests are not yet appropriate, use this alternative instead of the test file:

```text
scripts/reconstruction/check_phase1_dashboard_extraction_golden_master.py
```

Do not patch `src/statistics/hop_pattern_analysis_dashboard.py` in the first extraction commit. That keeps the first commit low-risk: it adds extracted pure modules and validation, but does not change dashboard behavior.

## 7. Files And Logic Not To Touch

Do not touch these in the first extraction commit:

- `src/statistics/hop_pattern_analysis_dashboard.py`
- `src/kg_building/build_connected_graph_from_allocation.py`
- `src/kg_building/config_sampler.py`
- archived Hetzner source or artifacts
- Stage11/Stage12 graph artifacts
- canonical allocation JSON
- support matrix JSON
- composition/hop-support JSONL artifacts
- Streamlit UI layout
- Phase 4 realization code
- WDQS/SPARQL code
- MongoDB code
- thesis LaTeX

Do not move historical files into the new package. Copy only pure logic into new modules and validate behavior by normalized comparisons.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Hidden behavior change from removing `@st.cache_data` | Extract loaders without caching; compare outputs against dashboard-derived golden-master records. |
| DataFrame dtype or ordering changes | Normalize sorted records before comparison; do not require byte-identical JSON. |
| Allocation row ordering changes | Compare by `(pattern, relation)` keys and eta values. |
| Duplicate relation rows in canonical allocation | Apply the same duplicate-row merging interpretation used in reconstruction docs and evaluator logic. |
| External frozen inputs are large and untracked | Make golden-master checks explicit about required external artifact paths and hashes. |
| Accidentally promoting Phase 4 live graph realization | Do not import or copy `WikidataSparqlTripleSource`, MongoDB realization code, or Phase 4 UI code. |
| Creating a reusable package that cannot import allocation logic | Keep `allocation_export.py` as a thin wrapper around existing `src.kg_building.bidirectional_triple_allocation.allocate_for_patterns`; do not rewrite allocation math in the first commit. |
| Confusing reconstructed inference with exact export provenance | Test relation-set and normalized allocation reproduction; preserve caveat that the original dashboard export session is missing. |

## 9. First Commit Validation Commands

Run these after implementation:

```bash
python -m py_compile \
  src/kg_pipeline/__init__.py \
  src/kg_pipeline/phase1/__init__.py \
  src/kg_pipeline/phase1/pattern_evidence.py \
  src/kg_pipeline/phase1/pattern_groups.py \
  src/kg_pipeline/phase1/genericity_matrix.py \
  src/kg_pipeline/phase1/allocation_export.py
```

If using a reconstruction check script:

```bash
python scripts/reconstruction/check_phase1_dashboard_extraction_golden_master.py
```

If using pytest:

```bash
pytest tests/phase1/test_dashboard_extraction_golden_master.py
```

Also run:

```bash
git diff --check -- src/kg_pipeline tests scripts/reconstruction
```

## 10. Proposed First Commit Summary

Commit message:

`Extract pure Phase I dashboard allocation logic`

Commit purpose:

- add a reusable Phase I package
- copy pure dashboard logic without changing dashboard runtime behavior
- add golden-master validation against frozen patched v3 inputs and canonical allocation evidence
- keep UI, WDQS/SPARQL, MongoDB, and Phase 4 realization code untouched

This commit should create the reusable foundation for later dashboard refactoring and future manifest-driven graph construction experiments.
