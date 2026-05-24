# C5-H2 Candidate Decision Audit

## Status

C5-H2 generated a policy-passing experimental auxiliary-connectivity graph candidate, but it should not be registered yet.

Recommended decision: `pending_further_cap_sweep`

Rationale: the candidate improves canonical surplus by only `50` out of B0's `6,702` total surplus, a reduction of about `0.75%`. It preserves full weak connectivity only by adding `50` observed unallocated auxiliary edges. Without those auxiliary edges, the canonical-only graph has `49` weak components.

## Preservation Check

The C5-H2 generated outputs exist locally. They are not tracked by Git.

| Path | Exists | Git status | Size bytes | SHA256 |
| --- | --- | --- | ---: | --- |
| `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/graph.jsonl` | yes | ignored/untracked | 4,736,392 | `91f221e96401bf61eb449ca46467742d809d5589554b770fe9455a5de3d53480` |
| `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/canonical_edges.jsonl` | yes | ignored/untracked | 4,664,815 | `48a052a33002e0fea80969a4da2d5a552c16960758525a3d09e91a694c879d09` |
| `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_edges.jsonl` | yes | ignored/untracked | 71,577 | `e6d279a69978539b17474451e02692a5643a51a431d31f2930eaf30c34ff9eed` |
| `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/removed_canonical_edges.jsonl` | yes | ignored/untracked | 29,559 | `d6737cdd147dbda67482a8aa148486bfcaee54c8e5868cf3a058eb3838de6b11` |
| `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/report.json` | yes | untracked | 240,193 | `e952515b903f8afbf84c00a8fe09af6b7020275710f6ec09a54646b357f733b9` |
| `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/summary.md` | yes | untracked | 920 | `d88a3c8cb0cfe6cf51df070c14e5bfc5bef13d86bb5ba20d9241a6f7727fd547` |
| `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/relation_quota_report.tsv` | yes | untracked | 3,954 | `8b02b180cb5fd8285e067efe279010d1ce2e3393d0ddb0867ca6a849516e9380` |
| `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/pattern_balance_report.tsv` | yes | untracked | 225 | `4c8a5ae79446355189403c85c0a09890b12c387c55912d265f29d8f7cdcaaf9a` |
| `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/manifest.json` | yes | untracked | 2,746 | `b6003f1f0294cd1f4c68e93224c8ed99c7997fbafdf2d4111ab3c89cd9d6348a` |
| `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/auxiliary_edge_report.tsv` | yes | untracked | 9,206 | `66d0001d24be38389d0045f4f0ac3c1f5bc7875a02ad7ba34930e1ea4690c526` |
| `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/removed_edge_report.tsv` | yes | untracked | 2,423 | `a19822b6ea58fbc43fd1d90a28271600e42ba3a176b4c6c063ee4702b8890a88` |

Total generated output and report size: `9,762,010` bytes.

Recommendation:

- Commit the small reports, decision file, generator script, and design documentation to normal Git.
- Preserve the graph JSONL outputs in the external artifact bundle or Git LFS.
- If no external artifact store is available, the graph outputs are small enough to commit with an explicit human decision and `git add -f`, but they are ignored and should not be added accidentally.

## B0 Versus C5-H2

| Metric | B0 connected baseline | C5-H2 full graph | C5-H2 canonical-only |
| --- | ---: | ---: | ---: |
| Unique triples | 24,683 | 24,683 | 24,633 |
| Unique entities | 21,893 | 21,893 | 21,891 |
| Unique relations | 139 | 150 | 139 |
| Weak components | 1 | 1 | 49 |
| Duplicate triples | 0 | 0 | 0 |
| Allocated relations observed | 139 | not canonical scope | 139 |
| Zero allocated relations | 0 | not canonical scope | 0 |
| Total surplus | 6,702 | not canonical scope | 6,652 |
| Total deficit | 2,019 | not canonical scope | 2,019 |

Pattern integer totals:

| Pattern | B0 | C5-H2 canonical-only | Delta |
| --- | ---: | ---: | ---: |
| anti_symmetric | 4,970 | 4,970 | 0 |
| composition | 11,267 | 11,217 | -50 |
| inverse | 4,824 | 4,824 | 0 |
| symmetric | 3,622 | 3,622 | 0 |

## What C5-H2 Improves

