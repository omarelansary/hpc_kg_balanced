# R2.8 Genericity Support Matrix Provenance

## Executive Summary

The canonical support matrix used by archived Stage1 genericity scoring is:

`archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json`

SHA256:

`75794511aaa9ef72a7c63fd0d9a3c11969b72c4fa4bfb01237859b612f544041`

Status: **partial provenance**.

Confirmed:

- The artifact exists and has a stable SHA256.
- The JSON schema matches the nested sparse support-matrix format consumed by Stage1.
- Its outer relation set exactly matches the 139 unique positive-eta relations in the canonical 5k allocation after duplicate relation rows are merged.
- The archived Phase II run manifest and config point Stage1 to `src/kg_builder/input/genericity_support_matrix.adjacency_support.json`.
- The archived pipeline code loads `support_matrix_path` in `stage_score_genericity`.

Not confirmed:

- No direct dashboard export command or saved dashboard session was found.
- No same-run manifest cryptographically links this support matrix hash to the exact 5k allocation hash.
- Exact regeneration from Phase I inputs remains incomplete.

## Canonical Support Matrix Artifact

| Artifact | Size bytes | SHA256 | Role |
|---|---:|---|---|
| `archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json` | 18732 | `75794511aaa9ef72a7c63fd0d9a3c11969b72c4fa4bfb01237859b612f544041` | Stage1 genericity support matrix |

Search result: only one file named `genericity_support_matrix.adjacency_support.json` was found in the workspace. No separate non-archive duplicate copy was identified.

## Schema And Content

The support matrix is a JSON object:

```text
{
  "Pxx": {"Pyy": support_weight, ...},
  ...
}
```

It is sparse: missing cells are omitted and interpreted as zero by Stage1.

| Metric | Value |
|---|---:|
| outer relation keys | 139 |
| inner relation keys appearing in nonzero cells | 129 |
| nonempty rows | 134 |
| zero rows | 5 |
| nonzero cells | 831 |
| minimum nonzero weight | 50.0 |
| maximum nonzero weight | 2126780.0 |
| sum of nonzero weights | 10899602.0 |

Zero rows:

`P1001, P1889, P279, P31, P361`

The ten allocated relations that do not appear as inner keys are:

`P10374, P1158, P13210, P2353, P3833, P4353, P5277, P7209, P814, P8308`

This is not evidence of relation loss. It means those relations do not appear as nonzero columns in the sparse matrix. Stage1 explicitly reads missing row/column cells as zero support.

## Relation-Set Compatibility With Canonical 5k Allocation

Canonical allocation used for comparison:

`src/Pruning graph/bidirectional_allocation_results5k.json`

SHA256:

