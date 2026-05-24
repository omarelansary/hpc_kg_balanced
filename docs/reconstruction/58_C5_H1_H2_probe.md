# C5 H1/H2 Connectivity-Support Probe

## Purpose

This document records the first C5 probe-only implementation for controlled connectivity-support hypotheses.

C5 is not strict C4. It separates:

- H1: canonical allocated observed cut-crossing replacements,
- H2: auxiliary unallocated observed cut-crossing support followed by pruning tests.

Synthetic pattern-derived triples, live WDQS evidence, and LLM use remain disabled and deferred.

## Files

Probe script:

- `tools/graph_candidate_generation/c5_probe_h1_h2_connectivity_support.py`

Probe outputs:

- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/c5_h1_h2_probe_report.json`
- `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/c5_h1_h2_probe_summary.md`

Inputs:

- C5 config:
  `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/config.template.json`
- B0 graph:
  `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Canonical allocation:
  `src/Pruning graph/bidirectional_allocation_results5k.json`
- C4.2 local cut-crossing search:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/local_cut_crossing_candidate_search.json`
- C4.3 decision audit:
  `docs/reconstruction/56_C4_branch_decision_audit.md`

## Pattern Priority

The probe computed B0 pattern deficits from the reusable evaluator. It did not hardcode a pattern-first policy.

Observed priority order:

| Pattern | Deficit | Surplus |
| --- | ---: | ---: |
| `symmetric` | 1378.9028308028305 | 0.0 |
| `inverse` | 175.78250108152952 | 0.0 |
| `anti_symmetric` | 29.24863345853464 | 0.0 |
| `composition` | 0.0 | 6266.933965342894 |

The largest current deficit is symmetric, but this is a measured result, not a hardcoded assumption.

## Bounded Probe Run

Command:

```bash
python tools/graph_candidate_generation/c5_probe_h1_h2_connectivity_support.py \
  --config experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/config.template.json \
  --max-cuts 200 \
  --max-candidates 1000 \
  --force
```

The probe loaded 200 tested bridge cuts and 655 local cut-crossing candidate-cut pairs from frozen evidence:

- H1 allocated candidate-cut pairs: 109
- H2 unallocated candidate-cut pairs: 546

## H1 Result

H1 tested canonical allocated observed cut-crossing replacements under remove/replace.

Result:

| Measure | Count |
| --- | ---: |
| Candidate-cut pairs tested | 109 |
| Feasible connectivity-preserving H1 moves | 109 |
| Balance-improving H1 moves | 0 |
| Greedy H1 upper-bound count | 0 |
| Greedy H1 surplus delta | 0.0 |
| Greedy H1 deficit delta | 0.0 |

Interpretation: allocated cut-crossing replacements exist and preserve connectivity in the independent probe, but they do not improve balance. A strict H1 graph generator is not justified from this evidence.

## H2 Result

H2 tested observed unallocated cut-crossing candidates as auxiliary connectivity support. The auxiliary edge is added first, then the target surplus bridge edge is pruned. Canonical allocation metrics are computed over canonical allocated triples only, while full graph size accounts for the auxiliary edge separately.

Result:

| Measure | Count |
| --- | ---: |
| Candidate-cut pairs tested | 546 |
| Feasible H2 auxiliary-support moves | 546 |
| Greedy H2 upper-bound count | 151 |
| Greedy H2 surplus delta | -151.0 |
| Greedy H2 deficit delta | 0.0 |

Interpretation: H2 has probe support as an auxiliary-connectivity branch, but it changes the evidence accounting model because it uses observed unallocated triples. It is not a canonical allocated replacement branch.

## Generator Recommendation

The probe recommendation is:

`h2_auxiliary_probe_supports_designing_a_constrained_auxiliary_branch`

Do not implement a strict H1 graph generator from this evidence. An H2 generator may be worth designing only after a human decision approves auxiliary unallocated support as a separate edge class with separate evaluation accounting.

## Guardrails

- No graph was generated.
- `outputs/graph.jsonl` was not written.
- `candidate_registry.v1.json` was not updated.
- No WDQS query was made.
- No LLM call was made.
- No synthetic triples were created.

## Next Decision

The next human decision is whether C5-H2 auxiliary observed unallocated support is an acceptable experimental branch. If yes, the next step should be a generator design document, not immediate graph generation. That design must define auxiliary-edge accounting, report formats, and acceptance thresholds before writing a graph.
