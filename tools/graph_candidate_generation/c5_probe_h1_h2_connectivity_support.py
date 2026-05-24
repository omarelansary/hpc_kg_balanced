#!/usr/bin/env python3
"""Probe C5 H1/H2 connectivity-support hypotheses without generating a graph."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.allocation_metrics import load_allocation  # noqa: E402
from src.kg_pipeline.evaluation.candidate_report import evaluate_candidate, sha256_file  # noqa: E402
from src.kg_pipeline.evaluation.graph_io import Triple, load_graph_triples  # noqa: E402
from tools.graph_candidate_generation.c4_probe_bridge_aware_replace_add import (  # noqa: E402
    relation_delta,
    repo_relative,
    resolve_path,
)
from tools.graph_candidate_generation.c4_search_local_cut_crossing_candidates import (  # noqa: E402
    candidate_sources,
    iter_jsonl_triples,
    prepare_tested_cuts,
    row_source_metadata,
)

DEFAULT_CONFIG = Path("experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/configs/config.template.json")
DEFAULT_OUTPUT_DIR = Path("experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only")
REPORT_JSON = "c5_h1_h2_probe_report.json"
REPORT_MD = "c5_h1_h2_probe_summary.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--max-cuts", type=int, default=200)
    parser.add_argument("--max-candidates", type=int, default=1000)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_c5_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "kg-candidate-hypothesis-matrix-config-v1":
        raise ValueError(f"Unexpected C5 config schema_version: {config.get('schema_version')!r}")
    for key in ("allowed_live_sources", "allowed_wdqs", "allowed_llm", "allowed_synthetic_pattern_derived"):
        if config.get(key) is not False:
            raise ValueError(f"C5 H1/H2 probe requires {key}=false")
    if config.get("first_probe_hypotheses") != ["H1", "H2"]:
        raise ValueError("C5 H1/H2 probe expects first_probe_hypotheses to be ['H1', 'H2']")
    return config


def output_paths() -> dict[str, Path]:
    return {
        "json": DEFAULT_OUTPUT_DIR / REPORT_JSON,
        "markdown": DEFAULT_OUTPUT_DIR / REPORT_MD,
    }


def refuse_overwrite(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite C5 H1/H2 probe reports without --force: {names}")


def compact_baseline(report: dict[str, Any]) -> dict[str, Any]:
    graph = report["graph_metrics"]
    allocation = report["allocation_metrics"]
    return {
        "unique_triples": graph["unique_triples"],
        "unique_entities": graph["unique_entities"],
        "unique_relations": graph["unique_relations"],
        "weak_component_count": graph["weak_component_count"],
        "largest_weak_component_ratio": graph["largest_weak_component_ratio"],
        "duplicate_triple_count": graph["duplicate_triple_count"],
        "allocated_relations_observed": allocation["allocated_relations_observed"],
        "zero_allocated_relations": allocation["zero_allocated_relations"],
        "total_surplus": allocation["total_surplus"],
        "total_deficit": allocation["total_deficit"],
        "pattern_level_expected_observed": allocation["pattern_level_expected_observed"],
    }


def pattern_priority_order(baseline_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = baseline_report["allocation_metrics"]["pattern_level_expected_observed"]
    return sorted(
        (
            {
                "pattern": row["pattern"],
                "expected_eta": row["expected_eta"],
                "observed_count_apportioned": row["observed_count_apportioned"],
                "deficit": row["deficit"],
                "surplus": row["surplus"],
            }
            for row in rows
        ),
        key=lambda row: (-float(row["deficit"]), row["pattern"]),
    )


def pattern_delta_for_relation(allocation: dict[str, Any], relation: str, count_delta: int) -> dict[str, float]:
    rows = allocation["relation_patterns"].get(relation, [])
    row_eta_total = sum(float(row["eta"]) for row in rows)
    if not rows or row_eta_total <= 0:
        return {}
    deltas: dict[str, float] = defaultdict(float)
    for row in rows:
        pattern = row.get("pattern")
        if pattern:
            deltas[str(pattern)] += count_delta * (float(row["eta"]) / row_eta_total)
    return dict(sorted(deltas.items()))


def combined_pattern_delta(
    allocation: dict[str, Any],
    target_relation: str,
    replacement_relation: str | None,
) -> dict[str, float]:
    out: Counter[str] = Counter()
    out.update(pattern_delta_for_relation(allocation, target_relation, -1))
    if replacement_relation is not None and replacement_relation in allocation["relation_expected"]:
        out.update(pattern_delta_for_relation(allocation, replacement_relation, 1))
    return {pattern: value for pattern, value in sorted(out.items()) if value != 0}


def target_key(edge: dict[str, str]) -> tuple[str, str, str]:
    return edge["h"], edge["r"], edge["t"]


def candidate_key(edge: dict[str, str]) -> tuple[str, str, str]:
    return edge["h"], edge["r"], edge["t"]


def collect_cut_crossing_pairs(
    cuts: list[dict[str, Any]],
    cut_index: dict[str, set[int]],
    graph_triples: set[Triple],
    entities: set[str],
    max_candidates: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sources = candidate_sources()
    pairs: list[dict[str, Any]] = []
    source_stats: dict[str, Counter[str]] = defaultdict(Counter)
    stopped_after_limit = False

    for source in sources:
        source_id = source["source_id"]
        for path in source["paths"]:
            if not path.is_file():
                source_stats[source_id]["missing_files"] += 1
                continue
            source_stats[source_id]["files_scanned"] += 1
            source_stats[source_id]["bytes_scanned"] += path.stat().st_size
            for line_number, triple, row in iter_jsonl_triples(path):
                source_stats[source_id]["rows_scanned"] += 1
                if triple is None:
                    source_stats[source_id]["rows_without_parseable_triple"] += 1
                    continue
                source_stats[source_id]["triples_parsed"] += 1
                h, r, t = triple
                if h not in entities or t not in entities:
                    if h in entities or t in entities:
                        source_stats[source_id]["endpoint_inside_b0_one"] += 1
                    else:
                        source_stats[source_id]["endpoint_inside_b0_none"] += 1
                    continue
                source_stats[source_id]["endpoint_inside_b0_both"] += 1
                if triple in graph_triples:
                    source_stats[source_id]["already_in_b0"] += 1
                    continue
                crossing_cut_ids = cut_index.get(h, set()) ^ cut_index.get(t, set())
                if not crossing_cut_ids:
                    source_stats[source_id]["both_endpoints_in_b0_but_no_tested_cut_crossing"] += 1
                    continue
                for cut_id in sorted(crossing_cut_ids):
                    cut = cuts[cut_id]
                    pairs.append(
                        {
                            "source_id": source_id,
                            "source_path": repo_relative(path),
                            "line_number": line_number,
                            "candidate": {"h": h, "r": r, "t": t},
                            "cut_id": cut_id,
                            "target_edge": cut["target_edge"],
                            "smaller_side_size": cut["smaller_side_size"],
                            "larger_side_size": cut["larger_side_size"],
                            "source_metadata": row_source_metadata(row),
                        }
                    )
                    source_stats[source_id]["cut_crossing_candidate_pairs"] += 1
                    if len(pairs) >= max_candidates:
                        stopped_after_limit = True
                        break
                if stopped_after_limit:
                    break
            if stopped_after_limit:
                break
        if stopped_after_limit:
            break
    return pairs, {
        "stopped_after_max_candidates": stopped_after_limit,
        "source_stats": {source_id: dict(sorted(stats.items())) for source_id, stats in sorted(source_stats.items())},
    }


def hard_constraint_summary(
    relation_counts: Counter[str],
    target_relation: str,
    replacement_relation: str | None,
    relation_expected: dict[str, float],
    duplicate: bool,
    connected: bool,
) -> dict[str, Any]:
    counts = Counter(relation_counts)
    counts[target_relation] -= 1
    if replacement_relation is not None and replacement_relation in relation_expected:
        counts[replacement_relation] += 1
    allocated_relations_observed = sum(1 for relation in relation_expected if counts.get(relation, 0) > 0)
    zero_allocated_relations = sum(1 for relation in relation_expected if counts.get(relation, 0) <= 0)
    return {
        "weak_component_count": 1 if connected else 2,
        "duplicate_triple_count": 1 if duplicate else 0,
        "allocated_relations_observed": allocated_relations_observed,
        "zero_allocated_relations": zero_allocated_relations,
        "passes": (
            connected
            and not duplicate
            and allocated_relations_observed == len(relation_expected)
            and zero_allocated_relations == 0
        ),
    }


def classify_h1(
    pair: dict[str, Any],
    graph_triples: set[Triple],
    relation_counts: Counter[str],
    relation_expected: dict[str, float],
    allocation: dict[str, Any],
) -> dict[str, Any]:
    target = pair["target_edge"]
    candidate = pair["candidate"]
    duplicate = candidate_key(candidate) in graph_triples
    delta = relation_delta(relation_counts, relation_expected, target["r"], candidate["r"])
    constraints = hard_constraint_summary(
        relation_counts,
        target["r"],
        candidate["r"],
        relation_expected,
        duplicate,
        connected=True,
    )
    pattern_delta = combined_pattern_delta(allocation, target["r"], candidate["r"])
    if not constraints["passes"]:
        status = "rejected_h1_breaks_constraints"
    elif delta["surplus_delta"] < 0 and delta["deficit_delta"] <= 0:
        status = "feasible_h1_balance_improving"
    elif delta["surplus_delta"] <= 0 and delta["deficit_delta"] <= 0:
        status = "feasible_h1_connectivity_only"
    else:
        status = "rejected_h1_balance_worse"
    return {
        **pair,
        "hypothesis": "H1",
        "edge_provenance": "canonical_allocated_observed",
        "operation": "remove_replace",
        "classification": status,
        "total_surplus_delta": delta["surplus_delta"],
        "total_deficit_delta": delta["deficit_delta"],
        "pattern_total_delta": pattern_delta,
        "target_relation_observed_delta": -1,
        "replacement_relation_observed_delta": 1,
        "hard_constraints": constraints,
        "balance_effect": delta,
    }


def classify_h2(
    pair: dict[str, Any],
    graph_triples: set[Triple],
    relation_counts: Counter[str],
    relation_expected: dict[str, float],
    allocation: dict[str, Any],
    baseline_unique_triples: int,
) -> dict[str, Any]:
    target = pair["target_edge"]
    candidate = pair["candidate"]
    duplicate = candidate_key(candidate) in graph_triples
    delta = relation_delta(relation_counts, relation_expected, target["r"], None)
    constraints = hard_constraint_summary(
        relation_counts,
        target["r"],
        None,
        relation_expected,
        duplicate,
        connected=True,
    )
    pattern_delta = combined_pattern_delta(allocation, target["r"], None)
    if not constraints["passes"]:
        status = "rejected_h2_breaks_constraints"
    elif constraints["weak_component_count"] != 1:
        status = "rejected_h2_no_connectivity_gain"
    elif delta["surplus_delta"] < 0 and delta["deficit_delta"] <= 0:
        status = "feasible_h2_auxiliary_enables_prune"
    elif delta["surplus_delta"] == 0 and delta["deficit_delta"] == 0:
        status = "feasible_h2_connectivity_only_but_balance_neutral"
    else:
        status = "rejected_h2_breaks_constraints"
    return {
        **pair,
        "hypothesis": "H2",
        "edge_provenance": "auxiliary_unallocated_observed",
        "edge_role": "auxiliary_connectivity_verified",
        "operation": "auxiliary_add_then_prune",
        "classification": status,
        "auxiliary_edges_used": 1,
        "canonical_triples_after_prune": baseline_unique_triples - 1,
        "full_triples_after_auxiliary": baseline_unique_triples + 1,
        "full_triples_after_auxiliary_and_prune": baseline_unique_triples,
        "canonical_surplus_delta": delta["surplus_delta"],
        "canonical_deficit_delta": delta["deficit_delta"],
        "pattern_total_delta": pattern_delta,
        "connectivity_with_auxiliary": 1,
        "connectivity_without_auxiliary": 2,
        "hard_constraints": constraints,
        "balance_effect": delta,
    }


def sort_move(move: dict[str, Any]) -> tuple[Any, ...]:
    return (
        move.get("total_surplus_delta", move.get("canonical_surplus_delta", 0.0)),
        move.get("total_deficit_delta", move.get("canonical_deficit_delta", 0.0)),
        move["cut_id"],
        move["candidate"]["r"],
        move["candidate"]["h"],
        move["candidate"]["t"],
    )


def greedy_non_reuse(moves: list[dict[str, Any]]) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    used_targets: set[tuple[str, str, str]] = set()
    used_candidates: set[tuple[str, str, str]] = set()
    surplus_delta = 0.0
    deficit_delta = 0.0
    for move in sorted(moves, key=sort_move):
        t_key = target_key(move["target_edge"])
        c_key = candidate_key(move["candidate"])
        if t_key in used_targets or c_key in used_candidates:
            continue
        used_targets.add(t_key)
        used_candidates.add(c_key)
        selected.append(move)
        surplus_delta += float(move.get("total_surplus_delta", move.get("canonical_surplus_delta", 0.0)))
        deficit_delta += float(move.get("total_deficit_delta", move.get("canonical_deficit_delta", 0.0)))
    return {
        "count": len(selected),
        "aggregate_surplus_delta": surplus_delta,
        "aggregate_deficit_delta": deficit_delta,
        "examples": selected[:20],
    }


def summarize(classified: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
    counts = Counter(row["classification"] for row in classified)
    feasible = [row for row in classified if row["classification"].startswith(f"feasible_{prefix.lower()}")]
    return {
        "candidate_cut_pairs_tested": len(classified),
        "classification_counts": dict(sorted(counts.items())),
        "feasible_count": len(feasible),
        "best_examples": sorted(feasible, key=sort_move)[:20],
    }


def run_probe(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    config_path = resolve_path(args.config)
    config = load_c5_config(config_path)
    parent_graph = resolve_path(config["parent_graph_path"])
    allocation_path = resolve_path(config["allocation_path"])
    c4_2_path = resolve_path(config["source_evidence"]["c4_2_local_cut_crossing_search"])
    c4_3_path = resolve_path("docs/reconstruction/56_C4_branch_decision_audit.md")
    if not c4_2_path.is_file():
        raise FileNotFoundError(c4_2_path)
    if not c4_3_path.is_file():
        raise FileNotFoundError(c4_3_path)

    baseline_report = evaluate_candidate(parent_graph, allocation_path, config["parent_candidate_id"], "B0")
    baseline_metrics = compact_baseline(baseline_report)
    allocation = load_allocation(allocation_path)
    relation_expected = allocation["relation_expected"]
    graph_triples = set(load_graph_triples(parent_graph))
    entities = {node for h, _r, t in graph_triples for node in (h, t)}
    relation_counts = Counter(r for _h, r, _t in graph_triples)
    target_relations = set(["P31", "P279", "P131"])
    cuts, cut_index = prepare_tested_cuts(
        graph_triples,
        entities,
        relation_counts,
        relation_expected,
        target_relations,
        args.max_cuts,
    )
    pairs, scan_metadata = collect_cut_crossing_pairs(
        cuts,
        cut_index,
        graph_triples,
        entities,
        args.max_candidates,
    )

    h1_pairs = [pair for pair in pairs if pair["candidate"]["r"] in relation_expected]
    h2_pairs = [pair for pair in pairs if pair["candidate"]["r"] not in relation_expected]
    h1_classified = [
        classify_h1(pair, graph_triples, relation_counts, relation_expected, allocation) for pair in h1_pairs
    ]
    h2_classified = [
        classify_h2(pair, graph_triples, relation_counts, relation_expected, allocation, baseline_metrics["unique_triples"])
        for pair in h2_pairs
    ]

    h1_feasible = [row for row in h1_classified if row["classification"].startswith("feasible_h1")]
    h2_feasible = [row for row in h2_classified if row["classification"].startswith("feasible_h2")]
    h1_balance = [row for row in h1_classified if row["classification"] == "feasible_h1_balance_improving"]
    h2_balance = [row for row in h2_classified if row["classification"] == "feasible_h2_auxiliary_enables_prune"]
    rejection_reasons = {
        "H1": dict(Counter(row["classification"] for row in h1_classified if row not in h1_feasible)),
        "H2": dict(Counter(row["classification"] for row in h2_classified if row not in h2_feasible)),
    }
    finished = time.time()
    return {
        "schema_version": "c5-h1-h2-probe-report-v1",
        "candidate_id": config["candidate_id"],
        "parent_candidate_id": config["parent_candidate_id"],
        "status": "probe_only_no_graph_generated",
        "inputs": {
            "config": {"path": repo_relative(config_path), "sha256": sha256_file(config_path)},
            "parent_graph": {"path": config["parent_graph_path"], "sha256": sha256_file(parent_graph)},
            "allocation": {"path": config["allocation_path"], "sha256": sha256_file(allocation_path)},
            "c4_2_local_cut_crossing_search": {
                "path": repo_relative(c4_2_path),
                "sha256": sha256_file(c4_2_path),
            },
            "c4_3_decision_audit": {"path": repo_relative(c4_3_path), "sha256": sha256_file(c4_3_path)},
        },
        "limits": {"max_cuts": args.max_cuts, "max_candidates": args.max_candidates},
        "baseline_metrics": baseline_metrics,
        "pattern_priority_order": pattern_priority_order(baseline_report),
        "cut_context": {
            "cuts_loaded": len(cuts),
            "cut_index_entities": len(cut_index),
            "candidate_cut_pairs_loaded": len(pairs),
            "h1_candidate_cut_pairs": len(h1_pairs),
            "h2_candidate_cut_pairs": len(h2_pairs),
        },
        "candidate_scan_metadata": scan_metadata,
        "h1_summary": {
            **summarize(h1_classified, "H1"),
            "strict_allocated_replacements_found": len(h1_pairs),
            "balance_improving_count": len(h1_balance),
        },
        "h2_summary": {
            **summarize(h2_classified, "H2"),
            "auxiliary_unallocated_pairs_found": len(h2_pairs),
            "auxiliary_enables_prune_count": len(h2_balance),
        },
        "greedy_h1_upper_bound": greedy_non_reuse(h1_balance),
        "greedy_h2_upper_bound": greedy_non_reuse(h2_balance),
        "rejection_reasons": rejection_reasons,
        "top_examples": {
            "h1": sorted(h1_classified, key=sort_move)[:20],
            "h2": sorted(h2_classified, key=sort_move)[:20],
        },
        "generator_recommendation": generator_recommendation(len(h1_balance), len(h2_balance)),
        "notes": [
            "Probe-only report; no graph candidate was generated.",
            "No WDQS query was made.",
            "No LLM call was made.",
            "No synthetic triples were created.",
            "candidate_registry.v1.json was not updated.",
            "H2 auxiliary unallocated edges are accounted separately from canonical allocated triples.",
        ],
        "runtime": {
            "started_on": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "finished_on": datetime.fromtimestamp(finished, timezone.utc).isoformat(),
            "elapsed_seconds": round(finished - started, 6),
        },
    }


def generator_recommendation(h1_balance_count: int, h2_balance_count: int) -> dict[str, Any]:
    if h1_balance_count:
        decision = "strict_h1_generator_may_be_worth_designing_after_human_review"
    elif h2_balance_count:
        decision = "h2_auxiliary_probe_supports_designing_a_constrained_auxiliary_branch"
    else:
        decision = "no_c5_generator_justified_from_h1_h2_probe"
    return {
        "decision": decision,
        "strict_h1_graph_generator_justified": h1_balance_count > 0,
        "h2_auxiliary_generator_justified": h2_balance_count > 0,
        "requires_human_decision_before_graph_generation": True,
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    h1 = report["h1_summary"]
    h2 = report["h2_summary"]
    greedy_h1 = report["greedy_h1_upper_bound"]
    greedy_h2 = report["greedy_h2_upper_bound"]
    lines = [
        "# C5 H1/H2 Connectivity-Support Probe",
        "",
        "Status: probe only. No graph candidate was generated.",
        "",
        "## Pattern Priority",
        "",
        "| Pattern | Deficit | Surplus | Observed | Expected |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in report["pattern_priority_order"]:
        lines.append(
            f"| `{row['pattern']}` | {row['deficit']} | {row['surplus']} | "
            f"{row['observed_count_apportioned']} | {row['expected_eta']} |"
        )
    lines.extend(
        [
            "",
            "## H1: Canonical Allocated Observed Replacement",
            "",
            "H1 tests whether observed, allocated cut-crossing replacements can replace target-generic bridge edges while preserving hard constraints.",
            "",
            f"- Candidate-cut pairs tested: `{h1['candidate_cut_pairs_tested']}`",
            f"- Feasible H1 moves: `{h1['feasible_count']}`",
            f"- Balance-improving H1 moves: `{h1['balance_improving_count']}`",
            f"- Greedy H1 upper-bound count: `{greedy_h1['count']}`",
            f"- Greedy H1 surplus delta: `{greedy_h1['aggregate_surplus_delta']}`",
            f"- Greedy H1 deficit delta: `{greedy_h1['aggregate_deficit_delta']}`",
            "",
            "## H2: Auxiliary Unallocated Observed Support",
            "",
            "H2 tests whether observed unallocated cut-crossing edges can be added as auxiliary connectivity support, enabling later pruning of surplus generic bridge edges.",
            "",
            f"- Candidate-cut pairs tested: `{h2['candidate_cut_pairs_tested']}`",
            f"- Feasible H2 moves: `{h2['feasible_count']}`",
            f"- Auxiliary enables-prune moves: `{h2['auxiliary_enables_prune_count']}`",
            f"- Greedy H2 upper-bound count: `{greedy_h2['count']}`",
            f"- Greedy H2 surplus delta: `{greedy_h2['aggregate_surplus_delta']}`",
            f"- Greedy H2 deficit delta: `{greedy_h2['aggregate_deficit_delta']}`",
            "",
            "## Generator Decision",
            "",
            f"Recommendation: `{report['generator_recommendation']['decision']}`.",
            "",
            "A strict H1 replacement generator is justified only if allocated, balance-improving moves exist. "
            "An H2 branch, if pursued, must keep auxiliary unallocated edges separate from canonical allocation accounting "
            "and must receive human approval before any graph generation.",
            "",
            "## Notes",
            "",
            "- No WDQS query was made.",
            "- No LLM call was made.",
            "- No synthetic triples were created.",
            "- `outputs/graph.jsonl` was not written.",
            "- `candidate_registry.v1.json` was not updated.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    config = load_c5_config(resolve_path(args.config))
    paths = output_paths()
    if args.dry_run:
        print("dry_run=true")
        print(f"candidate_id={config['candidate_id']}")
        print(f"parent_graph={config['parent_graph_path']}")
        print(f"allocation={config['allocation_path']}")
        print(f"output_json={paths['json']}")
        print(f"output_markdown={paths['markdown']}")
        print("no_reports_written=true")
        return 0
    refuse_overwrite(paths, args.force)
    report = run_probe(args)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(paths["markdown"], report)
    print(f"probe_json={paths['json']}")
    print(f"probe_markdown={paths['markdown']}")
    print(f"pattern_priority_order={[row['pattern'] for row in report['pattern_priority_order']]}")
    print(f"h1_feasible_count={report['h1_summary']['feasible_count']}")
    print(f"h2_feasible_count={report['h2_summary']['feasible_count']}")
    print(f"greedy_h1_upper_bound={report['greedy_h1_upper_bound']['count']}")
    print(f"greedy_h2_upper_bound={report['greedy_h2_upper_bound']['count']}")
    print(f"generator_recommendation={report['generator_recommendation']['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
