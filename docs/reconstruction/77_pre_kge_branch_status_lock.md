# Pre-KGE Branch Status Lock

## 1. Purpose

This document locks the current branch state before interpreting KGE results as thesis evidence, generating a new KG candidate, continuing C5-H2, or opening new construction branches.

It is not a final thesis result document. It is a decision map that records what is currently supported, what remains bounded, and what must not be claimed.

## 2. Global Status Summary

- A connected realization exists.
- The current connected realization is relation-complete and connected: B0 covers `139/139` allocated relations and has one weak component.
- B0 is not perfectly balanced and is classified as `provisional_baseline_not_final_solution`.
- Balance-first deletion can reduce surplus, but the tested stress endpoint damages connectivity.
- Replacement, auxiliary, and synthetic branches have bounded evidence.
- No current branch has yet produced a clean final KG that is both connected and substantially better balanced under canonical allocation constraints.
- KGE interpretation is not locked until protocol, split, model, metric, seed, command, and result artifacts are recorded.

## 3. Framework/Reproducibility Status

| Component | Current status | Evidence | Limitation | Next action |
| --- | --- | --- | --- | --- |
| Frozen validation | done | `docs/reconstruction/70_reusable_A_to_Z_pipeline_runner.md`; `scripts/reconstruction/check_required_artifacts.sh` | Requires restored frozen evidence artifacts. | Keep as default guardrail. |
| Phase I replay/allocation/matrix | done | `docs/reconstruction/70_reusable_A_to_Z_pipeline_runner.md`; `docs/reconstruction/72_phase1_run_scoped_replay.md` | Safe replay covers run-scoped allocation/matrix export comparison, not live dashboard state. | Use saved configs/artifacts; keep Streamlit manual-only. |
| Stage1/Stage3 replay | partial | `docs/reconstruction/73_phase2_stage1_stage3_run_scoped_replay.md` | Run-scoped Stage1/Stage3 slices exist, but do not regenerate B0. | Keep as replay slice; do not promote to full graph regeneration. |
| Stage4 wrapper | partial | `docs/reconstruction/70_reusable_A_to_Z_pipeline_runner.md`; `docs/reconstruction/71_level2_replay_design_audit.md` | Guarded, long-running, skipped by default; not a full B0 regeneration path. | Keep disabled by default; require explicit objective and run-scoped outputs. |
| Full historical KG regeneration | not_done | `docs/reconstruction/71_level2_replay_design_audit.md` | Stage4-7 wrappers, Stage11/12 no-live wrappers, and Stage13 SLURM tracking are incomplete. | Do not claim end-to-end regeneration. |
| New KG generation | not_done | `docs/reconstruction/70_reusable_A_to_Z_pipeline_runner.md`; C5 branch docs | General new-candidate generation is not a reusable solved pathway. | Define objective weights and edge provenance before any new generator. |
| Packaging of candidates | done | `docs/reconstruction/70_reusable_A_to_Z_pipeline_runner.md`; `artifacts/final_graph/selected_final_graph/rebuild/candidate_registry.v1.json` | Packages existing frozen registered candidates only. | Use for B0/C1 comparison and frozen candidate handoff. |
| KGE protocol | not_done | This lock; `docs/reconstruction/76_C5_H2_auxiliary_support_pre_kge_status.md` | Protocol, split, model, seed, metrics, commands, and result artifacts are not locked here. | Lock KGE protocol before interpreting results. |

## 4. Branch Status Matrix

