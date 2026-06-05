# C6 Observed Canonical Densification Design

## Research Question

`C6_observed_canonical_densification` asks whether observed triples from
canonical allocated relations can improve B0 density and underfilled pattern
coverage while preserving the hard graph constraints that made B0 usable. The
branch also tests whether additions create enough structural redundancy to make
some surplus composition-heavy B0 triples safely removable afterward.

C6 does not query WDQS, call LLMs, run KGE, or use synthetic triples. It uses
only frozen local evidence already present in the repository/worktree.

## Starting Point

C6 starts from B0, the connected realization:

- graph: `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`
- allocation: `src/Pruning graph/bidirectional_allocation_results5k.json`
- registry evidence: `artifacts/final_graph/selected_final_graph/rebuild/candidate_registry.v1.json`
- branch lock evidence: `docs/reconstruction/77_pre_kge_branch_status_lock.md`

C6 does not start from the balance-first stress test, the C5-H2 full auxiliary
graph, or the C5-H2 canonical-only diagnostic graph. B0 is used because it is
the frozen connected reference, covers `139/139` allocated relations, and is
duplicate-free. It is not treated as an optimally balanced final KG.

## Candidate Evidence

The first C6 implementation uses frozen Stage2 candidate shards:

`archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards/*.jsonl`

These rows are treated as observed local frozen candidate evidence. A candidate
is eligible only if:

- the triple is not already in B0;
- the relation is in the canonical allocated relation set;
- no synthetic, auxiliary, live, WDQS, or LLM evidence is introduced;
- the candidate class is allowed by the generator config.

Candidate classes:

- `internal`: both endpoints already exist in B0;
- `semi_internal`: exactly one endpoint exists in B0;
- `external`: neither endpoint exists in B0.

The default sweep runs `internal_only` so density and redundancy can improve
without adding new entities.

## Hard Constraints

Every generated C6 graph must preserve:

- weak component count `1`;
- allocated relation coverage `139/139`;
- duplicate triple count `0`;
- canonical allocated evidence only;
- no graph/data artifact modification outside the C6 run directory.

The scripts write only under:

`experiments/graph_candidates/C6_observed_canonical_densification/runs/{RUN_ID}/`

## Objective Function

The addition score is deterministic:

```text
candidate_score =
  + relation_deficit_weight * normalized_relation_deficit_gain
  + pattern_deficit_weight * normalized_pattern_deficit_gain
  + symmetric_priority_weight * symmetric_underfill_gain
  + entity_reuse_weight * existing_endpoint_score
  + local_density_weight * local_common_neighbors_score
  + redundancy_weight * alternative_path_or_wedge_score
  - composition_penalty_weight * composition_overfill_penalty
  - generic_relation_penalty_weight * generic_relation_penalty_if_available
  - new_entity_penalty_weight * introduced_new_entities_count
```

The default tie-breaker is:

1. higher score;
2. fewer introduced entities;
3. larger relation deficit;
4. lexical `(r, h, t)`.

This prioritizes underfilled relation and pattern coverage, gives extra weight
to symmetric underfill, reuses existing entities, and penalizes composition
additions when composition is already over target.

## Stages

### C6.0 Candidate Census

`scripts/graph_candidates/c6_candidate_census.py`

Inputs:

- B0 graph;
- canonical allocation;
- frozen Stage2 candidate shards.

Outputs:

- `c6_candidate_census.csv`;
- `c6_candidate_census_summary.json`.

The census classifies candidates, computes relation/pattern deficits, flags
composition and symmetric memberships, records endpoint reuse, local common
neighbors, duplicate status, source path, line number, and deterministic score
components.

### C6.1 Controlled Addition

`scripts/graph_candidates/c6_controlled_addition.py`

Default config:

```json
{
  "mode": "internal_only",
  "max_additions": 2000,
  "allowed_candidate_classes": ["internal"],
  "require_allocated_relation": true,
  "allow_auxiliary": false,
  "allow_synthetic": false,
  "preserve_connected": true,
  "preserve_relation_coverage": true,
  "composition_addition_policy": "penalize_or_forbid_if_overfilled",
  "new_entity_budget": 0,
  "random_seed": 0
}
```

