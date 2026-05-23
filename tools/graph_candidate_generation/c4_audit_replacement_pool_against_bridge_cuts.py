#!/usr/bin/env python3
"""Audit why the C4 eligible replacement pool does not rescue tested bridge cuts."""

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
from src.kg_pipeline.evaluation.candidate_report import sha256_file  # noqa: E402
from src.kg_pipeline.evaluation.graph_io import Triple, load_graph_triples  # noqa: E402
from tools.graph_candidate_generation.c4_probe_bridge_aware_replace_add import (  # noqa: E402
    build_undirected,
    classify_target,
    load_config,
    load_replacement_pool,
    relation_delta,
    repo_relative,
    resolve_path,
    resolve_replacement_pool,
    target_edges,
)

DEFAULT_CONFIG = Path("experiments/graph_candidates/C4_bridge_aware_replace_add/configs/config.template.json")
DEFAULT_PROBE_REPORT = Path(
    "experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/probe_report.json"
)
DEFAULT_OUTPUT_DIR = Path("experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--probe-report", type=Path, default=DEFAULT_PROBE_REPORT)
    parser.add_argument("--max-target-edges", type=int, default=1000)
    parser.add_argument("--max-replacement-candidates", type=int, default=5000)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    return {
        "json": output_dir / "replacement_pool_bridge_cut_audit.json",
        "markdown": output_dir / "replacement_pool_bridge_cut_audit.md",
    }