| branch_id | branch_name | tested_question | evidence_files | output_or_result | supported_conclusion | not_supported | decision_state | next_action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `B0` | Connected realization | Can a frozen graph remain connected, relation-complete, duplicate-free, and auditable? | `docs/reconstruction/68_final_endpoint_and_branch_synthesis.md`; `docs/reconstruction/69_B0_provisional_baseline_status_audit.md`; `artifacts/final_graph/selected_final_graph/rebuild/final_endpoint_branch_synthesis.json` | `24,683` triples, `139/139` relations, `1` weak component, surplus `6,702`, deficit `2,019`. | B0 is the current frozen connected baseline. | B0 is not optimal, not final balanced, and not proof the construction problem is solved. | keep_as_reference | Use as baseline only with limitations and KGE protocol lock. |
| `balance_first_stress_test` | Connectivity-relaxed balance-first pruning | Can surplus be reduced by aggressive deletion? | `docs/reconstruction/68_final_endpoint_and_branch_synthesis.md`; `docs/reconstruction/69_B0_provisional_baseline_status_audit.md` | Surplus reduced to `105`, but weak components increased to `5,623`. | Balance can improve by deletion in the tested setup. | This does not prove no connected balanced alternative exists. | closed_for_now | Keep as diagnostic stress evidence. |
| `C1` | Guarded surplus pruning | Does Stage13 guarded pruning beat B0 enough to replace it? | `docs/reconstruction/19_final_graph_selection_decision.md`; `docs/reconstruction/graph_candidates.tsv`; `docs/reconstruction/graph_candidate_reports/C1_stage13_aggressive.report.json` | C1 preserves connectivity and relation coverage; surplus improves from `6,702` to `6,582`, but deficit worsens from `2,019` to `2,359`. | C1 is a valid comparison candidate. | C1 does not supersede B0 under the recorded final decision. | closed_for_now | Keep as nonselected candidate evidence. |
| `C2` | Targeted safe deletion | Can targeted deletion of generic surplus preserve hard constraints and beat the surplus threshold? | `docs/reconstruction/12_C2_result_interpretation.md`; `experiments/graph_candidates/C2_targeted_generic_pruning/reports/evaluator.report.json`; `experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json` | Preserved connectivity and coverage, but surplus was `6,675`; only `27` removals accepted. | Deletion-only pruning can be safe but too weak under current objective. | C2 is not a final candidate and does not solve balance. | closed_for_now | Use as negative evidence against deletion-only next steps. |
| `C3_probe_v1` | Remove-and-replace probe | Can eligible replacement pool v1 rescue connectivity-critical generic deletions? | `docs/reconstruction/17_C3_feasibility_probe_result.md`; `experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1/feasibility_probe_report.json` | No graph generated; `0` feasible replacements for `473` connectivity-critical bridge-like targets. | Eligible pool v1 did not solve the tested bridge-rescue problem. | C3 is not a generated graph and does not improve B0/C1/C2. | closed_for_now | Reopen only with a new candidate source or a changed, explicit operation policy. |
| `C4` | Strict allocated bridge replacement | Can strict allocated replacements remove surplus bridge edges while preserving constraints? | `docs/reconstruction/56_C4_branch_decision_audit.md`; `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/probe_report.json` | First `200` surplus target bridge edges had `0` feasible strict replacements. | Strict C4 is not justified from current frozen evidence. | This does not prove all replacement methods fail globally. | closed_for_now | Reopen only with allocated, cut-crossing, surplus-improving candidates. |
| `C4_1` | Replacement-pool bridge-cut audit | Did eligible pool v1 cross the tested bridge cuts? | `docs/reconstruction/56_C4_branch_decision_audit.md`; `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/replacement_pool_bridge_cut_audit.json` | `990` rows loaded; `0` crossed any tested cut. | The pool failed primarily on bridge-cut crossing coverage. | This does not prove future pools cannot cross cuts. | closed_for_now | Build a new cut-aware pool only with explicit objective and frozen evidence. |
| `C4_2` | Local cut-crossing search | Does broader frozen local evidence contain cut-crossing candidates? | `docs/reconstruction/56_C4_branch_decision_audit.md`; `experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/local_cut_crossing_candidate_search.json` | `625` unique cut-crossing candidates found; `546` surplus-reducing candidate-cut pairs were unallocated. | Cut-crossing evidence exists locally, but surplus-reducing evidence is unallocated. | It does not validate unallocated evidence as canonical allocated replacement. | open_bounded | Feed auxiliary-labeled branches only; do not call it strict replacement success. |
| `C5_H1` | Allocated support | Do allocated observed cut-crossing candidates improve balance? | `docs/reconstruction/58_C5_H1_H2_probe.md`; `experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/c5_h1_h2_probe_report.json` | `109` connectivity-preserving H1 moves; `0` balance-improving H1 moves. | H1 has connectivity signal but no balance-improving signal. | A strict H1 generator is not justified. | closed_for_now | Reopen only with new allocated candidates or changed objective. |
| `C5_H2` | Auxiliary unallocated support | Can observed unallocated auxiliary edges preserve full connectivity while pruning surplus canonical bridge edges? | `docs/reconstruction/58_C5_H1_H2_probe.md`; `docs/reconstruction/66_C5_H2_marginal_utility_decision_audit.md`; `docs/reconstruction/76_C5_H2_auxiliary_support_pre_kge_status.md` | Expanded package: `3,643` auxiliary edges, `3,643` canonical removals, surplus `6,702 -> 3,059`, full WCC `1`, canonical-only WCC `3,471`. | C5-H2 preserves full connectivity in the auxiliary-supported graph while reducing surplus, but canonical-only connectivity still fragments. | It is not canonical-final and not a B0 replacement because connectivity depends on unallocated auxiliary edges. | continue_candidate | Run KGE only after protocol lock and report auxiliary dependence explicitly. |
| `C5_H2_diversity` | Diversity reranking | Can relation concentration be reduced without losing surplus benefit? | `docs/reconstruction/66_C5_H2_marginal_utility_decision_audit.md`; `docs/reconstruction/76_C5_H2_auxiliary_support_pre_kge_status.md` | Cap-50 P17 concentration was reduced from `39/50` to `1/50`; expanded strategy has P17 share about `0.341`. | Diversity can reduce concentration under tested policies. | Diversity does not remove auxiliary dependence or make the graph canonical-only connected. | open_bounded | Keep diversity as a selection criterion for auxiliary candidates. |
| `H3` | Bounded synthetic pattern-derived candidates | Can verified pattern rules synthesize bridge alternatives under bounded frozen evidence? | `docs/reconstruction/67_H3_synthetic_pattern_feasibility_audit.md`; `experiments/graph_candidates/H3_synthetic_pattern_feasibility/reports/h3_synthetic_pattern_feasibility_report.json` | `0` synthetic candidates found over `200` cuts. | H3 graph generation is not justified from this bounded audit. | This does not prove all synthetic methods fail. | closed_for_now | Reopen only with broader source scope or changed bridge-target definition. |
| `stage4_7_replay_full_regeneration` | Stage4-7 replay/full regeneration | Can historical graph generation be safely replayed from frozen/local inputs? | `docs/reconstruction/70_reusable_A_to_Z_pipeline_runner.md`; `docs/reconstruction/71_level2_replay_design_audit.md`; `docs/reconstruction/73_phase2_stage1_stage3_run_scoped_replay.md` | Stage1/Stage3 run-scoped slices exist; Stage4 wrapper is guarded; full B0 regeneration is not safe today. | Some framework pieces exist. | Full historical regeneration is not yet reproducible or safe. | open_bounded | Continue wrapper work only with run-scoped outputs and no-live guards. |
| `live_new_candidate_pool_expansion` | Live/new candidate-pool expansion | Can a broader or live source find better cut-aware evidence? | `docs/reconstruction/56_C4_branch_decision_audit.md`; `docs/reconstruction/57_C5_hypothesis_matrix_and_branch_spec.md`; `docs/reconstruction/68_final_endpoint_and_branch_synthesis.md` | Mentioned as future/non-canonical option; no locked local result. | It remains a possible future branch. | No claim can be made until results are frozen, hashed, audited, and evaluated. | open_bounded | Define source boundary and freeze policy before implementation. |
| `broader_synthetic_strategy` | Broader synthetic strategy | Can synthetic/pattern-derived methods work beyond the bounded H3 audit? | `docs/reconstruction/57_C5_hypothesis_matrix_and_branch_spec.md`; `docs/reconstruction/67_H3_synthetic_pattern_feasibility_audit.md`; `docs/reconstruction/68_final_endpoint_and_branch_synthesis.md` | Bounded H3 found zero candidates; broader synthetic scope is unresolved. | Bounded H3 is negative evidence for that scope. | It does not globally rule out all synthetic methods. | open_bounded | Define explicit rule source, thresholds, labels, and evaluation policy before any generation. |
| `KGE_evaluation_branch` | KGE evaluation | Do graph variants improve downstream utility? | No locked KGE protocol/result artifact in the inspected reconstruction docs. | KGE interpretation remains unlocked. | KGE can become decision evidence only after protocol and results are recorded. | No causal diagnosis of weakness is supported yet. | needs_protocol_lock | Lock protocol and artifact hashes before interpreting results. |