Outputs:

- `c6_added_graph.jsonl`;
- `c6_added_graph.csv`;
- `c6_additions.csv`;
- `c6_addition_report.json`.

The report records before/after metrics, accepted additions, rejection reasons,
additions by relation and pattern, composition surplus/share, symmetric deficit,
density, bridge count, and the claim boundary:

`Addition-only can improve underfilled patterns and density, but does not directly remove existing composition surplus.`

### C6.2 Semi-Internal Optional Mode

The optional `internal_then_semi_internal` mode permits semi-internal candidates
after internal candidates and uses a new-entity budget. This mode is not the
default sweep because it changes the sparsity trade-off by admitting new
entities.

### C6.3 Redundancy Audit

`scripts/graph_candidates/c6_redundancy_audit.py`

Inputs:

- B0 graph;
- C6 added graph;
- canonical allocation.

Outputs:

- `c6_redundancy_audit.json`;
- `c6_safe_deletion_candidates.csv`.

The audit checks whether surplus relation or composition-heavy B0 triples become
safe to remove after additions. It records whether the relevant undirected pair
was a bridge before and after additions, whether multiple triples still support
the pair, and whether the deletion is safe after additions but was not safe
before additions.

### C6.4 Add-Then-Safe-Delete

`scripts/graph_candidates/c6_add_then_safe_delete.py`

Inputs:

- C6 added graph;
- safe deletion candidates;
- canonical allocation.

Outputs:

- `c6_add_delete_graph.jsonl`;
- `c6_add_delete_graph.csv`;
- `c6_deletions.csv`;
- `c6_add_delete_report.json`.

The deletion stage greedily removes surplus-reducing candidates and rechecks
connectivity, relation coverage, and duplicate-free status after each accepted
deletion. It stops when no safe candidate remains or the configured deletion cap
is reached.

## Exact Mode and Global Optimality Limitation

The real B0 graph is too large for exhaustive subset search. C6 therefore uses a
deterministic heuristic and candidate-ranked search on the real graph. It must
not claim a global maximum or global optimality.

The shared helper includes an exact small-subset function for toy graphs and
explicitly bounded candidate subsets. Tests cover:

- a simple case where greedy matches exact optimum;
- a constructed counterexample where a score-greedy order is not globally
  optimal for a different coverage objective.

This validates scoring behavior and documents why real-graph C6 results are
heuristic, not exhaustive proofs.

## What C6 Can Claim

C6 can claim:

- observed canonical allocated additions were or were not found from frozen
  local candidate sources;
- addition-only changed density, pattern totals, and relation surplus/deficit by
  the reported amounts;
- add-then-safe-delete preserved or failed hard constraints in the generated
  run;
- results are deterministic for the recorded inputs, hashes, command, and
  config.

## What C6 Cannot Claim

C6 cannot claim:

- global optimality on the real graph;
- all future candidate sources fail or succeed;
- synthetic triples are valid;
- auxiliary unallocated edges are canonical allocated triples;
- live WDQS or LLM evidence was considered;
- B0 is replaced unless a later human decision accepts and preserves the
  generated artifacts.

## Validation Commands

```bash
python -m py_compile \
  scripts/graph_candidates/c6_common.py \
  scripts/graph_candidates/c6_candidate_census.py \
  scripts/graph_candidates/c6_controlled_addition.py \
  scripts/graph_candidates/c6_redundancy_audit.py \
  scripts/graph_candidates/c6_add_then_safe_delete.py

bash -n scripts/graph_candidates/c6_run_sweep.sh

pytest -q tests/graph_candidates

RUN_ID=c6_smoke_$(date -u +%Y%m%dT%H%M%SZ) \
  bash scripts/graph_candidates/c6_run_sweep.sh

python -m json.tool experiments/graph_candidates/C6_observed_canonical_densification/runs/*/*.json
```

## Expected Outputs

Each C6 run directory contains the census, addition, redundancy-audit, and
add-delete artifacts. Generated graph JSONL/CSV files stay under the run
directory and should not be committed as final graph artifacts without a
separate artifact-preservation decision.

