# B0 Provisional Baseline Status Audit

## Purpose

This audit corrects the endpoint framing after the branch synthesis in
`docs/reconstruction/68_final_endpoint_and_branch_synthesis.md`.

B0 is a frozen, connected, relation-complete graph realization. It is not an
optimally balanced solution to the KG construction problem. The later C4, C5,
and H3 audits provide bounded negative or diagnostic evidence, not global
impossibility proofs for all future construction strategies.

## Corrected Status

| Question | Status | Rationale |
| --- | --- | --- |
| B0 as frozen connected baseline | Supported | B0 is connected, duplicate-free, covers all allocated relations, and has stable hashes. |
| B0 as final balanced solution | Not supported | B0 retains large surplus, composition overrepresentation, and pattern/relation imbalance. |
| B0 as thesis evaluation endpoint under deadline/scope constraints | Acceptable with explicit limitations | B0 can support downstream evaluation if it is described as a limited connected baseline rather than a final construction solution. |

Corrected endpoint status:

`provisional_baseline_not_final_solution`

## What B0 Is

B0 is the current frozen connected reference baseline.

| Metric | Value |
| --- | ---: |
| Triples | 24,683 |
| Unique entities | 21,893 |
| Unique relations | 139 |
| Allocated relations covered | 139/139 |
| Weak components | 1 |
| Largest weak component ratio | 1.0 |
| Duplicate triples | 0 |
| Graph SHA256 | `c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9` |
| Allocation SHA256 | `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb` |

These properties make B0 useful as a connected, auditable benchmark baseline.
They do not make it a final balanced graph.

## Remaining Defects

B0 does not solve the allocation-balance objective.

| Defect | Evidence |
| --- | --- |
| High total surplus | Total surplus is `6,702`. |
| Remaining total deficit | Total deficit is `2,019`. |
| Composition overrepresentation | Composition observed total is `11,266.934` against target `5,000`, with surplus `6,266.934`. |
| Generic relation dominance | `P31` alone has surplus `5,719`; `P279` has surplus `523`; `P131` has surplus `174`. |
| Pattern imbalance | Symmetric has deficit `1,378.903`; inverse has deficit `175.783`; anti-symmetric has deficit `29.249`. |
| Entity/triple sparsity concern | B0 has `21,893` entities for `24,683` triples, about `1.127` triples per entity. |
| Low graph density | Simple undirected density approximation is about `0.000103`. |

The sparsity concern is not a proof that B0 is unusable, but it is a real
endpoint-quality limitation. A connected graph with many entities and few
triples per entity can be fragile for downstream representation learning and
may understate relation-level evidence density.

## What Later Tests Proved

### Balance-First Stress Test

Evidence strength: directly verified for the tested stress endpoint, not
globally exhaustive.

The balance-first stress test showed that aggressive deletion can reduce the
surplus objective, but it destroys graph usability by fragmenting the graph into
thousands of weak components.

| Metric | Value |
| --- | ---: |
| Triples | 17,683 |
| Allocated relations covered | 139/139 |
| Weak components | 5,623 |
| Total surplus | 105 |
| Total deficit | 2,422 |
| Composition observed total | 4,703 |

This proves that balance can be improved by deletion in that tested branch. It
does not prove that no connected balanced alternative exists.

### C4 Strict Bridge-Aware Replacement

Evidence strength: bounded evidence only, not globally exhaustive.

C4 tested strict allocated replacements for surplus generic bridge edges under
the frozen local evidence used by the branch. It did not find useful feasible
balance-improving replacements in the bounded target space.

This supports closing strict C4 under the tested evidence. It does not prove
that all replacement methods fail globally.

### C5-H2 Observed Auxiliary Connectivity

Evidence strength: bounded diagnostic evidence only, not globally exhaustive.

C5-H2 showed that observed unallocated auxiliary edges can preserve full
connectivity while allowing limited removal of surplus canonical bridge edges.
Diversity reranking corrected the P17 concentration issue at cap 50, but the
marginal utility remained weak:

| Cap | Surplus reduction | Ratio of B0 surplus |
| ---: | ---: | ---: |
| 50 | 50 | 0.746% |
| 151 | 151 | 2.253% |

C5-H2 is useful diagnostic evidence for a local mechanism. It is not a
canonical allocation-faithful replacement for B0.

### H3 Synthetic Pattern-Derived Feasibility

Evidence strength: bounded evidence only, not globally exhaustive.

The H3 audit tested verified symmetry, inverse, and composition rules over a
bounded bridge-cut space and found zero synthetic cut-crossing candidates under
that frozen audit.

This argues against generating an H3 graph from the tested evidence. It does
not prove that all synthetic approaches fail, nor that broader source scopes
cannot produce candidates.

## What Later Tests Did Not Prove

The later tests do not prove:

- all replacement methods fail;
- all synthetic methods fail;
- live WDQS has been exhausted;
- no better multi-objective construction method exists;
- capped or bounded tests imply full-space impossibility;
- B0 is the best possible graph under any future candidate source or algorithm.

## Safe Claims

- B0 is the current frozen connected baseline.
- B0 is usable for downstream evaluation only if its limitations are explicitly reported.
- B0 does not solve the balance objective.
- C4, C5-H2, and H3 provide bounded negative or diagnostic evidence, not impossibility proofs.
- Full end-to-end reproducibility remains incomplete where live WDQS, LLM, or exact dashboard export sessions are missing.

## Unsafe Claims

- B0 is optimally balanced.
- B0 solves the KG construction problem.
- All other hypotheses fail globally.
- Capped or bounded tests prove impossibility.
- C5-H2 or H3 exhausts the full candidate space.
- Auxiliary unallocated edges are canonical allocated triples.
- Synthetic pattern-derived triples are Wikidata facts without separate observation or verification.

## Decision Options

### A. Continue With B0 As Evaluation Baseline

Use B0 for downstream evaluation, but frame it as a connected, frozen,
relation-complete baseline with unresolved balance limitations.

### B. Continue Graph Construction Research

Develop new hypotheses beyond strict allocated replacement, observed auxiliary
support, and bounded H3 synthesis. This requires a new construction plan rather
than more endpoint-chasing with the same bounded evidence.

### C. Run Downstream KGE Evaluation On B0

Proceed with B0 as the available connected baseline and make the endpoint
limitations part of the thesis evaluation framing.

### D. Design A New Multi-Objective Construction Method

If final KG quality is still the priority, design a method that jointly
optimizes connectivity, relation coverage, pattern balance, surplus/deficit,
and evidence provenance.

## Recommended Next Action

Do not update `candidate_registry.v1.json` in this correction.

Do not replace B0 now, and do not claim B0 is a final balanced solution.

The next action should be one of:

1. thesis integration with B0 as a limited connected baseline; or
2. a new multi-objective construction plan if final KG quality remains the
   priority.

## Patch Implication

`docs/reconstruction/68_final_endpoint_and_branch_synthesis.md` and
`artifacts/final_graph/selected_final_graph/rebuild/final_endpoint_branch_synthesis.json`
have been patched to avoid reading B0 as a final balanced solution. The safer
framing is:

`B0 remains the frozen connected reference baseline, but it is provisional and
not a final balanced solution.`
