# C5-H2 Auxiliary Support Pre-KGE Status

## Purpose

The C5-H2 branch tests whether observed but unallocated auxiliary support edges can allow removal of surplus canonical bridge triples while keeping the full graph weakly connected. This is an experimental auxiliary-support branch. It is not a final KG claim and does not replace B0.

## Why This Was Tested

B0 is the frozen connected baseline: it covers all 139 allocated relations, is duplicate-free, and is hash-stable. It remains imbalanced, composition/generic-heavy, sparse relative to its entity count, and weak enough in downstream evaluation motivation that an auxiliary-support branch was worth testing before KGE handoff.

## What Was Tested

Three local frozen-evidence checks were performed:

1. Bounded auxiliary saturation over the earlier limited source. This found only 151 possible removals and was insufficient as a meaningful endpoint improvement.
2. Expanded frozen-source saturation over all available surplus bridge targets under local frozen evidence. This identified a policy-passing no-cap strategy with 3,643 removals.
3. Best experimental candidate package generation from the expanded audit result. The package reconstructs the selected strategy, compares it against the expanded audit row, and writes KGE-compatible bare graph JSONL files plus separate provenance-rich sidecars.

No WDQS query, LLM call, SLURM job, or Stage4 graph construction is required for this branch.

## Current Candidate Result

The current expanded candidate package uses strategy `relation_diversity_penalty_light_no_cap`.

| Metric | Value |
| --- | ---: |
| Auxiliary edges selected | 3,643 |
| Canonical edges removed | 3,643 |
| Canonical surplus before | 6,702 |
| Canonical surplus after | 3,059 |
| Canonical surplus delta | -3,643 |
| Canonical deficit before | 2,019 |
| Canonical deficit after | 2,019 |
| Canonical deficit delta | 0 |
| Composition surplus delta | -3,571.229166666667 |
| P31 surplus delta | -3,062 |
| P279 surplus delta | -170 |
| P131 surplus delta | -174 |
| Full graph weak components | 1 |
| Canonical-only weak components | 3,471 |
| Duplicate triples | 0 |
| Allocated relation coverage | 139 |
| P17 auxiliary share | 0.340653307713423 |
| Policy validation | passed |
| Audit strategy comparison | matched |

## Interpretation

Structurally, this is a successful experimental auxiliary-support candidate: the full graph remains connected while thousands of surplus canonical bridge triples are removed without increasing canonical deficit.

It is not a clean canonical-only KG. Removing auxiliary edges leaves the canonical-only graph with 3,471 weak components, so full connectivity depends on observed but unallocated auxiliary support. Auxiliary edges are not canonical allocation triples, and this candidate must not be presented as a final KG or B0 replacement.

The next decision point is downstream KGE evaluation. If the full auxiliary graph improves downstream performance, the branch can be classified as an experimental auxiliary-support success. If it remains poor, it should be classified as structural success but downstream failure. If the canonical-only graph fails while the full graph improves, the gain depends on auxiliary support and must be reported that way.

## Output Locations

- Expanded audit report: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/auxiliary_expanded_saturation/expanded_auxiliary_saturation_report.json`
- Expanded audit summary: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/auxiliary_expanded_saturation/expanded_auxiliary_saturation_summary.md`
- Expanded audit table: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/auxiliary_expanded_saturation/expanded_auxiliary_saturation_table.tsv`
- Candidate package: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/`
- KGE full graph input: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/full_graph.jsonl`
- Optional canonical-only diagnostic graph: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/canonical_only_graph.jsonl`
- Auxiliary edges: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/auxiliary_edges.jsonl`
- Removed canonical edges: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/removed_canonical_edges.jsonl`
- Provenance sidecars: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/*.provenance.jsonl`
- Combined edge provenance: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/edge_provenance.jsonl`
- Candidate manifest: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/candidate_manifest.json`
- Evaluation report: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/evaluation_report.json`

## Reproduction Commands

Compile the active branch scripts:

```bash
PYTHONPYCACHEPREFIX=/tmp/kg_pipeline_pycache PYTHONDONTWRITEBYTECODE=1 python -m py_compile \
  tools/graph_candidate_generation/c5_audit_h2_auxiliary_expanded_saturation.py \
  tools/graph_candidate_generation/c5_generate_h2_auxiliary_expanded_best_candidate.py
```

Dry-run the expanded audit:

```bash
python tools/graph_candidate_generation/c5_audit_h2_auxiliary_expanded_saturation.py --dry-run
```

Regenerate the expanded audit reports:

```bash
python tools/graph_candidate_generation/c5_audit_h2_auxiliary_expanded_saturation.py --force
```

Dry-run the best candidate package and verify the reconstructed metrics match the audit row:

```bash
python tools/graph_candidate_generation/c5_generate_h2_auxiliary_expanded_best_candidate.py --dry-run
```

Regenerate the best candidate package:

```bash
python tools/graph_candidate_generation/c5_generate_h2_auxiliary_expanded_best_candidate.py --force
```

Validate JSON reports:

```bash
python -m json.tool \
  experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/auxiliary_expanded_saturation/expanded_auxiliary_saturation_report.json

python -m json.tool \
  experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/candidate_manifest.json

python -m json.tool \
  experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/evaluation_report.json
```

Run registry and reconstruction checks:

```bash
python scripts/reconstruction/check_candidate_registry.py
python scripts/reconstruction/check_candidate_evaluation_compatibility.py

RECON_AUDIT_MANIFEST_OUT=/tmp/c5_h2_auxiliary_pre_kge_validate_only_manifest.json \
  bash scripts/reconstruction/check_required_artifacts.sh --run-validate-only
```

## What Not To Rerun

Do not query WDQS, call LLMs, submit SLURM jobs, or run Stage4 graph construction for this branch. The C5-H2 auxiliary-support package is derived from frozen local evidence and does not require live collection or historical Phase II construction reruns.

## Next Step

Run KGE with the same protocol on:

1. B0.
2. The full auxiliary graph: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/full_graph.jsonl`.
3. Optionally, the canonical-only diagnostic graph: `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/outputs/auxiliary_expanded_best_candidate/canonical_only_graph.jsonl`.

The post-KGE decision should preserve the distinction between canonical allocation quality and auxiliary-supported connectivity.
