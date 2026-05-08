# Open Questions

## Critical Human-Confirmation Questions

| ID | Question | Why It Matters | Evidence So Far | Suggested Resolution |
| --- | --- | --- | --- | --- |
| Q1 | Which allocation artifact is canonical for the thesis graph? | Eta quotas define expected relation counts and deficits. | Multiple allocation files exist: `data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json`, `data/connectedgraph/bidirectional_allocation_results_allsupp8_conf97_compconf90.json`, `data/processed/hop_support_v3/bidirectional_allocation_results_hop_v3_patchedby_v2_allsup50_60sym_99anti_90inv_95comp.json`, `src/Pruning graph/bidirectional_allocation_results5k.json`. | Choose one canonical allocation per reported graph and record hash. |
| Q2 | Is Stage13 `aggressive_but_guarded/pruned_graph.jsonl` the final reportable graph, or is Stage12 `largest_component.csv` the final graph? | Final graph choice affects all thesis metrics. | Stage12 eta analysis is strong; Stage13 April sweep preserves weak connectivity and improves balance by removing 460 triples. | Record final graph decision and cite the corresponding audit summary. |
| Q3 | How was `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json` generated? | It appears upstream of the 1703 wikibase-item universe and LLM target filtering. | `classify_relations_pipeline.py` exists; hop discovery consumed the relation-profile file; direct run log was not found. | Locate run log, notebook, command history, or raw LLM response archive. |
| Q4 | Are inverse LLM shards complete enough to support inverse pattern claims? | Inverse classifications affect allocation groups. | Shard7 log shows many OpenAI 429 errors and many `ERROR` decisions; complete shard report set was not proven. | Build shard completion table and count accepted inverse labels by shard. |
| Q5 | Was `relation_balanced_kg_pipeline.py` ever executed as the final Phase II pipeline? | Intended Phase II claims depend on actual execution evidence. | Source and config exist; no matching run log found; config uses `candidate_source_mode: wdqs`. | Search external run folders or shell history; otherwise present as scaffold/planned pipeline. |
| Q6 | Which Stage11/Stage12 input graph corresponds to the copied workspace? | Stage11/12 manifests reference `/home/kg_benchmark/runs/...`, outside this workspace. | Stage11/12 manifests and reports exist under `src/Pruning graph/...`; original input path is external. | Map external production run path to copied artifacts or mark input missing. |
| Q7 | Is the old Stage13 ablation from March part of the thesis narrative? | March ablation appears structurally destructive compared with April branch sweep. | Existing comparison note reports March ablation largest component fraction 0.1403; April branch sweep keeps weak component count 1. | Treat March ablation as failed experiment unless thesis uses it as contrast. |
| Q8 | Which support matrix is canonical? | Phase II input requires exported support matrix. | Matrix-related scripts and CSV/JSON artifacts exist, but several allocation/support variants exist. | Link one support matrix to the selected allocation and graph. |
| Q9 | Are missing log-referenced outputs recoverable? | Copied workspace may not contain every artifact from original execution. | Trial2 log references `data/connectedgraph/hop_support_v3/trial2_connected_allocation_sample.watch.triples.jsonl`; copied workspace contains checkpoint postprocess output. | Locate original artifact or document that only postprocessed output is available. |
| Q10 | Should online/frontier SPARQL attempts be described as abandoned, superseded, or negative-result experiments? | The thesis narrative must not overstate final pipeline design. | Online attempts are confirmed; existing comparison note labels Trial2 online as abandoned; later Stage11/12/13 outputs exist. | Add a thesis note explaining why online attach-only sampling failed. |

## Evidence Gaps

| Gap | Current Evidence | Impact |
| --- | --- | --- |
| No clean run manifest for entire pipeline | Logs and artifacts are distributed across `logs/`, `data/`, `src/Pruning graph/`, and external paths | Execution order remains reconstructed rather than formally recorded. |
| No hash chain from raw inputs to final graph | Outputs generally lack input SHA256 metadata | Reproducibility cannot be proven cryptographically. |
| No complete environment lock | `requirements.txt` has loose ranges; `.venv/` exists | Package drift can change behavior. |
| No full LLM provenance bundle | Scripts show prompts/models, but production metadata is incomplete | LLM-based relation filtering is not fully defensible. |
| No direct allocation export log | Allocation artifacts exist and source supports generation | Thresholds and interactive UI state may be underdocumented. |
| No confirmed offline candidate-pool run | Phase II scaffold exists, but evidence points to live-WDQS config or later repair/pruning runs | Intended offline quota-aware story needs qualification. |

## Conflicts Or Mismatches

| Conflict | Evidence | Interpretation |
| --- | --- | --- |
| Intended Phase II has eight stages, but scaffold exposes seven stage directories/subcommands | `relation_balanced_kg_pipeline.py` stage names include stage01 through stage07/final-audit | Stage numbering must be reconciled before thesis documentation. |
| Intended offline candidate pools versus config using WDQS | `relation_balanced_kg_pipeline_config.yaml` has `candidate_source_mode: wdqs` and `candidate_input_path: null` | Offline candidate-pool execution is not confirmed by current workspace evidence. |
| Inverse runner paths are stale | SLURM runners reference `src/*.py`, current scripts are under `src/inverse_verification_legacy/` | Current workspace cannot rerun those jobs without path correction. |
| Stage12 eta analysis allocation path does not match current local path | Summary references `src/kg_builder/input/bidirectional_allocation_results5k.json`; copied workspace has `src/Pruning graph/bidirectional_allocation_results5k.json` | Path translation is required. |
| Generated outputs live under source tree | Stage11/12/13 outputs under `src/Pruning graph/` | Current filesystem does not separate source from run artifacts. |

## Items To Verify Before Refactoring

1. Compute SHA256 hashes for candidate final artifacts and selected upstream inputs.
2. Produce a table of every SLURM log, command, start/end time, exit status, input path, and output path.
3. Confirm final graph and final allocation artifact with the thesis author.
4. Audit inverse LLM shard completion and relation-profile LLM provenance.
5. Locate or document absent external run inputs from `/home/kg_benchmark/runs/...`.
6. Decide whether `relation_balanced_kg_pipeline.py` is a planned replacement, an unrun scaffold, or an executed pipeline with logs outside this copied workspace.

