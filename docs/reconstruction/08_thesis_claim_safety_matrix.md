# Thesis Claim Safety Matrix

## Claim Matrix

| Safe Claim | Unsafe Or Not-Yet-Supported Claim | Required Evidence To Make It Safe |
| --- | --- | --- |
| The relation universe used by hop discovery was restricted to 1703 `wikibase-item` candidate properties. Evidence: `logs/hop_discovery_json_27530562.out`; `src/archive/hop_discovery.py`. | The full upstream relation-profile generation process is fully reproducible. | Production command/log/prompt/model metadata for `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json`; input/output hashes. |
| Empirical two-hop discovery was performed against WDQS. Evidence: `logs/hop_discovery_json_27530562.out`; `data/processed/hop_discovery_from_json.jsonl`. | Two-hop discovery can be reproduced exactly from live Wikidata today. | Frozen WDQS responses or cached discovery output with hash and retrieval timestamp. |
| Hop-support estimation was performed. Evidence: `logs/hop_support_v2_27520503.out`; `logs/normalized_hop_support_v3_rerun28049486.out`; support output hashes. | Hop-support values are stable under rerun against live WDQS. | Frozen support inputs/responses, exact command manifests, endpoint metadata, and output hashes. |
| Composition verification used sampled shortcut checks. Evidence: `src/composition_verification/composition_range_domain_improved.py`; `logs/composition_min8_jsonl_27683654.out`; `logs/composition_hop_support_v3_min8_jsonl_28197929.out`. | Composition verification was purely offline or independent of WDQS. | Cached query-response archive or proof that verifier consumed only frozen local inputs. Current evidence shows WDQS use. |
| Inverse alias construction was run, and inverse LLM verification has partial evidence. Evidence: `logs/build_inverse_alias_topk_27543764.out`; `logs/llm_classification_inv_27548189.out/.err`. | Inverse verification was fully completed. | Complete shard output/report inventory, shard success counts, failed/error counts, model/prompt metadata, and a merged final inverse classification artifact hash. |
| A scaffold for quota-aware graph construction exists in `src/kg_building/relation_balanced_kg_pipeline.py`. | The final graph-construction pipeline used offline quota-aware candidate pools. | Direct execution log/manifest for `relation_balanced_kg_pipeline.py` or equivalent offline run; candidate pool artifact hashes; config showing local candidate input rather than `candidate_source_mode: wdqs`. |
| Online/frontier SPARQL construction attempts existed and were used in Trial9/Trial2 branches. Evidence: Phase4 scripts and logs. | Online/frontier SPARQL construction was definitively abandoned solely because of attach feasibility. | Thesis-author decision note or run report explicitly tying abandonment to attach feasibility, plus supporting Trial2/Trial9 metrics. Current evidence supports this as inference, not a proven sole cause. |
| Stage11/Stage12 repairs were actually run and are post-pipeline repair candidates. Evidence: Stage11/12 manifests and reports. | Stage11/Stage12 repairs are native stages of the originally intended Phase II pipeline. | Thesis decision or design document that reclassifies Stage11/Stage12 as main pipeline stages rather than optional post-pipeline repairs. |
| Stage13 aggressive pruning is a strong candidate final graph. Evidence: Stage13 direct log, report, eta audit, branch summary, hash. | Stage13 pruning is the final reported graph. | Human confirmation that Stage13 is the final thesis artifact and should be included in the reported pipeline. |
| The final graph candidates can be hashed and audited from copied artifacts. Evidence: `canonical_artifact_hashes.tsv`; Stage12/Stage13 reports. | The final graph is reproducible from frozen inputs. | Complete hash chain from raw relation profiles through hop discovery, support, compatibility, composition, allocation, graph construction/repair/pruning, plus environment lock and command manifests. |

## Missing-Evidence Checklist

Before thesis writing, find or decide exactly these items:

1. Final graph choice: Stage12 largest component, Stage13 aggressive pruned graph, or another explicitly named artifact.
2. Final allocation choice: strongest current candidate for Stage12/Stage13 is `src/Pruning graph/bidirectional_allocation_results5k.json`, but it needs human confirmation.
3. LLM relation-profile provenance: prompt, model, temperature, schema, run command, raw responses or output hash for `data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json`.
4. Inverse shard completion: all shard outputs/reports, error counts, merged output, and acceptance criteria.
5. External Stage11/Stage12 input path mapping: map `/home/kg_benchmark/runs/...` and `/home/kg_benchmark/src/kg_builder/input/bidirectional_allocation_results5k.json` to copied-workspace artifacts.
6. Environment lock: exact Python version, packages, OpenAI client version, and any system dependencies.
7. Hash chain: raw inputs, intermediate outputs, allocation, graph, reports, logs, and configs.
8. Offline Phase II execution evidence, if the thesis claims it: direct log/manifest/config showing offline candidate pools and the executed construction stages.

## Claims That Should Be Avoided Until Evidence Is Added

- Avoid: "The final graph was built by the offline eight-stage Phase II pipeline."
- Safer: "The repository contains a Phase II scaffold, but the inspected final graph candidates are evidenced through Stage11/Stage12 repair and Stage13 pruning artifacts."

- Avoid: "Inverse verification completed successfully."
- Safer: "Inverse alias construction is evidenced; inverse LLM verification has partial shard evidence and unresolved API failures."

- Avoid: "Stage13 is the final dataset."
- Safer: "Stage13 aggressive_but_guarded is the strongest candidate final pruned dataset, pending human confirmation."

- Avoid: "The pipeline is exactly reproducible from live services."
- Safer: "The copied artifacts are hashable and auditable; exact rerun reproducibility requires frozen service-derived inputs and environment locking."

