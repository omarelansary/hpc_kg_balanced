# C5-H2 Auxiliary Cap Sweep

## Purpose

This audit runs a controlled C5-H2 cap sweep after the cap-50 decision audit classified C5-H2 as `pending_further_cap_sweep`.

C5-H2 is an experimental auxiliary-connectivity branch. It adds observed unallocated auxiliary edges, removes surplus canonical allocated bridge edges, and evaluates canonical allocation balance over canonical edges only.

No WDQS, LLM, or synthetic triples are used.

## Sweep Setup

Script:

`tools/graph_candidate_generation/c5_sweep_h2_auxiliary_caps.py`

Caps tested:

- 10
- 25
- 50
- 100
- 151

Per-cap outputs are written under:

`experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/cap_sweep/cap_<N>/`

The existing root cap-50 outputs are not overwritten.

Aggregate sweep reports:

- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/cap_sweep/cap_sweep_report.json`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/cap_sweep/cap_sweep_summary.md`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/cap_sweep/cap_sweep_table.tsv`

## Results

All tested caps passed the C5-H2 policy.

| Cap | Status | Aux edges | Surplus delta | Deficit delta | Full WCC | Canonical-only WCC | Canonical-only triples | Aux relations | P17 count | P17 share |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | `passed_policy` | 10 | -10.0 | 0.0 | 1 | 9 | 24,673 | 8 | 3 | 0.300 |
| 25 | `passed_policy` | 25 | -25.0 | 0.0 | 1 | 24 | 24,658 | 11 | 14 | 0.560 |
| 50 | `passed_policy` | 50 | -50.0 | 0.0 | 1 | 49 | 24,633 | 11 | 39 | 0.780 |
| 100 | `passed_policy` | 100 | -100.0 | 0.0 | 1 | 99 | 24,583 | 17 | 79 | 0.790 |
| 151 | `passed_policy` | 151 | -151.0 | 0.0 | 1 | 149 | 24,532 | 27 | 89 | 0.589 |

Graph hashes:

| Cap | Graph SHA256 |
| ---: | --- |
| 10 | `70bab2fafdfb6a3c167d86227253e0395798677df665842c9700f340678e9186` |
| 25 | `f835dc6485fc5e3d8037da5d46791956b2cc9e059c6ae2a055ff8bfd23c4c636` |
| 50 | `91f221e96401bf61eb449ca46467742d809d5589554b770fe9455a5de3d53480` |
| 100 | `b3baaf6f2b2a367b1f7b0303b42994b100b648655b5630500d97d88636784e15` |
| 151 | `66dedc8a14b4d4f8b561d81fc6abd6910a2aea45c27b4e9917a3411ce2fe1ae9` |

## Interpretation

The sweep shows a linear exchange: each selected auxiliary edge enables one surplus canonical edge removal. Deficit stays unchanged at every tested cap.

The tradeoff is not free:

- every passing candidate is auxiliary-dependent;
- canonical-only weak components increase with cap;
- auxiliary relations remain unallocated and are not canonical benchmark triples;
- P17 concentration is high for cap 50 and cap 100;
- the improvement remains small relative to B0 surplus.

The cap 151 candidate gives the largest surplus reduction (`-151`) but leaves the canonical-only graph with `149` weak components and adds `151` auxiliary edges. This is diagnostic evidence, not a clean replacement for B0.

The cap 10 candidate has the lowest auxiliary footprint and the lowest P17 share, but its surplus improvement is only `-10`.

## Recommendation

Sweep recommendation: `continue_with_diversity_penalty`

Best low-cost cap: `10`

Best surplus cap: `151`

The sweep does not support a registry update yet. It supports the conclusion that C5-H2 can produce policy-passing experimental auxiliary candidates, but the current ranking is too prone to auxiliary dependency and relation concentration.

Next C5-H2 work, if continued, should test:

- an auxiliary relation diversity penalty;
- an explicit P17 cap;
- a cap-normalized objective;
- a penalty for canonical-only fragmentation;
- an evaluation view that reports auxiliary cost per unit surplus reduction.

## Registry Decision

Do not update `candidate_registry.v1.json` from this sweep alone.

Before registry update, a human decision must select a specific cap and accept the auxiliary-edge methodology for the candidate's intended claim. The selected graph outputs must also be preserved in artifact storage or explicitly committed with a separate decision.

## Artifact Storage

The cap sweep writes graph outputs under `cap_sweep/`. The cap sweep graph directory is about `48M`; aggregate reports are about `24K`.

Recommendation:

- Commit the sweep script, documentation, aggregate report JSON/Markdown/TSV, and per-cap small reports if desired.
- Store per-cap graph JSONL outputs in external artifact storage or Git LFS.
- Do not accidentally commit ignored graph outputs without a deliberate artifact-storage decision.

## Optional Diagnostics

`src/statistics/kg_pattern_stats.py` and `src/statistics/extract_2paths.py` remain optional post-hoc diagnostics.

They should be deferred for now. The cap sweep already answers the immediate decision question: C5-H2 can pass policy, but the current ranking needs diversity/fragmentation penalties before registry consideration. If used later, these scripts should be wrapped with explicit output directories and treated as non-canonical diagnostics, not Phase I evidence.

## Guardrails

- No WDQS query was made.
- No LLM call was made.
- No synthetic triples were created.
- `candidate_registry.v1.json` was not updated.
- C5-H2 remains experimental auxiliary evidence, not a canonical allocation-faithful replacement for B0.