## 5. Closed-for-Now Branches

- `balance_first_stress_test`: closed because the tested deletion-heavy endpoint fragments into `5,623` weak components. It would reopen only with a method that preserves a documented connectivity/component policy.
- `C1`: closed as a replacement for B0 because it reduces surplus modestly but worsens total deficit. It would reopen only if the reporting objective explicitly prioritizes lower surplus/density over deficit and accepts Stage13 as the reported endpoint.
- `C2`: closed because deletion-only pruning accepted only `27` removals and failed the surplus threshold. It would reopen only with a non-deletion-only operation or a new objective.
- `C3_probe_v1`: closed because eligible pool v1 did not rescue tested connectivity-critical bridge-like deletions. It would reopen only with a new replacement pool or a different operation policy.
- `C4` and `C4_1`: closed because strict allocated replacement evidence did not cross or improve tested bridge cuts. They would reopen only with allocated, cut-crossing, surplus-improving candidates.
- `C5_H1`: closed because allocated cut-crossing moves preserved connectivity but did not improve balance. It would reopen only with new allocated candidate evidence.
- `H3`: closed for the bounded synthetic-pattern audit because it found zero candidates. It would reopen only with broader source scope or a revised target/rule definition.

These closures are scoped to the tested evidence. They are not global impossibility claims.

## 6. Open but Bounded Branches