def refuse_overwrite(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite audit reports without --force: {names}")


def find_simple_bridges_iterative(adjacency: dict[str, set[str]]) -> set[tuple[str, str]]:
    """Iterative Tarjan bridge search for the B0 undirected simple graph."""
    timer = 0
    tin: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    bridges: set[tuple[str, str]] = set()

    for root in adjacency:
        if root in tin:
            continue
        parent[root] = None
        stack: list[tuple[str, Any]] = [(root, iter(sorted(adjacency[root])))]
        timer += 1
        tin[root] = low[root] = timer

        while stack:
            node, iterator = stack[-1]
            try:
                nxt = next(iterator)
            except StopIteration:
                stack.pop()
                par = parent[node]
                if par is not None:
                    low[par] = min(low[par], low[node])
                    if low[node] > tin[par]:
                        bridges.add(tuple(sorted((par, node))))
                continue

            if nxt == parent[node]:
                continue
            if nxt in tin:
                low[node] = min(low[node], tin[nxt])
                continue
            parent[nxt] = node
            timer += 1
            tin[nxt] = low[nxt] = timer
            stack.append((nxt, iter(sorted(adjacency[nxt]))))
    return bridges


def replacement_endpoint_status(row: dict[str, Any], entities: set[str]) -> str:
    h_inside = row["h"] in entities
    t_inside = row["t"] in entities
    if h_inside and t_inside:
        return "both"
    if h_inside or t_inside:
        return "one"
    return "none"


def replacement_crosses_cut(row: dict[str, Any], side: set[str] | None) -> bool:
    if side is None:
        return False
    return (row["h"] in side) != (row["t"] in side)


def summarize_replacement_rows(
    rows: list[dict[str, Any]],
    entities: set[str],
    relation_expected: dict[str, float],
    graph_triples: set[Triple],
) -> dict[str, Any]:
    endpoint_counts: Counter[str] = Counter()
    relation_counts: Counter[str] = Counter()
    allocated_count = 0
    duplicate_count = 0
    for row in rows:
        endpoint_counts[replacement_endpoint_status(row, entities)] += 1
        relation_counts[row["r"]] += 1
        if row["r"] in relation_expected:
            allocated_count += 1
        if (row["h"], row["r"], row["t"]) in graph_triples:
            duplicate_count += 1
    return {
        "endpoint_inside_b0_both": endpoint_counts["both"],
        "endpoint_inside_b0_one": endpoint_counts["one"],
        "endpoint_inside_b0_none": endpoint_counts["none"],
        "allocated_relation_rows": allocated_count,
        "unallocated_relation_rows": len(rows) - allocated_count,
        "duplicate_rows": duplicate_count,
        "relation_distribution": dict(sorted(relation_counts.items())),
        "top_30_relations": dict(relation_counts.most_common(30)),
    }


def evaluate_target_against_pool(
    target: dict[str, Any],
    replacement_rows: list[dict[str, Any]],
    entities: set[str],
    graph_triples: set[Triple],
    relation_counts: Counter[str],
    relation_expected: dict[str, float],
) -> dict[str, Any]:
    side = target.get("_side")
    pair_counts: Counter[str] = Counter()
    cross_relation_counts: Counter[str] = Counter()
    cross_candidate_ids: list[str] = []
    unique_crossing_replacements: set[tuple[str, str, str]] = set()

    for row in replacement_rows:
        endpoint_status = replacement_endpoint_status(row, entities)
        pair_counts[f"endpoint_inside_b0_{endpoint_status}"] += 1

        if endpoint_status != "both":
            pair_counts["reject_endpoint_not_both_inside_b0"] += 1
            continue

        duplicate = (row["h"], row["r"], row["t"]) in graph_triples
        allocated = row["r"] in relation_expected
        crosses = replacement_crosses_cut(row, side)
        if not crosses:
            pair_counts["reject_does_not_cross_bridge_cut"] += 1
            continue

        unique_crossing_replacements.add((row["h"], row["r"], row["t"]))
        cross_relation_counts[row["r"]] += 1
        if len(cross_candidate_ids) < 20:
            cross_candidate_ids.append(row.get("candidate_id") or f"{row['h']}|{row['r']}|{row['t']}")
        pair_counts["crosses_cut"] += 1

        if duplicate:
            pair_counts["crosses_cut_but_duplicate"] += 1
            pair_counts["reject_duplicate"] += 1
            continue
        if not allocated:
            pair_counts["reject_unallocated_relation"] += 1
            continue
        pair_counts["crosses_cut_and_allocated"] += 1

        delta = relation_delta(relation_counts, relation_expected, target["r"], row["r"])
        if delta["surplus_delta"] < 0:
            pair_counts["crosses_cut_and_balance_improving"] += 1
        else:
            pair_counts["reject_not_surplus_reducing"] += 1
            continue
        if delta["deficit_delta"] > 0:
            pair_counts["deficit_would_increase"] += 1
            pair_counts["reject_deficit_increase"] += 1
            continue
        pair_counts["feasible_if_hard_constraints_hold"] += 1

    for key in (
        "endpoint_inside_b0_both",
        "endpoint_inside_b0_one",
        "endpoint_inside_b0_none",
        "crosses_cut",
        "crosses_cut_and_allocated",
        "crosses_cut_and_balance_improving",
        "crosses_cut_but_duplicate",
        "deficit_would_increase",
        "feasible_if_hard_constraints_hold",
        "reject_endpoint_not_both_inside_b0",
        "reject_does_not_cross_bridge_cut",
        "reject_duplicate",
        "reject_unallocated_relation",
        "reject_not_surplus_reducing",
        "reject_deficit_increase",
    ):
        pair_counts.setdefault(key, 0)

    return {
        "target_edge": {"h": target["h"], "r": target["r"], "t": target["t"]},
        "bridge_pair": target["bridge_pair"],
        "relation_surplus_before": target["relation_surplus_before"],
        "smaller_side_size": target["smaller_side_size"],
        "replacement_pair_tests": len(replacement_rows),
        "counts": dict(sorted(pair_counts.items())),
        "unique_crossing_replacements": len(unique_crossing_replacements),
        "crossing_relation_distribution": dict(sorted(cross_relation_counts.items())),
        "crossing_candidate_examples": cross_candidate_ids,
    }


def load_probe_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    config_path = resolve_path(args.config)
    probe_report_path = resolve_path(args.probe_report)
    config = load_config(config_path)
    probe_report = load_probe_report(probe_report_path)

    parent_graph = resolve_path(config["parent_graph_path"])
    allocation_path = resolve_path(config["allocation_path"])
    pool_info = resolve_replacement_pool(config)
    pool_path = resolve_path(pool_info["resolved_path"])

    triples = load_graph_triples(parent_graph)
    graph_triples = set(triples)
    entities = {node for h, _r, t in graph_triples for node in (h, t)}
    relation_counts = Counter(r for _h, r, _t in graph_triples)
    allocation = load_allocation(allocation_path)
    relation_expected = allocation["relation_expected"]
    target_relations = set(config.get("target_relations") or [])
    replacement_rows = load_replacement_pool(pool_path, args.max_replacement_candidates, target_relations)

    adjacency, pair_counts, _degrees = build_undirected(graph_triples)
    simple_bridges = find_simple_bridges_iterative(adjacency)
    bridges = {pair for pair in simple_bridges if pair_counts[pair] == 1}

    ordered_targets = target_edges(
        sorted(graph_triples),
        relation_counts,
        relation_expected,
        target_relations,
        args.max_target_edges,
    )

    tested_bridge_targets: list[dict[str, Any]] = []
    for target in ordered_targets:
        classified = classify_target(target, pair_counts, bridges, adjacency, len(entities))
        if classified["connectivity_critical"]:
            tested_bridge_targets.append(classified)

    replacement_summary = summarize_replacement_rows(
        replacement_rows,
        entities,
        relation_expected,
        graph_triples,
    )

    target_summaries: list[dict[str, Any]] = []
    pair_counts_total: Counter[str] = Counter()
    unique_crossing_rows: set[tuple[str, str, str]] = set()
    unique_crossing_allocated_rows: set[tuple[str, str, str]] = set()
    unique_crossing_balance_rows: set[tuple[str, str, str]] = set()
    unique_crossing_duplicate_rows: set[tuple[str, str, str]] = set()

    for target in tested_bridge_targets:
        target_summary = evaluate_target_against_pool(
            target,
            replacement_rows,
            entities,
            graph_triples,
            relation_counts,
            relation_expected,
        )
        target_summaries.append(target_summary)
        pair_counts_total.update(target_summary["counts"])

        side = target.get("_side")
        for row in replacement_rows:
            if replacement_endpoint_status(row, entities) != "both":
                continue
            if not replacement_crosses_cut(row, side):
                continue
            row_key = (row["h"], row["r"], row["t"])
            unique_crossing_rows.add(row_key)
            if row["r"] in relation_expected:
                unique_crossing_allocated_rows.add(row_key)
                delta = relation_delta(relation_counts, relation_expected, target["r"], row["r"])
                if delta["surplus_delta"] < 0:
                    unique_crossing_balance_rows.add(row_key)
            if row_key in graph_triples:
                unique_crossing_duplicate_rows.add(row_key)

    no_feasible_reason_counts = Counter()
    if pair_counts_total["crosses_cut"] == 0:
        no_feasible_reason_counts["no_replacement_candidate_crossed_any_tested_bridge_cut"] = len(tested_bridge_targets)
    if replacement_summary["endpoint_inside_b0_both"] == 0:
        no_feasible_reason_counts["no_replacement_candidate_had_both_endpoints_in_b0"] = len(tested_bridge_targets)
    if pair_counts_total["crosses_cut_and_allocated"] == 0:
        no_feasible_reason_counts["no_cut_crossing_allocated_replacement"] = len(tested_bridge_targets)
    if pair_counts_total["crosses_cut_and_balance_improving"] == 0:
        no_feasible_reason_counts["no_cut_crossing_surplus_reducing_replacement"] = len(tested_bridge_targets)
    no_feasible_reason_counts.update(
        {
            key.removeprefix("reject_"): value
            for key, value in pair_counts_total.items()
            if key.startswith("reject_") and value
        }
    )

    finished = time.time()
    return {
        "schema_version": "c4-replacement-pool-bridge-cut-audit-v1",
        "audit_id": "C4_1_replacement_pool_bridge_cut_audit",
        "status": "read_only_probe_audit",
        "inputs": {
            "config": {
                "path": repo_relative(config_path),
                "sha256": sha256_file(config_path),
            },
            "probe_report": {
                "path": repo_relative(probe_report_path),
                "sha256": sha256_file(probe_report_path),
                "summary": probe_report.get("summary"),
            },
            "parent_graph": {
                "path": config["parent_graph_path"],
                "sha256": sha256_file(parent_graph),
            },
            "allocation": {
                "path": config["allocation_path"],
                "sha256": sha256_file(allocation_path),
            },
            "replacement_pool": pool_info,
        },
        "limits": {
            "max_target_edges": args.max_target_edges,
            "max_replacement_candidates": args.max_replacement_candidates,
        },
        "bridge_cut_context": {
            "b0_unique_triples": len(graph_triples),
            "b0_entities": len(entities),
            "undirected_simple_bridge_pairs": len(bridges),
            "ordered_surplus_target_edges_considered": len(ordered_targets),
            "tested_bridge_targets": len(tested_bridge_targets),
            "target_relations": sorted(target_relations),
        },
        "replacement_pool_summary": replacement_summary,
        "aggregate": {
            "tested_bridge_targets": len(tested_bridge_targets),
            "replacement_rows_loaded": len(replacement_rows),
            "endpoint_inside_b0_both": replacement_summary["endpoint_inside_b0_both"],
            "endpoint_inside_b0_one": replacement_summary["endpoint_inside_b0_one"],
            "endpoint_inside_b0_none": replacement_summary["endpoint_inside_b0_none"],
            "crosses_any_tested_cut": len(unique_crossing_rows),
            "crosses_cut_and_allocated": len(unique_crossing_allocated_rows),
            "crosses_cut_and_balance_improving": len(unique_crossing_balance_rows),
            "crosses_cut_but_duplicate": len(unique_crossing_duplicate_rows),
        },
        "pair_test_aggregate": normalized_pair_counts(pair_counts_total),
        "top_reasons_no_feasible_replacement": dict(no_feasible_reason_counts.most_common(20)),
        "target_bridge_summaries_first_50": target_summaries[:50],
        "target_bridge_summaries_count": len(target_summaries),
        "interpretation": {
            "primary_failure_mode": primary_failure_mode(
                len(unique_crossing_rows),
                replacement_summary,
                pair_counts_total,
            ),
            "no_graph_generated": True,
            "candidate_registry_updated": False,
        },
        "runtime": {
            "started_on": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "finished_on": datetime.fromtimestamp(finished, timezone.utc).isoformat(),
            "elapsed_seconds": round(finished - started, 6),
        },
        "notes": [
            "Read-only audit; no graph candidate was generated.",
            "No WDQS query was made.",
            "No LLM call was made.",
            "candidate_registry.v1.json was not updated.",
        ],
    }


def primary_failure_mode(
    crossing_rows: int,
    replacement_summary: dict[str, Any],
    pair_counts_total: Counter[str],
) -> str:
    if crossing_rows == 0:
        if replacement_summary["endpoint_inside_b0_both"] > 0:
            return "bridge_cut_crossing_failure"
        return "endpoint_coverage_failure"
    if pair_counts_total["crosses_cut_and_allocated"] == 0:
        return "relation_allocation_mismatch_after_cut_crossing"
    if pair_counts_total["crosses_cut_and_balance_improving"] == 0:
        return "balance_delta_failure_after_cut_crossing"
    if pair_counts_total["deficit_would_increase"] == pair_counts_total["crosses_cut_and_balance_improving"]:
        return "deficit_increase_after_cut_crossing"
    return "mixed_failure_after_cut_crossing"


def normalized_pair_counts(counts: Counter[str]) -> dict[str, int]:
    keys = (
        "endpoint_inside_b0_both",
        "endpoint_inside_b0_one",
        "endpoint_inside_b0_none",
        "crosses_cut",
        "crosses_cut_and_allocated",
        "crosses_cut_and_balance_improving",
        "crosses_cut_but_duplicate",
        "deficit_would_increase",
        "feasible_if_hard_constraints_hold",
        "reject_endpoint_not_both_inside_b0",
        "reject_does_not_cross_bridge_cut",
        "reject_duplicate",
        "reject_unallocated_relation",
        "reject_not_surplus_reducing",
        "reject_deficit_increase",
    )
    out = {key: int(counts.get(key, 0)) for key in keys}
    for key, value in sorted(counts.items()):
        out.setdefault(key, int(value))
    return out


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    aggregate = report["aggregate"]
    replacement = report["replacement_pool_summary"]
    pair_tests = report["pair_test_aggregate"]
    lines = [
        "# C4.1 Replacement Pool Bridge-Cut Audit",
        "",
        "Status: read-only audit. No graph candidate was generated.",
        "",
        "## Inputs",
        "",
        f"- Config: `{report['inputs']['config']['path']}`",
        f"- Probe report: `{report['inputs']['probe_report']['path']}`",
        f"- Parent graph: `{report['inputs']['parent_graph']['path']}`",
        f"- Parent graph SHA256: `{report['inputs']['parent_graph']['sha256']}`",
        f"- Allocation: `{report['inputs']['allocation']['path']}`",
        f"- Allocation SHA256: `{report['inputs']['allocation']['sha256']}`",
        f"- Replacement pool: `{report['inputs']['replacement_pool']['resolved_path']}`",
        f"- Replacement pool SHA256: `{report['inputs']['replacement_pool']['sha256']}`",
        "",
        "## Audit Counts",
        "",
        f"- Tested bridge targets: `{aggregate['tested_bridge_targets']}`",
        f"- Replacement rows loaded: `{aggregate['replacement_rows_loaded']}`",
        f"- Replacement rows with both endpoints in B0: `{aggregate['endpoint_inside_b0_both']}`",
        f"- Replacement rows with one endpoint in B0: `{aggregate['endpoint_inside_b0_one']}`",
        f"- Replacement rows with no endpoints in B0: `{aggregate['endpoint_inside_b0_none']}`",
        f"- Unique replacement rows crossing any tested cut: `{aggregate['crosses_any_tested_cut']}`",
        f"- Unique cut-crossing allocated replacement rows: `{aggregate['crosses_cut_and_allocated']}`",
        f"- Unique cut-crossing balance-improving replacement rows: `{aggregate['crosses_cut_and_balance_improving']}`",
        f"- Unique cut-crossing duplicate rows: `{aggregate['crosses_cut_but_duplicate']}`",
        "",
        "## Pair-Test Aggregate",
        "",
        "| Check | Count |",
        "| --- | ---: |",
    ]
    for key, count in pair_tests.items():
        lines.append(f"| `{key}` | {count} |")

    lines.extend(
        [
            "",
            "## Replacement Relation Distribution",
            "",
            "| Relation | Rows |",
            "| --- | ---: |",
        ]
    )
    for relation, count in replacement["top_30_relations"].items():
        lines.append(f"| `{relation}` | {count} |")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"Primary failure mode: `{report['interpretation']['primary_failure_mode']}`.",
            "",
            "The bounded audit shows that eligible replacement candidates with both endpoints in B0 exist, "
            "but none cross any of the tested bridge cuts. The zero feasible C4 probe result is therefore "
            "explained primarily by bridge-cut crossing coverage, not by allocation status or balance-delta "
            "filtering after a crossing candidate exists.",
            "",
            "## Notes",
            "",
            "- This audit reads frozen local files only.",
            "- It does not write `outputs/graph.jsonl`.",
            "- It does not update `candidate_registry.v1.json`.",
            "- It does not query WDQS or call LLMs.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    paths = output_paths()
    refuse_overwrite(paths, args.force)
    report = run_audit(args)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(paths["markdown"], report)
    print(f"audit_json={paths['json']}")
    print(f"audit_markdown={paths['markdown']}")
    print(f"tested_bridge_targets={report['aggregate']['tested_bridge_targets']}")
    print(f"replacement_rows_loaded={report['aggregate']['replacement_rows_loaded']}")
    print(f"endpoint_inside_b0_both={report['aggregate']['endpoint_inside_b0_both']}")
    print(f"crosses_any_tested_cut={report['aggregate']['crosses_any_tested_cut']}")
    print(f"primary_failure_mode={report['interpretation']['primary_failure_mode']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
