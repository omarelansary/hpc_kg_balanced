# C5-H2 Diversity Reranking Probe

## Purpose

C5-H2 showed that observed unallocated auxiliary edges can preserve full weak connectivity while removing surplus canonical bridge edges, but the cap sweep exposed heavy concentration in relation `P17`. This probe tests whether deterministic diversity-aware reranking can reduce that concentration without using WDQS, LLMs, synthetic triples, or registry updates.

The probe is limited to the existing C5-H2 observed auxiliary candidate space. Per-strategy graphs under `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/diversity_probe/` are probe artifacts, not registered graph candidates.

## Inputs

- Generator logic: `tools/graph_candidate_generation/c5_generate_h2_auxiliary_connectivity_candidate.py`
- Cap sweep evidence: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/cap_sweep/cap_sweep_report.json`
- H1/H2 probe evidence: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/c5_h1_h2_probe_report.json`
- Score provenance audit: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/c5_candidate_score_provenance_audit.json`
- C5 config and H2 policy templates under `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/`

## Strategies Tested

Caps tested: `25`, `50`, `100`, and `151`.

Strategies tested:

- `baseline_current_ranking`
- `p17_cap_25_percent`
- `p17_cap_40_percent`
- `max_per_aux_relation_10`
- `max_per_aux_relation_20`
- `relation_diversity_penalty_light`
- `relation_diversity_penalty_strong`

All strategies keep the existing C5-H2 hard constraints: full graph weak components must remain `1`, canonical relation coverage must remain `139`, zero allocated relations must remain `0`, duplicate triples must remain `0`, each selected move must reduce canonical surplus, and canonical total deficit must not increase.

## Results

All tested strategy/cap combinations passed the C5-H2 policy constraints. The main effect of reranking is on auxiliary relation concentration.

| Strategy | Cap | Aux edges | Surplus delta | Deficit delta | Canonical WCC | P17 count | P17 share |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `baseline_current_ranking` | 25 | 25 | -25 | 0 | 24 | 14 | 0.560 |
| `baseline_current_ranking` | 50 | 50 | -50 | 0 | 49 | 39 | 0.780 |
| `baseline_current_ranking` | 100 | 100 | -100 | 0 | 99 | 79 | 0.790 |
| `baseline_current_ranking` | 151 | 151 | -151 | 0 | 149 | 89 | 0.589 |
| `p17_cap_25_percent` | 50 | 50 | -50 | 0 | 48 | 12 | 0.240 |
| `p17_cap_40_percent` | 50 | 50 | -50 | 0 | 48 | 20 | 0.400 |
| `max_per_aux_relation_10` | 50 | 50 | -50 | 0 | 48 | 10 | 0.200 |
| `max_per_aux_relation_20` | 50 | 50 | -50 | 0 | 48 | 20 | 0.400 |
| `relation_diversity_penalty_light` | 50 | 50 | -50 | 0 | 49 | 1 | 0.020 |
| `relation_diversity_penalty_strong` | 50 | 50 | -50 | 0 | 49 | 1 | 0.020 |
| `relation_diversity_penalty_light` | 100 | 100 | -100 | 0 | 98 | 13 | 0.130 |
| `relation_diversity_penalty_strong` | 100 | 100 | -100 | 0 | 98 | 13 | 0.130 |
| `relation_diversity_penalty_light` | 151 | 151 | -151 | 0 | 149 | 60 | 0.397 |
| `relation_diversity_penalty_strong` | 151 | 151 | -151 | 0 | 149 | 60 | 0.397 |

The full table is stored in `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/diversity_reranking/diversity_reranking_table.tsv`.

## Best Observed Diversity Strategy

The aggregate probe recommends `relation_diversity_penalty_light` at cap `50`.

Compared with the baseline cap-50 C5-H2 candidate:

- Auxiliary edge count remains `50`.
- Canonical surplus delta remains `-50`.
- Canonical deficit delta remains `0`.
- Full graph weak components remain `1`.
- Canonical-only weak components remain `49`.
- P17 count drops from `39` to `1`.
- P17 share drops from `0.780` to `0.020`.
- Surplus cost of diversity is `0`.

The strong diversity penalty gives the same selected result for the tested cap-50 setting.

## Interpretation

Diversity-aware reranking materially improves the auxiliary relation distribution without reducing the cap-50 surplus benefit. This supports continuing C5-H2 with a diversity-aware generator/evaluation branch if auxiliary unallocated observed edges remain methodologically acceptable.

This does not support a registry update by itself. C5-H2 remains an experimental auxiliary-connectivity branch because the improvement depends on unallocated auxiliary edges, and canonical-only connectivity remains fragmented after removing those auxiliary edges.

## Safe Claims

- C5-H2 diversity reranking can reduce P17 concentration sharply in the observed auxiliary candidate space.
- The cap-50 light/strong diversity penalty result preserves the same canonical surplus improvement as baseline cap-50 while reducing P17 share from `0.780` to `0.020`.
- The probe used frozen local evidence only.
- No WDQS query, LLM call, or synthetic triple generation was used.
- `candidate_registry.v1.json` was not updated.

## Unsafe Claims

- Do not claim C5-H2 is canonical allocation-faithful.
- Do not claim the diversity probe proves scientific optimality.
- Do not claim auxiliary unallocated edges are canonical benchmark triples.
- Do not update the candidate registry without a human decision and standard candidate evaluation/decision package.

## Recommendation

The next implementation branch can generate or preserve a diversity-aware C5-H2 candidate, preferably using `relation_diversity_penalty_light` at cap `50`, for human decision and comparison. Registry update remains deferred.
