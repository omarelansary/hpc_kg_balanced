#!/usr/bin/env python3
"""Probe C4 bridge-aware replace/add feasibility without writing a graph."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.allocation_metrics import load_allocation  # noqa: E402
from src.kg_pipeline.evaluation.candidate_report import evaluate_candidate, sha256_file  # noqa: E402
from src.kg_pipeline.evaluation.graph_io import Triple, load_graph_triples  # noqa: E402

DEFAULT_OUTPUT_DIR = Path("experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only")
REPLACEMENT_POOL_MISSING_MESSAGE = (
    "replacement pool missing; restore optional C3 replacement pool artifact or run a no-pool "
    "diagnostic mode if implemented"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--max-target-edges", type=int, default=1000)
    parser.add_argument("--max-replacement-candidates", type=int, default=5000)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def resolve_path(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return REPO_ROOT / p


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "kg-candidate-generation-config-v1":
        raise ValueError(f"Unexpected config schema_version: {config.get('schema_version')!r}")
    if config.get("allowed_live_sources") is not False:
        raise ValueError("C4 probe requires allowed_live_sources=false")
    if config.get("allowed_wdqs") is not False:
        raise ValueError("C4 probe requires allowed_wdqs=false")
    if config.get("allowed_llm") is not False:
        raise ValueError("C4 probe requires allowed_llm=false")
    return config


def output_paths(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    return {
        "probe_report": output_dir / "probe_report.json",
        "probe_summary": output_dir / "probe_summary.md",
    }


def refuse_overwrite(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite probe reports without --force: {names}")


def resolve_replacement_pool(config: dict[str, Any]) -> dict[str, Any]:
    sources = config.get("replacement_sources") or []
    configured = None
    if sources and isinstance(sources[0], dict):
        configured = sources[0].get("path")
    if not configured:
        raise FileNotFoundError(REPLACEMENT_POOL_MISSING_MESSAGE)

    configured_path = resolve_path(configured)
    candidates = [configured_path]
    if configured_path.name == "eligible_replacement_candidates.jsonl":
        candidates.append(configured_path.parent / "eligible_v1" / configured_path.name)

    for candidate in candidates:
        if candidate.is_file():
            return {
                "configured_path": str(configured),
                "resolved_path": repo_relative(candidate),
                "sha256": sha256_file(candidate),
                "resolution_note": (
                    "used configured path"
                    if candidate == configured_path
                    else "configured path missing; used restored eligible_v1 pool path"
                ),
            }
    raise FileNotFoundError(REPLACEMENT_POOL_MISSING_MESSAGE)


def load_replacement_pool(path: Path, limit: int, target_relations: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"replacement pool row is not an object at line {line_number}")
            if not all(isinstance(row.get(key), str) and row.get(key) for key in ("h", "r", "t")):
                raise ValueError(f"replacement pool row missing h/r/t at line {line_number}")
            if row.get("r") in target_relations:
                row = {**row, "c4_warning": "target_generic_replacement_candidate"}
            rows.append(row)
            if len(rows) >= limit:
                break
    return rows


def build_undirected(triples: Iterable[Triple]) -> tuple[dict[str, set[str]], Counter[tuple[str, str]], Counter[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    pair_counts: Counter[tuple[str, str]] = Counter()
    degrees: Counter[str] = Counter()
    for h, _r, t in triples:
        if h == t:
            degrees[h] += 2
            adjacency.setdefault(h, set())
            continue
        pair = tuple(sorted((h, t)))
        pair_counts[pair] += 1
        adjacency[h].add(t)
        adjacency[t].add(h)
        degrees[h] += 1
        degrees[t] += 1
    return adjacency, pair_counts, degrees


def find_simple_bridges(adjacency: dict[str, set[str]]) -> set[tuple[str, str]]:
    timer = 0
    tin: dict[str, int] = {}
    low: dict[str, int] = {}
    bridges: set[tuple[str, str]] = set()

    def dfs(node: str, parent: str | None) -> None:
        nonlocal timer
        timer += 1
        tin[node] = low[node] = timer
        for nxt in adjacency.get(node, ()):
            if nxt == parent:
                continue
            if nxt in tin:
                low[node] = min(low[node], tin[nxt])
                continue
            dfs(nxt, node)
            low[node] = min(low[node], low[nxt])
            if low[nxt] > tin[node]:
                bridges.add(tuple(sorted((node, nxt))))

    for node in adjacency:
        if node not in tin:
            dfs(node, None)
    return bridges


def component_side_after_removal(
    adjacency: dict[str, set[str]],
    start: str,
    blocked_pair: tuple[str, str],
) -> set[str]:
    a, b = blocked_pair
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in adjacency.get(current, ()):
            if (current == a and nxt == b) or (current == b and nxt == a):
                continue
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def metric_parts(relation: str, count: float, expected: dict[str, float]) -> tuple[float, float]:
    eta = expected.get(relation)
    if eta is None:
        return 0.0, 0.0
    return max(eta - count, 0.0), max(count - eta, 0.0)


def relation_delta(
    relation_counts: Counter[str],
    expected: dict[str, float],
    remove_relation: str,
    add_relation: str | None = None,
) -> dict[str, Any]:
    remove_count = relation_counts[remove_relation]
    before_deficit, before_surplus = metric_parts(remove_relation, remove_count, expected)
    after_deficit, after_surplus = metric_parts(remove_relation, remove_count - 1, expected)
    deficit_delta = after_deficit - before_deficit
    surplus_delta = after_surplus - before_surplus

    detail = {
        "remove_relation": {
            "relation": remove_relation,
            "observed_before": remove_count,
            "observed_after": remove_count - 1,
            "expected_eta": expected.get(remove_relation),
            "deficit_delta": deficit_delta,
            "surplus_delta": surplus_delta,
        },
        "add_relation": None,
        "deficit_delta": deficit_delta,
        "surplus_delta": surplus_delta,
    }
    if add_relation is None:
        return detail

    add_count = relation_counts[add_relation]
    add_before_deficit, add_before_surplus = metric_parts(add_relation, add_count, expected)
    add_after_deficit, add_after_surplus = metric_parts(add_relation, add_count + 1, expected)
    add_deficit_delta = add_after_deficit - add_before_deficit
    add_surplus_delta = add_after_surplus - add_before_surplus
    detail["add_relation"] = {
        "relation": add_relation,
        "observed_before": add_count,
        "observed_after": add_count + 1,
        "expected_eta": expected.get(add_relation),
        "deficit_delta": add_deficit_delta,
        "surplus_delta": add_surplus_delta,
    }
    detail["deficit_delta"] = deficit_delta + add_deficit_delta
    detail["surplus_delta"] = surplus_delta + add_surplus_delta
    return detail


def target_edges(
    triples: list[Triple],
    relation_counts: Counter[str],
    relation_expected: dict[str, float],
    target_relations: set[str],
    max_target_edges: int,
) -> list[dict[str, Any]]:
    rows: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for h, r, t in triples:
        if r not in target_relations:
            continue
        surplus = max(relation_counts[r] - relation_expected.get(r, 0.0), 0.0)
        if surplus <= 0:
            continue
        rows.append(
            (
                (-surplus, r, h, t),
                {
                    "h": h,
                    "r": r,
                    "t": t,
                    "relation_surplus_before": surplus,
                },
            )
        )
    return [row for _key, row in sorted(rows, key=lambda item: item[0])[:max_target_edges]]


def classify_target(
    target: dict[str, Any],
    pair_counts: Counter[tuple[str, str]],
    bridges: set[tuple[str, str]],
    adjacency: dict[str, set[str]],
    entity_count: int,
) -> dict[str, Any]:
    h, t = target["h"], target["t"]
    pair = tuple(sorted((h, t)))
    is_bridge = h != t and pair_counts[pair] == 1 and pair in bridges
    side: set[str] | None = None
    smaller_side_size = None
    if is_bridge:
        side = component_side_after_removal(adjacency, h, pair)
        smaller_side_size = min(len(side), entity_count - len(side))
    return {
        **target,
        "is_bridge": is_bridge,
        "deletion_safe": not is_bridge,
        "connectivity_critical": is_bridge,
        "bridge_pair": list(pair),
        "smaller_side_size": smaller_side_size,
        "_side": side,
    }


def evaluate_safe_deletion(
    target: dict[str, Any],
    relation_counts: Counter[str],
    relation_expected: dict[str, float],
) -> tuple[dict[str, Any] | None, str | None]:
    r = target["r"]
    if relation_counts[r] - 1 <= 0:
        return None, "would_create_zero_allocated_relation"
    delta = relation_delta(relation_counts, relation_expected, r)
    if delta["surplus_delta"] >= 0:
        return None, "would_not_reduce_total_surplus"
    if delta["deficit_delta"] > 0:
        return None, "would_increase_total_deficit"
    return {
        "operation_type": "remove_safe_edge",
        "target_edge": {"h": target["h"], "r": r, "t": target["t"]},
        "replacement_edge": None,
        "balance_effect": delta,
        "hard_constraints": {
            "weak_component_count": 1,
            "zero_allocated_relations": 0,
            "duplicate_triple_count": 0,
            "allocated_relations_observed": 139,
        },
    }, None


def replacement_crosses_cut(candidate: dict[str, Any], side: set[str] | None) -> bool:
    if side is None:
        return False
    return (candidate["h"] in side) != (candidate["t"] in side)


def evaluate_replacement_candidates(
    target: dict[str, Any],
    replacement_rows: list[dict[str, Any]],
    graph_triples: set[Triple],
    entities: set[str],
    relation_counts: Counter[str],
    relation_expected: dict[str, float],
    target_relations: set[str],
) -> tuple[list[dict[str, Any]], Counter[str]]:
    feasible: list[dict[str, Any]] = []
    rejected: Counter[str] = Counter()
    target_relation = target["r"]
    if relation_counts[target_relation] - 1 <= 0:
        rejected["would_create_zero_allocated_relation"] += len(replacement_rows)
        return feasible, rejected

    for row in replacement_rows:
        candidate = (row["h"], row["r"], row["t"])
        relation = row["r"]
        if candidate in graph_triples:
            rejected["duplicate_replacement_edge"] += 1
            continue
        if relation not in relation_expected:
            rejected["unallocated_replacement_relation"] += 1
            continue
        if row["h"] not in entities or row["t"] not in entities:
            rejected["replacement_endpoint_not_in_parent_graph"] += 1
            continue
        if not replacement_crosses_cut(row, target.get("_side")):
            rejected["does_not_reconnect_bridge_cut"] += 1
            continue

        delta = relation_delta(relation_counts, relation_expected, target_relation, relation)
        if relation in target_relations and delta["surplus_delta"] >= 0:
            rejected["target_generic_replacement_without_net_surplus_gain"] += 1
            continue
        if delta["surplus_delta"] >= 0:
            rejected["would_not_reduce_total_surplus"] += 1
            continue
        if delta["deficit_delta"] > 0:
            rejected["would_increase_total_deficit"] += 1
            continue

        feasible.append(
            {
                "operation_type": "controlled_addition_then_remove",
                "target_edge": {"h": target["h"], "r": target_relation, "t": target["t"]},
                "replacement_edge": {
                    "candidate_id": row.get("candidate_id"),
                    "h": row["h"],
                    "r": relation,
                    "t": row["t"],
                    "score": row.get("score"),
                    "source_stage": row.get("source_stage"),
                    "provenance_type": row.get("provenance_type"),
                    "endpoint_overlap_with_b0": row.get("endpoint_overlap_with_b0"),
                    "relation_allocation_status": row.get("relation_allocation_status"),
                    "path_group_id": row.get("path_group_id"),
                    "path_group_size": row.get("path_group_size"),
                },
                "balance_effect": delta,
                "hard_constraints": {
                    "weak_component_count": 1,
                    "zero_allocated_relations": 0,
                    "duplicate_triple_count": 0,
                    "allocated_relations_observed": 139,
                },
            }
        )
    feasible.sort(key=move_sort_key)
    return feasible, rejected


def move_sort_key(move: dict[str, Any]) -> tuple[Any, ...]:
    replacement = move.get("replacement_edge") or {}
    balance = move["balance_effect"]
    return (
        balance["surplus_delta"],
        balance["deficit_delta"],
        -(replacement.get("score") or 0),
        replacement.get("candidate_id") or "",
        move["target_edge"]["r"],
        move["target_edge"]["h"],
        move["target_edge"]["t"],
    )


def greedy_non_reuse(moves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_targets: set[tuple[str, str, str]] = set()
    used_replacements: set[tuple[str, str, str]] = set()
    for move in sorted(moves, key=move_sort_key):
        target = move["target_edge"]
        target_key = (target["h"], target["r"], target["t"])
        if target_key in used_targets:
            continue
        replacement = move.get("replacement_edge")
        if replacement is not None:
            replacement_key = (replacement["h"], replacement["r"], replacement["t"])
            if replacement_key in used_replacements:
                continue
            used_replacements.add(replacement_key)
        used_targets.add(target_key)
        selected.append(move)
    return selected


def compact_metrics(report: dict[str, Any]) -> dict[str, Any]:
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
    }


def run_probe(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    parent_graph = resolve_path(config["parent_graph_path"])
    allocation_path = resolve_path(config["allocation_path"])
    if not parent_graph.is_file():
        raise FileNotFoundError(parent_graph)
    if not allocation_path.is_file():
        raise FileNotFoundError(allocation_path)

    pool_info = resolve_replacement_pool(config)
    pool_path = resolve_path(pool_info["resolved_path"])
    target_relations = set(config.get("target_relations") or [])

    baseline_report = evaluate_candidate(parent_graph, allocation_path, config.get("parent_candidate_id"), "B0")
    baseline_metrics = compact_metrics(baseline_report)
    triples = load_graph_triples(parent_graph)
    graph_triples = set(triples)
    entities = {node for h, _r, t in graph_triples for node in (h, t)}
    relation_counts = Counter(r for _h, r, _t in graph_triples)
    allocation = load_allocation(allocation_path)
    relation_expected = allocation["relation_expected"]
    replacement_rows = load_replacement_pool(
        pool_path,
        args.max_replacement_candidates,
        target_relations,
    )

    adjacency, pair_counts, _degrees = build_undirected(graph_triples)
    simple_bridges = find_simple_bridges(adjacency)
    bridges = {pair for pair in simple_bridges if pair_counts[pair] == 1}
    selected_targets = target_edges(
        sorted(graph_triples),
        relation_counts,
        relation_expected,
        target_relations,
        args.max_target_edges,
    )

    target_results: list[dict[str, Any]] = []
    feasible_safe_deletions: list[dict[str, Any]] = []
    feasible_replacements: list[dict[str, Any]] = []
    rejection_counts: Counter[str] = Counter()

    for target in selected_targets:
        classified = classify_target(target, pair_counts, bridges, adjacency, len(entities))
        side = classified.pop("_side")
        if classified["deletion_safe"]:
            move, reason = evaluate_safe_deletion(classified, relation_counts, relation_expected)
            if move:
                feasible_safe_deletions.append(move)
            elif reason:
                rejection_counts[reason] += 1
            target_results.append(
                {
                    **classified,
                    "feasible_safe_deletion": move is not None,
                    "feasible_replacement_count": 0,
                    "rejection_reason": reason,
                }
            )
            continue

        classified["_side"] = side
        replacements, rejected = evaluate_replacement_candidates(
            classified,
            replacement_rows,
            graph_triples,
            entities,
            relation_counts,
            relation_expected,
            target_relations,
        )
        classified.pop("_side", None)
        feasible_replacements.extend(replacements)
        rejection_counts.update(rejected)
        target_results.append(
            {
                **classified,
                "feasible_safe_deletion": False,
                "feasible_replacement_count": len(replacements),
                "best_replacements": replacements[:5],
                "rejection_counts": dict(sorted(rejected.items())),
            }
        )

    all_feasible_moves = feasible_safe_deletions + feasible_replacements
    greedy_moves = greedy_non_reuse(all_feasible_moves)
    best_surplus_delta = min((m["balance_effect"]["surplus_delta"] for m in all_feasible_moves), default=None)
    best_deficit_delta = min((m["balance_effect"]["deficit_delta"] for m in all_feasible_moves), default=None)
    finished = time.time()

    deletion_safe_count = sum(1 for row in target_results if row["deletion_safe"])
    connectivity_critical_count = len(target_results) - deletion_safe_count
    critical_with_replacements = sum(
        1 for row in target_results if row["connectivity_critical"] and row["feasible_replacement_count"] > 0
    )

    return {
        "schema_version": "c4-bridge-aware-replace-add-probe-v1",
        "probe_id": "C4_bridge_aware_replace_add_probe_only",
        "candidate_id": config["candidate_id"],
        "status": "probe_only_no_graph_generated",
        "inputs": {
            "config": repo_relative(resolve_path(args.config)),
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
        "baseline_metrics": baseline_metrics,
        "protected_constraints": config.get("protected_constraints"),
        "summary": {
            "target_edges_tested": len(target_results),
            "replacement_candidates_loaded": len(replacement_rows),
            "replacement_pair_tests_upper_bound": connectivity_critical_count * len(replacement_rows),
            "deletion_safe_count": deletion_safe_count,
            "connectivity_critical_count": connectivity_critical_count,
            "feasible_safe_deletions": len(feasible_safe_deletions),
            "feasible_replacements_for_connectivity_critical": critical_with_replacements,
            "total_feasible_independent_moves": len(all_feasible_moves),
            "greedy_non_reuse_candidate_count": len(greedy_moves),
            "best_observed_surplus_delta": best_surplus_delta,
            "best_observed_deficit_delta": best_deficit_delta,
        },
        "rejection_reasons": dict(sorted(rejection_counts.items())),
        "target_results_first_50": target_results[:50],
        "best_feasible_moves_first_50": sorted(all_feasible_moves, key=move_sort_key)[:50],
        "greedy_non_reuse_moves_first_50": greedy_moves[:50],
        "notes": [
            "Probe-only run; no graph candidate was generated.",
            "No WDQS query was made.",
            "No LLM call was made.",
            "Parent graph was read only and not modified.",
            "candidate_registry.v1.json was not updated.",
        ],
        "runtime": {
            "started_on": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "finished_on": datetime.fromtimestamp(finished, timezone.utc).isoformat(),
            "elapsed_seconds": round(finished - started, 6),
        },
    }


def write_summary(path: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    baseline = report["baseline_metrics"]
    lines = [
        "# C4 Bridge-Aware Replace/Add Probe",
        "",
        "Status: probe only. No graph candidate was generated.",
        "",
        "## Inputs",
        "",
        f"- Config: `{report['inputs']['config']}`",
        f"- Parent graph: `{report['inputs']['parent_graph']['path']}`",
        f"- Parent graph SHA256: `{report['inputs']['parent_graph']['sha256']}`",
        f"- Allocation: `{report['inputs']['allocation']['path']}`",
        f"- Allocation SHA256: `{report['inputs']['allocation']['sha256']}`",
        f"- Replacement pool: `{report['inputs']['replacement_pool']['resolved_path']}`",
        f"- Replacement pool SHA256: `{report['inputs']['replacement_pool']['sha256']}`",
        f"- Replacement pool note: {report['inputs']['replacement_pool']['resolution_note']}",
        "",
        "## Baseline B0 Metrics",
        "",
        f"- Unique triples: `{baseline['unique_triples']}`",
        f"- Weak components: `{baseline['weak_component_count']}`",
        f"- Duplicate triples: `{baseline['duplicate_triple_count']}`",
        f"- Allocated relations observed: `{baseline['allocated_relations_observed']}`",
        f"- Zero allocated relations: `{baseline['zero_allocated_relations']}`",
        f"- Total surplus: `{baseline['total_surplus']}`",
        f"- Total deficit: `{baseline['total_deficit']}`",
        "",
        "## Probe Results",
        "",
        f"- Target edges tested: `{summary['target_edges_tested']}`",
        f"- Deletion-safe targets: `{summary['deletion_safe_count']}`",
        f"- Connectivity-critical targets: `{summary['connectivity_critical_count']}`",
        f"- Feasible safe deletions: `{summary['feasible_safe_deletions']}`",
        f"- Connectivity-critical targets with feasible replacement: `{summary['feasible_replacements_for_connectivity_critical']}`",
        f"- Total feasible independent moves: `{summary['total_feasible_independent_moves']}`",
        f"- Greedy non-reuse candidate count: `{summary['greedy_non_reuse_candidate_count']}`",
        f"- Best observed surplus delta: `{summary['best_observed_surplus_delta']}`",
        f"- Best observed deficit delta: `{summary['best_observed_deficit_delta']}`",
        "",
        "## Rejection Reasons",
        "",
    ]
    if report["rejection_reasons"]:
        lines.extend(["| Reason | Count |", "| --- | ---: |"])
        for reason, count in report["rejection_reasons"].items():
            lines.append(f"| `{reason}` | {count} |")
    else:
        lines.append("No rejection reasons were recorded.")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This probe writes reports only under `reports/probe_only/`.",
            "- `outputs/graph.jsonl` is not written.",
            "- The candidate registry is not updated.",
            "- Live WDQS and LLM sources are disabled.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    config = load_config(resolve_path(args.config))
    pool_info = resolve_replacement_pool(config)
    if args.dry_run:
        print("dry_run=true")
        print(f"candidate_id={config.get('candidate_id')}")
        print(f"parent_graph={config.get('parent_graph_path')}")
        print(f"allocation={config.get('allocation_path')}")
        print(f"replacement_pool={pool_info['resolved_path']}")
        print(f"replacement_pool_sha256={pool_info['sha256']}")
        print(f"output_dir={DEFAULT_OUTPUT_DIR}")
        print("no_reports_written=true")
        return 0

    paths = output_paths()
    refuse_overwrite(paths, args.force)
    report = run_probe(config, args)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths["probe_report"].write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_summary(paths["probe_summary"], report)
    print(f"probe_report={paths['probe_report']}")
    print(f"probe_summary={paths['probe_summary']}")
    print(f"target_edges_tested={report['summary']['target_edges_tested']}")
    print(f"deletion_safe_count={report['summary']['deletion_safe_count']}")
    print(f"connectivity_critical_count={report['summary']['connectivity_critical_count']}")
    print(f"feasible_safe_deletions={report['summary']['feasible_safe_deletions']}")
    print(
        "feasible_replacements_for_connectivity_critical="
        f"{report['summary']['feasible_replacements_for_connectivity_critical']}"
    )
    print(f"greedy_non_reuse_candidate_count={report['summary']['greedy_non_reuse_candidate_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