- `C4_2`: may support auxiliary or new-pool branches because local cut-crossing evidence exists, but it is not strict allocated replacement success. Minimal closing test: determine whether a frozen allocated cut-aware pool can produce surplus-improving replacements.
- `C5_H2`: may support an experimental auxiliary-labeled candidate because the expanded package is structurally connected and reduces surplus. It is not final because full connectivity depends on unallocated auxiliary edges. Minimal closing test: run locked KGE protocol on B0, full auxiliary graph, and optional canonical-only graph.
- `C5_H2_diversity`: may improve auxiliary relation concentration. It is not final because it does not solve canonical-only fragmentation. Minimal closing test: compare KGE and relation-distribution effects under a locked protocol.
- `live_new_candidate_pool_expansion`: may find additional observed evidence, but it is non-canonical until frozen and audited. Minimal closing test: define and freeze a candidate-source artifact with hashes.
- `broader_synthetic_strategy`: may explore pattern-derived triples beyond bounded H3, but it is unresolved. Minimal closing test: define explicit pattern rules, confidence thresholds, labels, and a no-unmarked-synthetic policy before any generation.
- `stage4_7_replay_full_regeneration`: may improve reproducibility, but it is not a candidate-quality branch. Minimal closing test: run-scoped Stage4-7 wrappers plus no-live Stage11/12 replay policy.

## 7. KGE Protocol Lock Required

KGE results must not be used as causal diagnosis until the following are locked:

- KG artifact path and hash;
- train/valid/test split method;
- model(s);
- loss;
- negative sampling;
- filtered versus unfiltered ranking;
- metric(s);
- seed(s);
- evaluation library/version;
- exact command;
- exact result artifact path;
- whether auxiliary or synthetic edges are included and how they are labelled.

Without these fields, do not claim that balance, sparsity, auxiliary support, or relation distribution caused a KGE result.

## 8. Acceptance Criteria for a New KG Candidate

A new candidate is better than the connected realization only if it improves a defined objective while preserving required structural and provenance constraints. It must satisfy:

- `139/139` allocated relation coverage unless explicitly relaxed;
- duplicate-free triples;
- connectivity or a documented component policy;
- lower surplus and/or lower composition dominance;
- no hidden auxiliary or synthetic edges;
- provenance labels for canonical, auxiliary, and synthetic edges;
- KGE protocol compatibility;
- reproducible command or package manifest.

Improving one metric alone is not enough. A candidate that lowers surplus but fragments the graph, hides auxiliary evidence, or lacks reproducible artifact hashes is not a clean endpoint improvement.

## 9. Safe Claims and Unsafe Claims

### Safe Claims

| Claim | Scope |
| --- | --- |
| The connected realization exists and is audited. | B0 frozen evidence. |
| The connected realization is not perfectly balanced. | B0 surplus/deficit and composition surplus metrics. |
| Balance-first deletion improves surplus but damages connectivity under the tested setup. | Tested stress endpoint only. |
| Some replacement and auxiliary branches have bounded evidence. | C3/C4/C5 branch reports. |
| C5-H2 auxiliary support is promising as an experimental auxiliary branch but not canonical-final. | Expanded C5-H2 package and pre-KGE status. |
| KGE interpretation requires a protocol lock. | Current reconstruction docs do not lock KGE protocol/result artifacts. |

### Unsafe Claims

| Claim | Why unsafe |
| --- | --- |
| B0 is optimal. | No global search or proof exists. |
| B0 is the final balanced benchmark. | B0 is explicitly provisional and imbalanced. |
| All pruning fails. | Only tested pruning variants are evidenced. |
| All replacement fails. | C3/C4 results are bounded by candidate pools and target spaces. |
| All synthetic methods fail. | H3 is bounded and found zero candidates only in that scope. |
| KGE weakness is caused by balance or sparsity. | KGE protocol and result artifacts are not locked here. |
| Auxiliary edges are canonical allocated evidence. | C5-H2 auxiliary edges are observed but unallocated and separately labelled. |

## 10. Current Decision

- Do not generate random new KGs.
- Lock this branch map first.
- Then choose one explicit path:
  - A. package the current connected realization for KGE with a protocol lock;
  - B. continue C5-H2 only as auxiliary-supported candidate evaluation with labels;
  - C. open a new candidate-pool or controlled-addition branch with an explicit objective;
  - D. abandon a branch only with evidence and reason.

The current best candidate for immediate KGE handoff is not a new final KG. It is the comparison set: B0, the C5-H2 full auxiliary graph, and optionally the C5-H2 canonical-only diagnostic graph, all under one locked KGE protocol.

## 11. Minimal Next Actions

1. Lock this document and JSON.
2. Lock KGE protocol before interpreting KGE.
3. Decide whether the next KG candidate should be canonical-only or auxiliary-labelled.
4. If continuing C5-H2, define acceptance criteria before further generation.
5. If opening a new branch, define objective weights before implementation.