`a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

The allocation contains 154 allocation rows and 139 unique positive-eta relations after duplicate relation rows are merged.

| Check | Result |
|---|---|
| Support-matrix outer relation set equals merged 5k allocation relation set | `True` |
| Support outer minus allocation relations | `[]` |
| Allocation relations minus support outer | `[]` |
| Inner relation set equals outer relation set | `False` |
| Inner relation set is subset of outer relation set | `True` |
| Inner minus outer | `[]` |

Interpretation: the support matrix has a complete row key for every allocated relation used by the canonical 5k allocation. Its column key set is sparse and smaller because only nonzero columns are serialized.

## Stage1 Consumption Evidence

| Evidence | Path / lines | Interpretation |
|---|---|---|
| Run manifest records support matrix path | `archive/hetzner_version/runs/prod_refine_20260315_180520/manifest.json:1-45` | `support_matrix_path` is `src/kg_builder/input/genericity_support_matrix.adjacency_support.json`. |
| Archived production config describes Stage1 support matrix | `archive/hetzner_version/src/kg_builder/config.yaml:64-67` | The matrix is described as dashboard-exported nested JSON for Stage1 genericity scoring. |
| Pipeline loader schema | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py:565-583` | Stage1 accepts JSON object `{row_relation: {col_relation: value}}`. |
| Genericity scorer uses row and reverse-column lookups | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py:616-646` | The scorer computes support mass and coverage from the support matrix over allocated relations. |
| Stage1 runner loads support matrix directly | `archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py:2128-2134` | `stage_score_genericity` loads `ctx.config.support_matrix_path` before scoring. |
| R2.6 provenance confirms Stage1/Stage2 context | `docs/reconstruction/32_stage1_stage2_candidate_collection_provenance.md` | Stage1 consumed canonical allocation plus support matrix. |

Stage1 consumption status: **confirmed by manifest/config/code path**. A dedicated runtime log line saying "loaded support matrix" was not found in `archive/hetzner_version/logs/relation_balanced_kg_pipeline.out`.

## Likely Producer Code

Most likely producer/exporter: `src/statistics/hop_pattern_analysis_dashboard.py`.

| Evidence | Path / lines | Interpretation |
|---|---|---|
| `adjacency_support` mode returns raw adjacency support | `src/statistics/hop_pattern_analysis_dashboard.py:596-610` | Code supports the matrix mode in this filename. |
| Nested JSON serializer | `src/statistics/hop_pattern_analysis_dashboard.py:637-647` | Serializes the exact nested JSON schema consumed by Stage1. |
| Positive-eta relation subset for genericity export | `src/statistics/hop_pattern_analysis_dashboard.py:1576-1602` | Export uses current positive-eta allocation relation set. |
| Download button for Genericity Matrix JSON | `src/statistics/hop_pattern_analysis_dashboard.py:1628-1649` | Export filename pattern is `genericity_support_matrix.{genericity_matrix_mode}.json`. |
| Config template requires paired dashboard exports | `src/kg_building/relation_balanced_kg_pipeline_config.yaml:11-36` | Design says allocation JSON and genericity matrix should be exported from the same dashboard run. |

Producer status: **code-path confirmed, exact artifact export inferred**. No direct command/log proves this exact file was generated in a recorded dashboard session.

## Same-Run Linkage To The 5k Allocation

The support matrix is relation-compatible with the canonical 5k allocation because its outer keys exactly match the 139 merged positive-eta relations.

However, relation compatibility is not the same as cryptographic same-run provenance.

No artifact was found that records both:

- support matrix SHA256 `75794511aaa9ef72a7c63fd0d9a3c11969b72c4fa4bfb01237859b612f544041`
- allocation SHA256 `a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb`

in the same export manifest or command record.

Same-run linkage status: **partial**.

## Answers To R2.8 Questions

1. **What is the canonical support matrix path and SHA256?**  
   `archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json` with SHA256 `75794511aaa9ef72a7c63fd0d9a3c11969b72c4fa4bfb01237859b612f544041`.

2. **Are there local/archive duplicate copies?**  
   Only one exact-name copy was found in the workspace. No separate non-archive duplicate was identified.

3. **What is the JSON schema?**  
   Sparse nested object: relation row key -> relation column key -> numeric support weight.

4. **How many outer relations, inner relations, nonempty rows, and nonzero cells?**  
   139 outer relations, 129 inner relations, 134 nonempty rows, and 831 nonzero cells.

5. **Does the outer relation set match the 139 unique allocated relations in the 5k allocation?**  
   Yes. The sets match exactly after duplicate allocation rows are merged by relation.

6. **Does the inner relation set match the outer relation set?**  
   No. The inner set has 129 relations and is a subset of the 139 outer relations.

7. **Which relations are missing as inner keys?**  
   `P10374, P1158, P13210, P2353, P3833, P4353, P5277, P7209, P814, P8308`.

8. **Did Stage1 consume this support matrix directly?**  
   Yes, by manifest/config/code-path evidence. The archived Stage1 runner loads `ctx.config.support_matrix_path`.

9. **Which script most likely produced/exported this support matrix?**  
   `src/statistics/hop_pattern_analysis_dashboard.py` through the Genericity Matrix JSON download path.

10. **Is there direct command/log evidence for producing it?**  
   No direct export command or dashboard session log was found.

11. **Is it cryptographically linked to the exact 5k allocation export?**  
   No. It is relation-compatible and co-located with the archived allocation, but no same-run manifest records both hashes.

12. **Is the support matrix provenance confirmed, partial, ambiguous, or unresolved?**  
   Partial. Artifact identity, schema, relation-set compatibility, and Stage1 consumption are confirmed; exact export provenance and same-run allocation linkage are not.

13. **What exact thesis claim is safe?**  
   Safe: "Stage1 genericity scoring used a sparse adjacency-support matrix whose row relation set exactly matched the 139 unique positive-eta relations in the canonical 5k allocation."

14. **What claim is unsafe?**  
   Unsafe: "The support matrix was regenerated or exported in the same dashboard session as the 5k allocation with a preserved command and cryptographic manifest."

## Thesis Claim Safety

| Claim | Status | Recommended wording |
|---|---|---|
| Stage1 consumed `genericity_support_matrix.adjacency_support.json`. | Safe | Cite archived manifest/config and Stage1 code. |
| The matrix outer relation set matches the 139 canonical allocation relations. | Safe | Cite this report and JSON evidence. |
| The matrix uses adjacency-support weights in sparse nested JSON form. | Safe | Cite dashboard serializer and Stage1 loader. |
| The support matrix and allocation were intended to be paired dashboard exports. | Safe as design/code-path evidence | Use "intended to be paired" or "code-compatible and relation-compatible". |
| The support matrix and allocation were definitely exported in the same dashboard session. | Unsupported | Avoid unless a same-run export manifest/command is found. |
| The support matrix can be regenerated exactly from preserved Phase I inputs. | Unsupported | Requires saved dashboard state, inputs, thresholds, and hashes. |

## Remaining Gaps

- Missing direct Streamlit/dashboard export command for this support matrix.
- Missing same-run manifest containing both support matrix and allocation output hashes.
- Missing embedded input paths/hashes in the support matrix artifact itself.
- Missing exact dashboard state for genericity matrix mode, although the filename and dashboard default support `adjacency_support`.
- Full Phase I-to-support-matrix reproducibility remains incomplete.

## Machine-Readable Evidence

A structured evidence record was written to:

`artifacts/final_graph/selected_final_graph/rebuild/support_matrix_provenance.json`
