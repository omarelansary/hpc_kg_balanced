# Phase I-A Extraction Implementation

## Summary

Phase I-A adds pure reusable Phase I modules under `src/kg_pipeline/phase1/` and a golden-master validation script:

`scripts/reconstruction/check_phase1_dashboard_extraction.py`

The implementation copies deterministic logic from `src/statistics/hop_pattern_analysis_dashboard.py` without modifying the dashboard. No WDQS queries, LLM calls, graph generation, graph-artifact edits, or thesis LaTeX edits are part of this extraction.

## Created Modules

| Module | Responsibility |
|---|---|
| `src/kg_pipeline/phase1/pattern_evidence.py` | Load hop-support JSONL, aggregate pair counts, compute loop/non-loop confidence, prepare inverse confidence evidence, load compact composition-verification JSONL, compute sampled composition confidence, and provide Wilson interval helper. |
| `src/kg_pipeline/phase1/pattern_groups.py` | Apply dashboard-equivalent filters for symmetric, anti-symmetric, inverse, and composition candidates; classify accepted composition rows; build relation-level pattern groups. |
| `src/kg_pipeline/phase1/genericity_matrix.py` | Build support adjacency matrices, transform weight matrices, extract relation submatrices, and serialize nested JSON compatible with the existing genericity support matrix export. |
| `src/kg_pipeline/phase1/allocation_export.py` | Call the existing bidirectional allocation function, convert allocation results into stable export rows, build allocation payloads, derive positive-eta relations, and normalize allocation rows for comparison. |

Package markers were added:

- `src/kg_pipeline/__init__.py`
- `src/kg_pipeline/phase1/__init__.py`

## Dashboard Logic Extracted

The extracted logic includes:

- property-ID validation
- hop-support pair-count loading and aggregation
- `conf_loop = loop / total`
- `conf_nonloop = nonloop / total`
- symmetric filtering from self-pair loop confidence
- anti-symmetric filtering from self-pair non-loop confidence
- inverse filtering using bidirectional loop confidence over forward and reverse rows
- compact composition-verification loading
- sampled composition confidence from shortcut counts over examined chain pairs
- optional Wilson interval computation
- relation-level pattern group construction
- support/genericity matrix construction and export serialization
- bidirectional allocation execution through the existing allocation function
- allocation row normalization for golden-master comparison

The allocation math was not rewritten. `allocation_export.py` calls:

`src.kg_building.bidirectional_triple_allocation.allocate_for_patterns`

## What Remains In The Dashboard

The following remain in `src/statistics/hop_pattern_analysis_dashboard.py`:

- Streamlit UI layout
- sidebar widgets and manual threshold exploration
- display tables, charts, metrics, and download buttons
- Phase 4 connected-realization UI
- `WikidataSparqlTripleSource`
- MongoDB realization controls
- JSONL/MongoDB/SPARQL graph-realization source selection
- prototype connected-realization execution

Those parts are UI, historical prototype, or live-source code and are not promoted into the pure reusable Phase I modules in this implementation.

## Golden-Master Check

The validation script is:

`scripts/reconstruction/check_phase1_dashboard_extraction.py`

It uses frozen local artifacts only:

- `data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl`
- `data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl`
- `src/Pruning graph/bidirectional_allocation_results5k.json`
- `archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json`

The check verifies:

- patched v3 inputs reproduce the canonical pattern group counts with Wilson disabled:
  - symmetric = 18
  - anti_symmetric = 66
  - inverse = 44
  - composition = 26
- reproduced pattern relation sets match the canonical allocation
- reproduced allocation rows match the canonical allocation by normalized `(pattern, relation)` rows and eta values
- reproduced genericity matrix relation set matches the archived support matrix relation set

The check exits nonzero on missing inputs, relation-set mismatches, allocation mismatches, or genericity-matrix relation-set mismatches.

## What The Check Does Not Verify

The golden-master check does not verify:

- the missing exact Streamlit dashboard export session
- raw LLM prompt/model/response provenance
- live WDQS rerun behavior
- Phase II graph construction
- B0 graph generation
- byte-identical JSON formatting

The comparison is semantic and normalized where row ordering or formatting is not scientifically meaningful.

## Runtime Boundaries

The extraction does not call:

- WDQS
- OpenAI or any LLM API
- MongoDB
- Streamlit
- graph-generation code

The only non-reconstruction dependency reused for scientific behavior is the existing allocation function.

## Validation Commands

```bash
PYTHONDONTWRITEBYTECODE=1 python -m py_compile \
  src/kg_pipeline/__init__.py \
  src/kg_pipeline/phase1/__init__.py \
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

```bash
git diff --check -- \
  src/kg_pipeline \
  scripts/reconstruction/check_phase1_dashboard_extraction.py \
  docs/reconstruction/46_phase1_extraction_implementation.md
```

## Status

Phase I-A creates a reusable, testable Phase I foundation. The dashboard still owns UI and historical live-source behavior. A later commit can update the dashboard to call the extracted modules after this extraction is reviewed.
