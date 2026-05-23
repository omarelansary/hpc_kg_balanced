# C4 Configs

`config.template.json` is a planning config for `C4_bridge_aware_replace_add`.

This is not a generated graph candidate. No graph has been produced, no evaluator report exists yet, and `candidate_registry.v1.json` should not be updated until a graph, report package, and human decision exist.

C4 is intended to test a hybrid bridge-aware replacement/addition strategy after earlier evidence showed that deletion-only pruning and eligible-pool bridge rescue were insufficient:

- C2 preserved connectivity but failed the surplus threshold.
- C3 probe v1 found no feasible eligible-pool replacement for tested connectivity-critical bridge-like target edges.

Live WDQS and LLM sources are disabled in this config. Any future generator should use frozen local inputs only unless a new exploratory live-source policy is explicitly approved and documented.
