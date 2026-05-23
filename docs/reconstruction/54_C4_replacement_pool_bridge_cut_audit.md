# C4.1 Replacement Pool Bridge-Cut Audit

## Purpose

This audit explains why the C4 bridge-aware replace/add probe found no feasible replacements for the tested connectivity-critical target-generic edges.

The audit is read-only. It does not generate a graph, does not modify B0, and does not update `candidate_registry.v1.json`.

## Evidence Used

- B0 graph:
  `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- Canonical allocation:
  `src/Pruning graph/bidirectional_allocation_results5k.json`
- C4 config:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/configs/config.template.json`
- C4 probe report:
  `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/probe_report.json`
- Eligible replacement pool:
  `artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/eligible_replacement_candidates.jsonl`

The audit output files are:

- `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/replacement_pool_bridge_cut_audit.json`
- `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/replacement_pool_bridge_cut_audit.md`

## Method

The script `tools/graph_candidate_generation/c4_audit_replacement_pool_against_bridge_cuts.py` loads B0, builds the undirected graph, identifies simple bridge pairs, and applies the same bounded target ordering used by the C4 probe.

It then restricts targets to surplus target-generic relations from the C4 config:

- `P31`
- `P279`
- `P131`

For each tested bridge target, the audit checks every loaded replacement candidate for:

- whether both endpoints are in B0,
- whether the replacement crosses the target bridge cut,
- whether the replacement relation is allocated,
- whether the triple is already a duplicate in B0,
- whether the target remove plus replacement add would reduce total surplus,
- whether the same move would increase total deficit.

The audit records aggregate counts and per-target summaries, but it does not write any candidate graph.

## Bounded Audit Result

The bounded audit used:

```bash
python tools/graph_candidate_generation/c4_audit_replacement_pool_against_bridge_cuts.py \
  --max-target-edges 200 \
  --max-replacement-candidates 1000 \
  --force
```

Observed counts:

| Measure | Count |
| --- | ---: |
| Tested bridge targets | 200 |
| Replacement rows loaded | 990 |
| Replacement rows with both endpoints in B0 | 612 |
| Replacement rows with one endpoint in B0 | 378 |
| Replacement rows with no endpoints in B0 | 0 |
| Unique replacement rows crossing any tested cut | 0 |
| Unique cut-crossing allocated replacement rows | 0 |
| Unique cut-crossing balance-improving replacement rows | 0 |
| Unique cut-crossing duplicate rows | 0 |

Pair-test counts:

| Pair-test check | Count |
| --- | ---: |
| Endpoint inside B0, both endpoints | 122,400 |
| Endpoint inside B0, one endpoint | 75,600 |
| Rejected because endpoint coverage was incomplete | 75,600 |
| Rejected because replacement did not cross the bridge cut | 122,400 |
| Crossed cut | 0 |
| Crossed cut and allocated | 0 |
| Crossed cut and balance-improving | 0 |

## Relation Distribution

The eligible replacement pool is concentrated in a small number of underfilled or near-target non-generic relations. The largest replacement relations in the bounded pool were:

| Relation | Rows |
| --- | ---: |
| `P5277` | 194 |
| `P2959` | 69 |
| `P2500` | 68 |
| `P2499` | 52 |
| `P1445` | 52 |
| `P1753` | 47 |
| `P3403` | 42 |
| `P2935` | 36 |
| `P4329` | 32 |
| `P3032` | 29 |

## Interpretation

The primary failure mode is bridge-cut crossing coverage.

The replacement pool is not empty, and many replacement rows have both endpoints in B0. However, none of the loaded replacement rows crossed any of the 200 tested bridge cuts. Because no candidate reconnects the cut created by removing a target bridge edge, later filters such as allocation status, duplicate rejection, and balance-delta tests never become the decisive blocker.

This means the C4 bounded failure is not primarily a relation mismatch or balance-delta problem. The eligible replacement pool lacks bridge-cut-spanning edges for the tested P31/P279/P131 bridge targets.

## Implication

The C4 result suggests that future bridge-aware replacement work needs a replacement source designed around bridge cuts, not only relation allocation status and endpoint overlap. Useful future evidence would include candidates generated specifically between the two components exposed by removing each target bridge.

This audit remains probe evidence only. It does not support adding a graph-candidate row and does not supersede B0.
