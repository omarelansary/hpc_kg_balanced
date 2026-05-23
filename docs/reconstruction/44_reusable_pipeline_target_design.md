# Reusable KG Construction Pipeline Target Design

## 1. Overall Goal

The next engineering target is a reusable knowledge-graph construction pipeline that can compare graph candidates along the connectedness-vs-balance frontier.

The frozen reconstruction layer established B0 as the current reference connected realization. The new pipeline should not merely replay B0. It should make candidate construction, repair, refinement, evaluation, and registration controlled enough that new strategies can be tested without losing provenance.

The target system must support two modes:

- **Frozen reconstruction mode:** validates already-preserved historical artifacts and selected B0 evidence without graph generation, WDQS calls, or LLM calls.
- **Experimental construction mode:** creates new graph candidates under explicit configs, manifests, hashes, and candidate registry rules.

These modes must remain separate. Frozen reconstruction evidence protects thesis defensibility; experimental construction explores improved scientific tradeoffs.

## 2. Current Known Endpoints

| Endpoint | Triples | Relation coverage | Weak components | Surplus | Deficit | Composition total | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| Connected realization / B0 | 24,683 | 139/139 | 1 | 6,702 | 2,019 | 11,267 | Usable connected graph, but composition-heavy and surplus-heavy. |
| Balance-first stress test | 17,683 | 139/139 | 5,623 | 105 | 2,422 | 4,703 | Much closer to allocation balance, but graph usability is destroyed by fragmentation. |

This establishes a real frontier rather than a single obvious optimum:

- connectedness-first construction preserves graph usability but overrepresents composition-heavy and generic relations
- balance-first construction improves quota balance but breaks graph connectivity
- deletion-only refinement has already shown limited ability to improve B0 without hitting connectivity constraints

## 3. B0 As Reference Connected Baseline

B0 should now be treated as the **reference connected baseline**, not as a permanent claim of scientific optimality.

Safe statement:

> B0 is the currently selected connected reference endpoint because it has 139/139 relation coverage, a single weak component, zero duplicate triples, and the strongest reconstructed provenance chain among available candidates.

Unsafe statement:

> B0 is the best possible graph, or the optimal solution to the allocation-vs-connectivity objective.

The reusable pipeline should preserve B0 as the baseline row in every comparison table. New candidates must beat or intentionally trade against B0 using documented objective criteria.

## 4. Reusable Pipeline Inputs

Every experimental run should declare inputs explicitly in a config and run manifest.

Required inputs:

- canonical allocation JSON with relation-level eta targets
- support matrix used for relation-genericity and pattern context
- candidate source selection:
  - local frozen candidate shards
  - local frozen replacement pool
  - controlled WDQS collection, marked non-exact-rerunnable unless endpoint/cache state is frozen
- parent graph, if the candidate is a refinement rather than a from-scratch construction
- target relation set, if using targeted deletion or replacement
- random seed, if any sampling or randomized tie-breaking is used
- acceptance thresholds for connectivity, coverage, surplus, deficit, and duplicate handling

Input manifest fields should include:

- path
- SHA256
- size bytes
- source type: `git`, `external_bundle`, `generated_in_run`, `wdqs_live`, `manual_ui_export`
- whether the input is sufficient for exact local rerun

## 5. Reusable Pipeline Stages

### 5.1 Allocation Loading

Load relation-level eta targets from a canonical allocation file. The loader should use the same eta precedence already used by the graph candidate evaluator:

1. `eta_integer`
2. `eta`
3. `eta_expected`

The stage should report:

- allocation file hash
- number of allocation rows
- number of merged positive-eta relations
- total expected eta
- duplicate or conflicting relation rows
- pattern groups if present

### 5.2 Support Matrix Loading

Load the support matrix for relation-genericity and pattern context. This stage should verify compatibility with the allocation relation set.

Checks:

- support matrix hash
- outer relation count
- inner relation count
- nonzero cell count
- missing allocated relations
- relations present in support matrix but absent from allocation

### 5.3 Candidate Source Loading Or WDQS Candidate Collection

The pipeline should support two candidate-source modes.

Local frozen mode:

- reads candidate shards or replacement pools from local artifacts
- verifies hashes
- records source manifest
- supports exact local re-evaluation

