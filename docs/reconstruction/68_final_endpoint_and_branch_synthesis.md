# Final Endpoint And Branch Synthesis

## Decision

B0 remains the selected graph endpoint.

B0 should be described as the selected connected reference baseline, not as an optimally balanced graph. Do not replace B0 with C5-H2 or H3 under the current evidence.

## Why B0 Remains Selected

B0 is the best defensible endpoint under the frozen reconstruction evidence:

- connected: `1` weak component;
- allocated relation coverage: `139/139`;
- duplicate-free;
- frozen and audited through the reconstruction wrapper layer;
- supported by the current candidate registry and final graph decision evidence;
- usable as a connected benchmark endpoint.

B0's limitation remains important: allocation imbalance is high, especially composition surplus. The endpoint is selected because it is the strongest connected and auditable realization, not because it solves the balance objective.

Key B0 reference metrics:

| Metric | Value |
| --- | ---: |
| Triples | 24,683 |
| Allocated relations covered | 139/139 |
| Weak components | 1 |
| Total surplus | 6,702 |
| Total deficit | 2,019 |
| Composition observed total | 11,267 |

## Branch Decisions

### Balance-First Stress Test

Decision: diagnostic only.

The balance-first stress test shows that deletion can improve allocation balance, but connectivity collapses. The stress-test endpoint has much lower surplus but thousands of weak components, so it is not usable as the final benchmark endpoint.

Reference metrics:

| Metric | Value |
| --- | ---: |
| Triples | 17,683 |
| Allocated relations covered | 139/139 |
| Weak components | 5,623 |
| Total surplus | 105 |
| Total deficit | 2,422 |
| Composition observed total | 4,703 |

### C4 Strict Bridge-Aware Replacement

Decision: negative/probe evidence.

C4 tested strict allocated replacement for surplus generic bridge edges. The original eligible replacement pool did not cross the tested bridge cuts, and broader frozen local evidence did not contain allocated surplus-improving cut-crossing replacements. A strict allocated C4 graph generator is not justified under the current frozen evidence.

### C5-H2 Observed Auxiliary Connectivity

Decision: diagnostic evidence only.

C5-H2 shows a real mechanism: observed unallocated auxiliary edges can preserve full connectivity while surplus canonical bridge edges are removed. The diversity reranking fixed the cap-50 P17 concentration problem, reducing P17 from `39/50` to `1/50` with no surplus cost.

The endpoint improvement is too small for registry:

| Cap | Surplus reduction | Ratio of B0 surplus | Decision |
| ---: | ---: | ---: | --- |
| 50 | 50 | 0.746% | too narrow for endpoint replacement |
| 151 | 151 | 2.253% | mostly increases auxiliary dependence |

C5-H2 remains auxiliary-dependent and not canonical allocation-faithful. The selected cap-50 diversity package may be preserved as experimental evidence, but it should not replace B0 or be registered without a separate artifact-preservation and human decision.

### H3 Synthetic Pattern-Derived Feasibility

Decision: not worth graph generation under the bounded frozen audit.

H3 tested verified symmetric, inverse, and composition rules over the bounded bridge-cut space. The audit found `0` synthetic pattern-derived bridge alternatives:

| Metric | Value |
| --- | ---: |
| Tested bridge cuts | 200 |
| Verified symmetric rules | 18 |
| Verified inverse oriented rules | 44 |
| Verified composition rules | 13 |
| Synthetic candidates found | 0 |

No H3 graph generation is justified from this audit.

## Hypotheses Answered

The current branch work answers these hypotheses:

- Strict allocated replacement: not feasible under current frozen evidence.
- Observed auxiliary connectivity support: feasible locally, but weak at endpoint scale.
- Diversity reranking: solves C5-H2 P17 concentration, but not auxiliary dependence.
- Synthetic pattern-derived feasibility: no candidates found in the bounded frozen audit.

## Hypotheses Still Unresolved

The following remain future work:

- broader H3 source scope or alternate bridge-cut target sets;
- live WDQS exploratory evidence, clearly non-canonical until frozen and audited;
- downstream KGE effects of B0 versus diagnostic variants;
- whether auxiliary edges should ever be included in final benchmark evaluation;
- whether a future multi-objective construction method can jointly optimize connectivity and balance.

## Safe Claims

- B0 is the selected connected reference baseline.
- C5-H2 and H3 are diagnostic branches, not selected endpoints.
- C5-H2 shows observed unallocated auxiliary edges can help locally but does not solve the global endpoint trade-off.
- H3 found no synthetic pattern-derived bridge alternatives in the bounded frozen audit.
- Full end-to-end reproducibility remains incomplete where live WDQS, LLM, or exact dashboard export sessions are missing.

## Unsafe Claims

- B0 is optimally balanced.
- C5-H2 solves the construction problem.
- H3 validates synthetic triples.
- Auxiliary edges are canonical allocated triples.
- Unobserved synthetic triples are Wikidata facts.
- The registry should be updated for C5-H2 or H3 now.

## Registry Decision

`candidate_registry.v1.json` should remain unchanged.

- B0 remains selected.
- C5-H2 should not be registered yet.
- H3 should not be registered.
- Probe-only branches remain evidence, not graph candidates.

## Artifact Policy

Generated C5-H2 graph artifacts should remain local, external, or Git LFS artifacts unless an explicit artifact-preservation decision is made. Small reports, summaries, manifests, and decision docs may remain in Git. Runtime/probe graph outputs should not be casually committed.

## Recommended Next Direction

Stop endpoint-chasing for now.

The next major work should be one of:

1. downstream KGE evaluation using B0;
2. thesis integration describing B0 as the selected connected baseline with known balance limitations;
3. future-work design for a multi-objective construction method.

Do not keep generating branches without a new, testable hypothesis.
