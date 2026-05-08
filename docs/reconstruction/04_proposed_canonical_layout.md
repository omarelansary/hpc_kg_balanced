# Proposed Canonical Layout

## Scope

This is a proposed future filesystem layout only. No files have been moved, deleted, renamed, or refactored as part of this reconstruction task.

The goal of the future layout is to separate source code, configs, runs, frozen inputs, reportable artifacts, exploratory work, and legacy scripts while preserving provenance.

## Proposed Structure

```text
docs/
  reconstruction/
  pipeline_reconstruction.md
  reproducibility_notes.md
  phase_mapping.md

src/
  phase1_relation_filtering/
  phase1_pattern_verification/
  phase1_allocation/
  phase2_graph_construction/
  phase2_repair_refinement/
  common/

configs/
  phase1/
  phase2/

scripts/
  run_phase1_...
  run_phase2_...
  audit_...
  slurm/

runs/
  YYYYMMDD_HHMMSS_run_name/
    manifest.json
    command.sh
    config.yaml
    inputs/
    outputs/
    logs/
    reports/

artifacts/
  frozen_inputs/
  final_outputs/
  figures/
  deprecated/

legacy/
  old_scripts/
  abandoned_online_sampling/
  exploratory/
```

## Proposed Destination Categories

| Proposed Destination | Current Examples | Rationale | Required Before Moving |
| --- | --- | --- | --- |
| `docs/reconstruction/` | Current six reconstruction docs | Forensic documentation and open questions | Already created by this task. |
| `src/phase1_relation_filtering/` | `src/archive/hop_discovery.py`; `src/composition_verification/classify_relations_pipeline.py` | Relation universe and LLM relation profile preparation | Confirm exact canonical relation-profile generation. |
| `src/phase1_pattern_verification/` | `src/hop_support_and_sym_anti_verification/hop_support_v2.py`; `hop_support_v3.py`; `src/composition_verification/composition_range_domain_improved.py`; `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py`; `src/inverse_verification_legacy/llm_classification_inv.py` | Hop support, symmetry/anti-symmetry support analysis, inverse, domain/range, composition verification | Resolve inverse shard completeness and v2/v3 canonical status. |
| `src/phase1_allocation/` | `src/kg_building/bidirectional_triple_allocation.py`; allocation/export portions of `src/statistics/hop_pattern_analysis_dashboard.py`; `scripts/export_pattern_group_matrix.py` | Relation-group analysis, eta allocation, support matrix export | Separate dashboard UI from allocation library only after evidence freeze. |
| `src/phase2_graph_construction/` | `src/kg_building/relation_balanced_kg_pipeline.py`; `src/kg_building/config_sampler.py`; `src/kg_building/kg_balanced_connected_sampler*.py`; `src/kg_building/build_connected_graph_from_allocation.py` | Candidate collection and graph construction code | Decide whether `relation_balanced_kg_pipeline.py` is executed, planned, or replacement scaffold. |
| `src/phase2_repair_refinement/` | `src/kg_building/repair_relation_allocated_absence.py`; `src/kg_building/repair_kg_connectivity.py`; `src/Pruning graph/kg_balance_remove_replace.py`; pruning scripts | Repair, path bridging, pruning, refinement, final balance checks | Preserve Stage11/12/13 run outputs before moving scripts. |
| `src/common/` | Shared SPARQL helpers, metadata loading helpers, generic statistics utilities if extracted later | Reduce duplication only after no-loss provenance documentation | Requires code refactor task, not part of this documentation task. |
| `configs/phase1/` | Composition verifier configs if externalized; LLM prompt/model configs; hop support parameters | Make Phase I reruns explicit | Need config extraction from logs/scripts. |
| `configs/phase2/` | `src/kg_building/relation_balanced_kg_pipeline_config.yaml`; Stage13 pruning parameter sets | Make graph construction and pruning reruns explicit | Must update paths in a future refactor. |
| `scripts/slurm/` | Existing `scripts/slurm/*.slurm` | Cluster job launchers | Fix stale paths only after documentation. |
| `scripts/run_phase1_*` | Future wrappers for hop discovery, support, compatibility, composition, allocation | Human-readable reproducible commands | Build from verified command history. |
| `scripts/run_phase2_*` | Future wrappers for construction, repair, Stage11/12/13 | Reproduce graph construction candidates | Requires canonical final path decision. |
| `runs/YYYYMMDD_HHMMSS_run_name/` | Stage11/Stage12/Stage13 generated outputs currently under `src/Pruning graph/`; Trial9/Trial2 outputs under `data/connectedgraph/` | Keep manifest, command, config, inputs, logs, reports, outputs together | First compute hashes and document path translations. |
| `artifacts/frozen_inputs/` | `data/raw/wikidata_ontology.*.json`; selected hop discovery/support/composition JSONL; selected allocation JSON | Immutable thesis inputs after freezing | Choose canonical inputs and record SHA256. |
| `artifacts/final_outputs/` | `largest_component.csv`; Stage12 eta analysis; Stage13 selected pruned graph and summaries | Reported thesis outputs | Human confirmation of final graph required. |
| `artifacts/figures/` | `outputs/visualizations/*`; generated `.html` visualizations; Stage13 charts | Thesis figures and diagnostics | Link each figure to generating script/input. |
| `artifacts/deprecated/` | Older ablation outputs, cancelled shard outputs, superseded online graphs after confirmation | Preserve but de-emphasize superseded artifacts | Must not move until obsolete status is proven. |
| `legacy/old_scripts/` | `src/archive/hop_support_copy.py`; older `kg_balance_pruner*.py` variants after confirmation | Preserve historical scripts without presenting them as canonical | Requires human confirmation and evidence. |
| `legacy/abandoned_online_sampling/` | `src/kg_building/run_phase4_sparql_from_allocation.py`; Trial9/Trial2 online outputs if retained as negative result | Keep abandoned online/frontier attempt separate from final offline narrative | Thesis decision needed: negative result, appendix, or deprecated branch. |
| `legacy/exploratory/` | Smoke files, local visualizations, one-off statistics scripts | Preserve exploratory analysis without polluting pipeline | Needs owner review. |

## Proposed Run Manifest Shape

Every future run folder should contain:

```json
{
  "run_id": "YYYYMMDD_HHMMSS_name",
  "purpose": "short human description",
  "workspace": "absolute path at execution time",
  "git_commit": "commit sha or dirty status snapshot",
  "command": "exact command",
  "config_path": "config file copied into run folder",
  "inputs": [
    {
      "path": "relative or original path",
      "sha256": "hash",
      "role": "input role"
    }
  ],
  "outputs": [
    {
      "path": "relative path",
      "sha256": "hash",
      "role": "output role"
    }
  ],
  "external_services": [
    {
      "name": "WDQS or OpenAI",
      "endpoint_or_model": "endpoint/model",
      "retrieval_started_at": "timestamp",
      "retrieval_finished_at": "timestamp"
    }
  ],
  "random_seeds": {
    "global": null,
    "script_specific": {}
  },
  "logs": [
    "logs/job.out",
    "logs/job.err"
  ],
  "status": "success, failed, cancelled, or partial"
}
```

## Migration Order For A Future Refactor

1. Freeze and hash canonical artifacts before moving anything.
2. Create a path-translation manifest for original absolute paths.
3. Choose canonical Phase I outputs: relation profiles, hop discovery, hop support, composition verification, allocation, and support matrix.
4. Choose canonical graph output: Stage12 largest component, Stage13 pruned graph, or another explicitly selected artifact.
5. Move generated outputs into `runs/` or `artifacts/` with manifests.
6. Only then refactor source paths and runner scripts.

