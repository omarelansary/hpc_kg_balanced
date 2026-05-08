# Workspace Inventory

## Scope

This inventory describes the copied refactor workspace at:

`/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced_refactor_work`

It is a forensic documentation pass only. Existing code, logs, artifacts, configs, and git metadata were not reorganized or refactored.

## Git And File Counts

Verified facts from the initial read-only pass:

| Item | Observation | Evidence |
| --- | --- | --- |
| Current workspace | `/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced_refactor_work` | `pwd` |
| Tracked files | 107 tracked files before these docs were created | `git ls-files \| wc -l` |
| Untracked non-ignored files | 516 before these docs were created | `git ls-files --others --exclude-standard \| wc -l` |
| Typed artifact count | 22,744 files matched broad source/artifact extensions when `.venv` was included | `find . -type f (...) \| wc -l` |
| Dirty tracked files | `.gitignore`, `data/processed/hop_support.jsonl`, several SLURM scripts | `git status --short` |
| Deleted tracked files | `data/processed/hop_discovery_failed_only.jsonl`, `data/processed/hop_support_failed_rerun.jsonl`, `scripts/run_stage13_branch_sweep.sh` | `git status --short` |
| Large untracked artifact population | Many files under `data/processed/`, `data/archived/`, `data/connectedgraph/`, `logs/`, `outputs/`, `scripts/`, `src/Pruning graph/`, `src/statistics/` | `git status --short`; `find . -maxdepth 4` |

Important caution: `docs/reconstruction/` is newly created by this documentation task and should not be interpreted as pre-existing pipeline evidence.

## Compact Directory Shape

Verified top-level and near-top-level structure:

| Area | Contents Observed | Evidence |
| --- | --- | --- |
| `data/raw/` | Wikidata ontology relation profiles, property metadata, aliases, embeddings, entity types | `find . -maxdepth 4`; `git status --short` |
| `data/processed/` | Hop discovery, hop support, compatibility, composition, inverse, normalized, shard, and visualization artifacts | `git status --short`; artifact file names |
| `data/archived/` | Older or backup hop-support recovery artifacts, archived visualizations, archived SLURM file | `git status --short` |
| `data/connectedgraph/` | Allocation results, online construction trials, repair outputs, hop-support-v3 trial outputs | `find`; pipeline logs |
| `logs/` | SLURM `.out` and `.err` files for discovery, support, composition, inverse, online construction, repairs, and pruning | `find . -type f \( -name "*.out" -o -name "*.err" \)` |
| `outputs/visualizations/` | Generated figure outputs | `git status --short`; `find . -maxdepth 4` |
| `scripts/` | Utility scripts, SLURM runners, job-based shard helpers, pruning runners | `find`; `git status --short` |
| `src/` | Main Python source plus archive, composition, enrichment, inverse, KG building, statistics, and pruning areas | `find . -name "*.py"` |
| `src/Pruning graph/` | Pruning scripts and many generated Stage11/Stage12/Stage13 outputs under a path containing a space | `find`; `git status --short` |
| `.venv/` | Local virtual environment present in the workspace | hidden-file inventory |
| `.env` | Local environment file present; contents were not inspected or copied into documentation | hidden-file inventory |
| `.vscode/`, `.codex/` | Local/editor/tooling folders | hidden-file inventory; `git status --short` |

## Classification Table