WDQS collection mode:

- queries live Wikidata/WDQS
- records query templates, query hashes, endpoint URL, timestamps, retry policy, and result hashes
- must be labelled non-exact-rerunnable unless a full endpoint snapshot or response cache is preserved

The pipeline must not silently mix local frozen candidates and live WDQS candidates in the same run. Mixed runs require an explicit config flag and separate provenance accounting.

### 5.4 Candidate Audit

Candidate audit should run before construction or refinement.

Required checks:

- h/r/t schema validation
- duplicate candidate triples
- candidate counts by relation
- candidate overlap with parent graph
- candidate relation allocation status
- endpoint overlap with parent graph
- candidate source distribution
- WDQS/cache provenance completeness

### 5.5 Graph Construction

Graph construction creates an initial graph candidate from allocation and candidate pools.

The construction stage should be configurable by objective:

- connectedness-first
- balance-first
- hybrid weighted objective
- seed-and-repair
- quota-first with post hoc connectivity repair

It must record:

- selected triples
- rejected candidates and reasons
- relation counts after construction
- connected components after construction
- objective value before repair
- deterministic tie-breaking or random seed

### 5.6 Connectivity Repair

Connectivity repair should be an explicit stage, not hidden inside construction.

Allowed repair families:

- one-hop bridge additions
- bounded two-hop path additions
- candidate-pool-only repair
- WDQS-backed repair, marked live and non-exact-rerunnable unless cached

Repair outputs must include:

- added triples
- source of each added triple
- relation counts before and after
- surplus/deficit impact
- component merges achieved
- failed bridge attempts and reasons

### 5.7 Remove-Replace Refinement

Remove-replace refinement is the most important near-term hybrid strategy.

Target behavior:

1. identify surplus-heavy or generic-dominant triples
2. classify whether a deletion is connectivity-safe or bridge-like
3. find replacement triples from an eligible frozen replacement pool or controlled candidate source
4. add replacement first when needed
5. verify weak connectivity
6. remove the target triple
7. accept only if the net balance objective improves under constraints

The stage must record:

- deletion candidates tested
- accepted deletions
- accepted replacements
- rejected deletions and reasons
- rejected replacements and reasons
- connectivity-critical targets rescued
- quota impact by relation and pattern

### 5.8 Optional Controlled Relation Addition

Controlled relation addition is a future direction, not yet a committed algorithm.

It should be considered only after explicit constraints are designed:

- maximum allowed graph growth
- allowed relation statuses: underfilled or near-target only
- duplicate prevention
- connectivity effect
- entity-introduction policy
- pattern-balance impact
- cap on generic relation additions

Unsafe design choice:

> Add triples simply because they improve connectivity or relation counts.

Safe design target:

> Add relation-constrained triples only when they improve underfilled relation realization or enable a documented remove-replace move without creating new severe surplus.

### 5.9 Candidate Evaluation

Every candidate graph must be evaluated with the same evaluator semantics:

- allocation metrics computed from unique triples
- duplicate triples reported separately
- weak components computed over unique triples
- relation counts compared against canonical allocation

The evaluator should remain independent from graph-generation code.

### 5.10 Candidate Registration

Candidate registration should be required before any graph is described as a formal candidate.

Registration should record:

- candidate ID
- parent candidate ID
- graph path and hash
- allocation path and hash
- generation script and command
- config path and hash
- evaluator report path and hash
- candidate status
- decision
- human rationale

Unregistered outputs should be called exploratory outputs, not final candidates.

## 6. Dashboard Extraction Boundary

`src/statistics/hop_pattern_analysis_dashboard.py` is important because it is not only a Streamlit interface. It also contains operational Phase I logic that currently connects hop-support evidence, composition verification, pattern grouping, allocation, and Phase II exports.

The reusable pipeline should explicitly extract the pure data logic from this dashboard, while leaving manual exploration and historical live-source features behind.

### 6.1 Logic To Extract Into Pure Reusable Modules

The following dashboard responsibilities should become deterministic, testable modules:

- pattern evidence loading from hop-support artifacts
- aggregation of loop, non-loop, and total pair counts
- symmetry confidence computation from self-pair loop support
- anti-symmetry confidence computation from self-pair non-loop support
- inverse confidence computation from forward, reverse, and bidirectional loop evidence over `(r1, r2)` and `(r2, r1)`
- compact composition-verification loading
- sampled composition confidence computation
- relation-level pattern-group construction
- allocation execution through `allocate_for_patterns`
- allocation JSON export
- genericity support matrix export

These extracted modules should accept explicit file paths and threshold configs, return structured objects, and write manifests with input hashes, threshold values, output hashes, and relation counts.

### 6.2 Logic To Keep As UI Or Manual Exploration

The following responsibilities should remain in the Streamlit/manual layer:

- interactive threshold exploration
- visual inspection of relation groups
- manual sanity checks of accepted/rejected relation sets
- ad hoc display tables and plots
- one-off export buttons used for exploration

The manual UI can call the pure modules, but the pure modules should not depend on Streamlit state.

### 6.3 Historical WDQS And Phase 4 Code Boundary

The dashboard also contains Phase 4 connected-realization UI code and a Wikidata SPARQL triple source. That code should not be promoted directly into the reusable construction pipeline.

Reasons:

- live WDQS calls are not exact-rerunnable without response caches or endpoint snapshots
- the Phase 4 connected-realization path was a historical/prototype branch, not the selected B0 construction chain
- mixing dashboard UI state with live graph realization would weaken provenance controls
- new construction experiments need manifest-driven configs, hashes, candidate registration, and standard evaluator reports

If any WDQS-backed logic is reused, it should be wrapped as an explicit experimental candidate-source mode with query hashes, timestamps, endpoint metadata, retry policy, and cached responses where possible.

### 6.4 Golden-Master Validation For Extraction

Extraction should be validated against frozen Phase I inputs and golden-master outputs before any new algorithmic work.

Required checks:

- load the patched v3 hop-support artifact and v3 compact composition-verification artifact used in the reconstruction evidence
- run the extracted pattern grouping with canonical thresholds and Wilson filtering disabled
- reproduce the canonical final 5k pattern relation-set sizes:
  - symmetric = 18
  - anti_symmetric = 66
  - inverse = 44
  - composition = 26
- reproduce the canonical allocation relation universe after duplicate-row merging
- reproduce the exported genericity support matrix relation set
- compare output hashes or stable sorted normalized records where exact JSON formatting differs

Only after these golden-master checks pass should the extracted modules be used as inputs to new graph-construction experiments.

## 7. Reusable Pipeline Outputs

Every run should write to an experiment-specific directory:

```text
experiments/graph_candidates/<candidate_id>_<name>/
  manifest.json
  command.sh
  config.json
  outputs/
    graph.jsonl
  reports/
    generation_report.json
    evaluator.report.json
    evaluator.summary.md
  decision.md
```

The pipeline should also produce:

- run manifest
- input hash manifest
- output hash manifest
- rejected-action logs
- candidate audit report
- final evaluator report
- optional compact decision summary

Historical artifacts should remain in place. New controlled outputs should live under `experiments/graph_candidates/`.

## 8. Candidate Graph Registry Model

The candidate registry should remain a governance tool, not a scratchpad.

Candidate statuses:

- `frozen_baseline`
- `active_candidate_not_final`
- `generated_passed_minimum_thresholds`
- `generated_failed_minimum_thresholds`
- `rejected_as_final_kept_as_exploratory_evidence`
- `feasibility_probe_only`
- `selected_final_graph`
- `not_selected_after_final_decision`

Candidate IDs should be stable:

- `B0`: selected connected reference baseline
- `C1`: Stage13 aggressive candidate
- `C2`: targeted generic deletion candidate
- `C3_probe_v1`: feasibility evidence only, not a graph candidate
- future graph candidates: `C3`, `C4`, ...
- future probes: use `_probe_` suffix and do not add as graph rows unless they produce graph artifacts

## 9. Required Metrics For Every Candidate

Every graph candidate must report:

- total graph rows
- unique triples
- duplicate triple count
- unique entities
- unique relations
- allocated relations observed
- zero allocated relations
- weak component count
- largest weak component ratio
- total surplus
- total deficit
- pattern totals versus target
- per-relation expected/observed/deficit/surplus
- top underfilled relations
- top overfilled relations
- relation count distribution
- target-generic counts for `P31`, `P279`, `P131`
- composition total
- graph density indicators
- parent graph hash
- allocation hash