C5-H2 reduces canonical total surplus by `50` without increasing total deficit and without losing canonical relation coverage. The improvement comes entirely from removing `50` surplus canonical P31 bridge edges after adding observed unallocated auxiliary edges that preserve full weak connectivity.

The full graph remains connected with `1` weak component and has no duplicate triples.

## What C5-H2 Makes Worse Or Less Canonical

C5-H2 is less canonical than B0 because it includes `50` observed unallocated auxiliary edges across `11` unallocated relations. These auxiliary edges are not part of the canonical 139-relation allocation.

The canonical-only graph is not connected after the removals. It has `49` weak components. Therefore the candidate's connectedness is highly dependent on auxiliary edges.

C5-H2 also increases full-graph relation count from `139` to `150`, which makes direct comparison to canonical allocation-only graphs more complex.

## Improvement Magnitude

The surplus reduction is real but small:

- Absolute surplus reduction: `50`
- B0 total surplus: `6,702`
- Relative surplus reduction: about `0.75%`

The composition integer total decreases from `11,267` to `11,217`, but composition remains heavily overrepresented relative to the 5k allocation target.

## Auxiliary Dependence

C5-H2 is strongly auxiliary-dependent. With auxiliary edges included, weak component count is `1`. Without auxiliary edges, the canonical-only graph has `49` weak components.

This means C5-H2 should not be described as a canonical connected graph. It is an auxiliary-connected graph candidate that trades canonical purity for a small balance improvement.

## P17-Heavy Distribution

The auxiliary relation distribution is P17-heavy:

| Auxiliary relation | Count |
| --- | ---: |
| `P17` | 39 |
| `P2853` | 2 |
| `P1056` | 1 |
| `P1412` | 1 |
| `P1552` | 1 |
| `P166` | 1 |
| `P21` | 1 |
| `P27` | 1 |
| `P30` | 1 |
| `P360` | 1 |
| `P915` | 1 |

This distribution is not acceptable as a final scientific endpoint without additional review. It may be acceptable for a diagnostic or experimental candidate if relation concentration is reported explicitly and if later sweeps test relation caps or diversity penalties.

## Decision Recommendation

Recommended status: `pending_further_cap_sweep`

C5-H2 should not be registered immediately. It should be preserved as an experimental candidate result and compared across caps before deciding whether to register it as an `experimental_candidate`.

Next comparison should test at least:

- cap 10;
- cap 25;
- cap 50;
- cap 100 if still within policy;
- cap 151 as the probe upper bound.

Each sweep must report canonical surplus/deficit, full connectivity, canonical-only connectivity, auxiliary relation distribution, and relation-concentration risk.

## Requirements Before Registry Update

Before any `candidate_registry.v1.json` update:

1. Preserve C5-H2 graph outputs and reports in Git LFS or external artifact storage, or explicitly commit them with a human decision.
2. Run the standard candidate evaluator and preserve report hashes.
3. Run a cap sweep and write a comparison decision.
4. Decide whether auxiliary unallocated edges are acceptable for the intended benchmark claim.
5. Write a final human decision file.
6. Only then update the candidate registry.

## Optional Diagnostic Scripts

Two source scripts were inspected:

- `src/statistics/kg_pattern_stats.py`
- `src/statistics/extract_2paths.py`

They are suitable for optional post-hoc diagnostics, not canonical Phase I evidence.

`kg_pattern_stats.py` computes simple relation-level symmetry, anti-symmetry, inverse, and composition statistics from a KG CSV and writes multiple CSV/TXT outputs. It could compare B0 and C5-H2 pattern behavior, but it uses its own threshold logic and does not reproduce the Phase I dashboard allocation/export evidence.

`extract_2paths.py` extracts all two-hop paths from a KG CSV and reports simple symmetry/inverse/commutativity-style counts. It could compare B0 and C5-H2 local two-hop profiles, but it writes potentially large output and is not part of the canonical frozen Phase I reconstruction chain.

Recommendation: wrap these later as optional diagnostics only, with explicit output paths under a candidate report directory. Do not use them to replace the existing Phase I evidence or allocation metrics.

## Guardrails

- `candidate_registry.v1.json` was not updated.
- No thesis LaTeX was edited.
- No WDQS query was made.
- No LLM call was made.
- No new graph candidate was generated during this decision audit.
