# Final Endpoint And Branch Synthesis

## Corrected Decision

B0 remains the current provisional connected baseline.

B0 is not accepted as a final balanced KG, and it does not solve the allocation-balance objective. It remains useful as a downstream evaluation baseline only if its limitations are reported explicitly.

This corrected framing follows `docs/reconstruction/69_B0_provisional_baseline_status_audit.md`, which classifies B0 as:

`provisional_baseline_not_final_solution`

Do not replace B0 with C5-H2 or H3 under the current evidence. Also do not treat the bounded C4, C5-H2, or H3 audits as global impossibility proofs.

## Why B0 Remains The Current Baseline

B0 is still the best registered connected baseline under the frozen reconstruction evidence:

- connected: `1` weak component;
- allocated relation coverage: `139/139`;
- duplicate-free;
- frozen and audited through the reconstruction wrapper layer;
- supported by the current candidate registry and final graph decision evidence;
- usable as a connected benchmark baseline when limitations are disclosed.

B0 remains in place because no better registered candidate currently supersedes it, not because B0 is optimal. Its allocation imbalance is high, especially composition surplus, and the graph also has a sparsity concern from its high entity count relative to triple count.

Key B0 reference metrics:

| Metric | Value |
| --- | ---: |
| Triples | 24,683 |
| Unique entities | 21,893 |
| Allocated relations covered | 139/139 |
| Weak components | 1 |
| Total surplus | 6,702 |
| Total deficit | 2,019 |
| Composition observed total | 11,267 |

## Branch Decisions

### Balance-First Stress Test

Decision: diagnostic only.

The balance-first stress test shows that deletion can improve allocation balance, but connectivity collapses. The stress-test endpoint has much lower surplus but thousands of weak components, so it is not usable as the connected evaluation baseline.

Reference metrics:

| Metric | Value |
| --- | ---: |
| Triples | 17,683 |
| Allocated relations covered | 139/139 |
| Weak components | 5,623 |
| Total surplus | 105 |
| Total deficit | 2,422 |
| Composition observed total | 4,703 |

This is directly verified for the tested stress endpoint, but it does not prove that no connected balanced graph can exist.

### C4 Strict Bridge-Aware Replacement

Decision: bounded negative/probe evidence.

C4 tested strict allocated replacement for surplus generic bridge edges. The original eligible replacement pool did not cross the tested bridge cuts, and broader frozen local evidence did not contain allocated surplus-improving cut-crossing replacements in the bounded target space.

A strict allocated C4 graph generator is not justified under the current frozen evidence. This does not prove that all replacement methods fail globally.

### C5-H2 Observed Auxiliary Connectivity

Decision: diagnostic auxiliary evidence only.

C5-H2 shows a real mechanism: observed unallocated auxiliary edges can preserve full connectivity while surplus canonical bridge edges are removed. The diversity reranking fixed the cap-50 P17 concentration problem, reducing P17 from `39/50` to `1/50` with no surplus cost.

The endpoint improvement is too small for registry and does not make the graph canonical allocation-faithful:

| Cap | Surplus reduction | Ratio of B0 surplus | Decision |
| ---: | ---: | ---: | --- |
| 50 | 50 | 0.746% | too narrow for endpoint replacement |
| 151 | 151 | 2.253% | mostly increases auxiliary dependence |

C5-H2 remains auxiliary-dependent and not canonical allocation-faithful. The selected cap-50 diversity package may be preserved as experimental evidence, but it should not replace B0 or be registered without a separate artifact-preservation and human decision.

### H3 Synthetic Pattern-Derived Feasibility

Decision: bounded negative feasibility evidence.

H3 tested verified symmetric, inverse, and composition rules over the bounded bridge-cut space. The audit found `0` synthetic pattern-derived bridge alternatives:

| Metric | Value |
| --- | ---: |
| Tested bridge cuts | 200 |
| Verified symmetric rules | 18 |
| Verified inverse oriented rules | 44 |
| Verified composition rules | 13 |
| Synthetic candidates found | 0 |

No H3 graph generation is justified from this bounded frozen audit. This does not prove that all synthetic methods fail globally or that broader source scopes cannot produce candidates.

## Hypotheses Answered

The current branch work answers these bounded hypotheses:

- Strict allocated replacement: not feasible under the tested frozen evidence.
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

The bounded branch audits cannot be generalized into full-space impossibility claims.

## Safe Claims

- B0 is the current frozen connected baseline.
- B0 has unresolved balance and sparsity limitations.
- B0 remains useful as a downstream evaluation baseline only if limitations are reported.
- Later branches provide bounded diagnostic evidence.
- C5-H2 shows observed unallocated auxiliary edges can help locally but does not solve the global endpoint trade-off.
- H3 found no synthetic pattern-derived bridge alternatives in the bounded frozen audit.
- Full end-to-end reproducibility remains incomplete where live WDQS, LLM, or exact dashboard export sessions are missing.

## Unsafe Claims

- B0 is the final balanced KG.
- B0 is optimally balanced.
- B0 solves the KG construction problem.
- Bounded tests prove all alternatives fail globally.
- C5-H2 solves the construction problem.
- H3 validates synthetic triples.
- Auxiliary edges are canonical allocated triples.
- Unobserved synthetic triples are Wikidata facts.
- The registry should be updated for C5-H2 or H3 now.

## Registry Decision

`candidate_registry.v1.json` should remain unchanged.

- B0 remains the current provisional connected baseline.
- The registry remains unchanged because no better registered candidate exists, not because B0 is optimal.
- C5-H2 should not be registered yet.
- H3 should not be registered.
- Probe-only branches remain evidence, not selected graph candidates.

## Artifact Policy

Generated C5-H2 graph artifacts should remain local, external, or Git LFS artifacts unless an explicit artifact-preservation decision is made. Small reports, summaries, manifests, and decision docs may remain in Git. Runtime/probe graph outputs should not be casually committed.

## Recommended Next Direction

Stop endpoint-chasing under the current bounded evidence.

The next major work should be one of:

1. downstream KGE evaluation using B0 as a limited connected baseline;
2. thesis integration describing B0 as provisional, connected, and limited by balance/sparsity issues;
3. future-work design for a multi-objective construction method.

Do not keep generating branches without a new, testable hypothesis.