Refinement candidates must additionally report:

- deletion candidates tested
- accepted deletions
- rejected deletions by reason
- replacement candidates tested
- accepted replacements
- rejected replacements by reason
- connectivity-critical targets tested
- connectivity-critical targets rescued
- net relation-balance effect

## 10. Refactor Boundary

### Can Be Wrapped Now

These are safe near-term wrapper/refactor targets:

- pattern evidence loading from frozen Phase I artifacts
- pattern-group construction
- allocation export
- genericity support matrix export
- config and manifest loading
- artifact hash validation
- graph candidate evaluation
- candidate registry update helpers
- candidate audit helpers
- shell/Python orchestration that calls existing logic without changing scientific behavior
- common h/r/t graph readers and writers
- read-only source/provenance checks

### Must Remain Historical Evidence For Now

Do not rewrite these as production modules until their provenance role is safely archived:

- archived Hetzner Phase II source
- standalone eta-aware Stage7 artifact lineage
- Stage11/Stage12 historical repair artifacts
- Streamlit dashboard export logic
- LLM relation-profile production code
- inverse LLM legacy branch
- old WDQS query scripts tied to historical outputs
- existing graph/data artifacts under historical paths

The first implementation boundary should be a new wrapper/orchestration package around candidate generation and evaluation, not a refactor of historical scripts.

## 11. Future Algorithmic Directions To Test

These directions need feasibility testing before implementation as formal candidate generators.

### Bridge-Aware Remove-Replace

Purpose:

- reduce generic/composition surplus without disconnecting the graph

Required design checks:

- identify bridge-like target triples
- use replacements that preserve weak connectivity
- prefer underfilled or near-target relations
- reject overfilled or unallocated replacement relations
- avoid replacing generic surplus with different surplus

### Controlled Relation Addition

Purpose:

- improve underfilled relations or create replacement opportunities

Required design checks:

- cap added triples
- prevent generic relation growth
- define new-entity policy
- ensure additions are not simply hidden surplus
- evaluate pattern totals after addition

### Hybrid Objective Search

Purpose:

- explore the connectedness-vs-balance frontier systematically

Possible objectives:

- minimize total surplus with deficit cap
- minimize total deficit with surplus cap
- maximize largest-component ratio with quota penalty
- penalize composition overrepresentation
- penalize graph fragmentation

### Candidate-Pool Expansion

Purpose:

- test whether better replacements exist beyond current eligible pool v1

Required provenance:

- local frozen pool if possible
- WDQS collection only under explicit experimental mode
- query hashes and retrieval timestamps
- response caches if exact rerun is desired

## 12. Unsafe Claims To Avoid

Do not claim:

- B0 is scientifically optimal
- B0 solves the connectedness-vs-balance tradeoff
- the balance-first stress-test graph is usable as a connected benchmark graph
- Stage13, C2, or C3 superseded B0
- C3 generated a graph candidate
- controlled relation addition is already validated
- WDQS-backed experimental runs are exactly reproducible without frozen response caches
- the historical pipeline is fully end-to-end reproducible from scratch
- the reusable pipeline exists before it is implemented and tested

Safe current claim:

> The reconstruction phase established B0 as a defensible connected reference baseline and exposed a frontier between connectedness and allocation balance. The next phase should build a reusable, manifest-driven construction and evaluation pipeline for controlled experiments on that frontier.

## 13. Proposed Next Implementation Boundary

The next implementation should create the reusable control layer, not rewrite historical pipeline code.

Recommended first implementation unit:

- pure Phase I extraction modules for pattern evidence loading, pattern-group construction, allocation export, and genericity matrix export
- `configs/graph_candidates/` schema for experimental construction configs
- `tools/graph_candidate_generation/` shared graph IO and manifest helpers
- a candidate audit command that reads allocation, support matrix, parent graph, and candidate source
- registry helper that validates candidate reports before registration
- no WDQS by default
- no graph-generation algorithm changes in the first commit

The first scientific generator after that should be a constrained prototype, likely bridge-aware remove-replace using a frozen candidate pool. It should be accepted only if it produces a registered candidate with standard evaluator reports and a clear improvement against B0/C1/C2 under predeclared metrics.