| Category | Current Examples | Evidence And Notes | Confidence |
| --- | --- | --- | --- |
| Canonical or currently relevant source code | `src/hop_support_and_sym_anti_verification/hop_support_v2.py`; `src/hop_support_and_sym_anti_verification/hop_support_v3.py`; `src/composition_verification/composition_range_domain_improved.py`; `src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py`; `src/kg_building/run_phase4_sparql_from_allocation.py`; `src/kg_building/repair_relation_allocated_absence.py`; `src/kg_building/repair_kg_connectivity.py` | These files are referenced by runners, logs, comments, or output artifacts. | High for referenced scripts; medium where direct run logs are absent |
| Archive or legacy-looking source | `src/archive/hop_discovery.py`; `src/archive/hop_support_copy.py`; `src/inverse_verification_legacy/*` | `hop_discovery.py` is under `archive` but is confirmed executed by `logs/hop_discovery_json_27530562.out`. `inverse_verification_legacy` has actual scripts and partial log evidence. | Mixed; do not discard without human confirmation |
| Likely entrypoint scripts | Python scripts with `argparse` or `__main__`, including `src/kg_building/relation_balanced_kg_pipeline.py`, `src/kg_building/bidirectional_triple_allocation.py`, `src/Pruning graph/kg_balance_remove_replace.py`, `src/statistics/hop_pattern_analysis_dashboard.py` | Discovered by source search for `argparse`, `if __name__ == "__main__"`, and command references. | Medium to high |
| Pipeline runners | `scripts/slurm/hop_discovery_json.slurm`; `scripts/slurm/hop_support_v2.slurm`; `scripts/slurm/composition_range_domain_improved_min8_jsonl.slurm`; `scripts/slurm/llm_classification_inv.slurm`; `scripts/slurm/stage13_balance_prune_revised_density_aware.slurm`; `scripts/job_based/*` | SLURM logs and runner contents provide command evidence. Some runner paths are stale. | High for logs; medium for runners without matching logs |
| Config files | `requirements.txt`; `src/kg_building/relation_balanced_kg_pipeline_config.yaml`; `.env`; `.vscode/*` | `requirements.txt` has loose ranges. `.env` exists but was not opened. | High |
| Intermediate artifacts | `data/processed/hop_discovery_from_json.jsonl`; `data/processed/hop_support_v2_w_failed_statuses.wikibase_item_only_w_target_enrichment.jsonl`; `data/processed/min8_hop_support_v2_with_compatible_targets_dom_rng_v1.jsonl`; `data/processed/hop_support_v3/*`; `data/processed/shards/*` | Names and logs indicate these feed later steps. | Medium to high |
| Final or reportable candidates | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component_eta_analysis/summary.json`; `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv`; `src/Pruning graph/stage13_branch_sweep_20260423_160635/summary.csv`; `src/Pruning graph/stage13_branch_sweep_20260423_160635/summary.md`; `src/Pruning graph/stage13_branch_sweep_20260423_160635/aggressive_but_guarded/pruned_graph.jsonl` | Later-stage reports and branch sweep logs identify these as strong final/reportable candidates, but final thesis selection still needs human confirmation. | Medium |
| SLURM and job evidence | `logs/hop_discovery_json_27530562.out`; `logs/hop_support_v2_27520503.out`; `logs/composition_min8_jsonl_27683654.out`; `logs/composition_hop_support_v3_min8_jsonl_28197929.out`; `logs/normalized_hop_support_v3_rerun28049486.out`; `logs/trial9_phase4_connectedgraph_sparql_watch_27985436.out`; `logs/repair_rel_alloc_abs_28220089.out`; `logs/stage13_prune_revised_29012090.out` | These are primary execution evidence for actual run reconstruction. | High |
| Visualizations | `data/processed/relation_graph_edges.viz.html`; `data/archived/*.viz.html`; `outputs/visualizations/*`; `src/Pruning graph/**/*.png`; `src/Pruning graph/**/*.html` | Generated artifacts; useful for thesis figures but usually not pipeline inputs. | Medium |
| Obsolete or superseded candidates | Online Phase4 trial outputs under `data/connectedgraph/trial9/` and `data/connectedgraph/hop_support_v3/trial2_checkpoint_postprocess/`; older Stage13 ablation output | Existing comparison note labels Trial2 online as abandoned and later Stage12/Stage13 outputs as final candidates. This is evidence-based inference, not deletion guidance. | Medium |
| Unclear files needing human confirmation | `.env`; `.codex/`; `.vscode/`; many `data/archived/*`; duplicated plot/prune scripts; smoke outputs such as `data/processed/inverse_alias_topk.smoke.json` | Purpose or current status cannot be proven from file names alone. | Low to medium |

## Suspicious Or Risky Issues

| Issue | Evidence | Why It Is Risky |
| --- | --- | --- |
| Dirty git tree before reconstruction docs | `git status --short` shows modified, deleted, and many untracked files | Any later cleanup could accidentally mix forensic documentation with unrelated user changes. |
| Original absolute paths in logs and manifests | Logs contain `/data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced`; Stage11/12 manifests contain `/home/kg_benchmark/runs/...` | Reproduction from the copied workspace may fail unless paths are normalized or documented. |
| Outputs mixed with source code | `src/Pruning graph/stage11_eta_aware_connectivity_repair_full/` contains generated run outputs | Makes source review and provenance reconstruction difficult. |
| Space in path | `src/Pruning graph/` | Shell scripts and Python invocations need careful quoting. |
| Stale runner paths | `scripts/slurm/build_inverse_alias_topk.slurm` and `scripts/slurm/llm_classification_inv.slurm` reference scripts at `src/*.py`, while current files are under `src/inverse_verification_legacy/` | Rerunning the runner from the copied workspace may fail. |
| Multiple similar scripts | `hop_support.py`, `hop_support_copy.py`, `hop_support_v2.py`, `hop_support_v3.py`; multiple pruning scripts; duplicate plotting scripts | Hard to know canonical implementation without execution evidence. |
| Live WDQS dependence | Hop discovery, hop support, composition verification, online construction, and repairs use SPARQL/WDQS evidence | Endpoint drift can change results. |
| LLM provenance gaps | Relation profile artifact exists, and LLM scripts exist, but direct run evidence for initial relation profile generation was not found | Model/prompt/version drift can affect relation universe and targets. |
| Loose environment specification | `requirements.txt` uses package ranges and no lockfile was found | Reproducing exact behavior may be difficult. |
| `.env` in workspace | Hidden-file inventory found `.env`; contents were not read | Potential secret handling issue and hidden dependency on local credentials. |
| Generated caches | `__pycache__` folders and `.venv/` exist | They inflate inventory and can obscure source/artifact boundaries. |

