#!/usr/bin/env python3
"""Generate a targeted generic-dominance pruning candidate.

This utility is intentionally standalone. It reads a graph and allocation
manifest, removes only safe target-relation triples, writes one JSONL graph, and
writes a provenance report. It does not import the historical pipeline modules.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


Triple = tuple[str, str, str]


@dataclass
class GraphData:
    triples: list[Triple]
    raw_total_rows: int
    duplicate_triple_count: int
    raw_relation_counts: Counter[str]


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.rank: dict[str, int] = {}

    def add(self, item: str) -> None:
        if item not in self.parent:
            self.parent[item] = item
            self.rank[item] = 0

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            parent = self.parent[item]
            self.parent[item] = root
            item = parent
        return root

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1

    def component_sizes(self) -> list[int]:
        counts: Counter[str] = Counter()
        for item in list(self.parent):
            counts[self.find(item)] += 1
        return list(counts.values())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_graph(path: Path) -> GraphData:
    raw_relation_counts: Counter[str] = Counter()
    raw_total_rows = 0
    seen: set[Triple] = set()
    triples: list[Triple] = []

    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {"h", "r", "t"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV graph missing required columns: {sorted(missing)}")
            for row in reader:
                triple = (str(row["h"]), str(row["r"]), str(row["t"]))
                raw_total_rows += 1
                raw_relation_counts[triple[1]] += 1
                if triple not in seen:
                    seen.add(triple)
                    triples.append(triple)
    elif suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                try:
                    triple = (str(obj["h"]), str(obj["r"]), str(obj["t"]))
                except KeyError as exc:
                    raise ValueError(f"JSONL graph line {line_no} missing key {exc}") from exc
                raw_total_rows += 1
                raw_relation_counts[triple[1]] += 1
                if triple not in seen:
                    seen.add(triple)
                    triples.append(triple)
    else:
        raise ValueError(f"Unsupported graph extension {path.suffix!r}; use .csv or .jsonl")

    return GraphData(
        triples=triples,
        raw_total_rows=raw_total_rows,
        duplicate_triple_count=raw_total_rows - len(triples),
        raw_relation_counts=raw_relation_counts,
    )


def extract_eta(row: dict[str, Any]) -> float:
    for key in ("eta_integer", "eta", "eta_expected"):
        value = row.get(key)
        if value is not None:
            return float(value)
    return 0.0


def load_allocation(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("allocations")
    if not isinstance(rows, list):
        raise ValueError("Allocation JSON must contain an 'allocations' list")

    relation_expected: dict[str, float] = defaultdict(float)
    positive_rows = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        relation = row.get("relation")
        if not relation:
            continue
        eta = extract_eta(row)
        if eta <= 0:
            continue
        positive_rows += 1
        relation_expected[str(relation)] += eta

    return {
        "raw_keys": sorted(data.keys()),
        "positive_allocation_rows": positive_rows,
        "relation_expected": dict(sorted(relation_expected.items())),
        "eta_field_precedence": ["eta_integer", "eta", "eta_expected"],
    }


def load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Config JSON root must be an object")
    return data


def nested_get(data: dict[str, Any], path: list[str]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def config_consistency_checks(
    config: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, dict[str, Any]]:
    cli_targets = sorted(set(args.target_relation or []))
    config_targets_raw = config.get("target_relations")
    config_targets = (
        sorted({str(relation) for relation in config_targets_raw})
        if isinstance(config_targets_raw, list)
        else config_targets_raw
    )

    checks = {
        "candidate_id": {
            "expected": "C2",
            "actual": config.get("candidate_id"),
        },
        "input_graph.path": {
            "expected": str(args.input_graph),
            "actual": nested_get(config, ["input_graph", "path"]),
        },
        "input_graph.sha256": {
            "expected": args.parent_graph_sha256,
            "actual": nested_get(config, ["input_graph", "sha256"]),
        },
        "allocation.path": {
            "expected": str(args.allocation),
            "actual": nested_get(config, ["allocation", "path"]),
        },
        "allocation.sha256": {
            "expected": args.allocation_sha256,
            "actual": nested_get(config, ["allocation", "sha256"]),
        },
        "outputs.candidate_graph": {
            "expected": str(args.output_graph),
            "actual": nested_get(config, ["outputs", "candidate_graph"]),
        },
        "outputs.generation_report": {
            "expected": str(args.output_report),
            "actual": nested_get(config, ["outputs", "generation_report"]),
        },
        "target_relations": {
            "expected": cli_targets,
            "actual": config_targets,
        },
    }

    for check in checks.values():
        check["passed"] = check["actual"] == check["expected"]
    return checks


def relation_counts(triples: list[Triple]) -> Counter[str]:
    return Counter(r for _, r, _ in triples)


def entity_degrees(triples: list[Triple]) -> Counter[str]:
    degrees: Counter[str] = Counter()
    for h, _, t in triples:
        degrees[h] += 1
        if t != h:
            degrees[t] += 1
    return degrees


def graph_metrics(
    triples: list[Triple],
    relation_expected: dict[str, float],
    raw_total_rows: int | None = None,
    duplicate_triple_count: int = 0,
) -> dict[str, Any]:
    counts = relation_counts(triples)
    entities: set[str] = set()
    uf = UnionFind()
    for h, _, t in triples:
        entities.update((h, t))
        uf.union(h, t)

    component_sizes = uf.component_sizes()
    largest_component_size = max(component_sizes) if component_sizes else 0
    largest_component_ratio = (
        largest_component_size / len(entities) if entities else 0.0
    )

    allocated_relations = set(relation_expected)
    observed_allocated = 0
    zero_allocated: list[str] = []
    total_expected = 0.0
    total_observed = 0
    total_deficit = 0.0
    total_surplus = 0.0
    per_relation: dict[str, dict[str, float | int | str]] = {}

    for relation in sorted(allocated_relations):
        expected = float(relation_expected[relation])
        observed = int(counts.get(relation, 0))
        deficit = max(expected - observed, 0.0)
        surplus = max(observed - expected, 0.0)
        total_expected += expected
        total_observed += observed
        total_deficit += deficit
        total_surplus += surplus
        if observed > 0:
            observed_allocated += 1
        else:
            zero_allocated.append(relation)
        per_relation[relation] = {
            "relation": relation,
            "expected_eta": expected,
            "observed_count": observed,
            "deficit": deficit,
            "surplus": surplus,
        }

    return {
        "raw_total_rows": len(triples) if raw_total_rows is None else raw_total_rows,
        "unique_triples": len(triples),
        "duplicate_triple_count": duplicate_triple_count,
        "unique_entities": len(entities),
        "unique_relations": len(counts),
        "weak_component_count": len(component_sizes),
        "largest_weak_component_size": largest_component_size,
        "largest_weak_component_ratio": largest_component_ratio,
        "relation_counts": dict(sorted(counts.items())),
        "allocation_relation_count": len(allocated_relations),
        "allocated_relations_observed": observed_allocated,
        "zero_allocated_relations": len(zero_allocated),
        "zero_allocated_relation_ids": zero_allocated,
        "total_expected_eta": total_expected,
        "total_observed_allocated_triples": total_observed,
        "total_deficit": total_deficit,
        "total_surplus": total_surplus,
        "per_relation_expected_observed": per_relation,
    }


def would_preserve_connectivity(
    triples: list[Triple],
    remove_index: int,
    required_components: int,
    required_largest_ratio: float,
    relation_expected: dict[str, float],
) -> tuple[bool, dict[str, Any]]:
    candidate = triples[:remove_index] + triples[remove_index + 1 :]
    metrics = graph_metrics(candidate, relation_expected)
    passes = (
        metrics["weak_component_count"] == required_components
        and metrics["largest_weak_component_ratio"] >= required_largest_ratio
    )
    return passes, {
        "weak_component_count": metrics["weak_component_count"],
        "largest_weak_component_ratio": metrics["largest_weak_component_ratio"],
    }


def edge_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def weak_connectivity_bridge_edges(triples: list[Triple]) -> set[tuple[str, str]]:
    """Return undirected entity-pair keys whose deletion would split a component.

    Parallel edges between the same entity pair are never bridges for single-edge
    deletion. Self-loops are ignored because they do not affect weak
    connectivity.
    """

    pair_counts: Counter[tuple[str, str]] = Counter()
    adjacency: dict[str, set[str]] = defaultdict(set)
    for h, _, t in triples:
        if h == t:
            continue
        key = edge_key(h, t)
        pair_counts[key] += 1
        adjacency[h].add(t)
        adjacency[t].add(h)

    visited_at: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    bridges: set[tuple[str, str]] = set()
    time = 0

    def dfs(node: str) -> None:
        nonlocal time
        time += 1
        visited_at[node] = time
        low[node] = time
        for neighbor in adjacency[node]:
            if neighbor == parent.get(node):
                continue
            if neighbor not in visited_at:
                parent[neighbor] = node
                dfs(neighbor)
                low[node] = min(low[node], low[neighbor])
                key = edge_key(node, neighbor)
                if low[neighbor] > visited_at[node] and pair_counts[key] == 1:
                    bridges.add(key)
            else:
                low[node] = min(low[node], visited_at[neighbor])

    for node in list(adjacency):
        if node not in visited_at:
            parent[node] = None
            dfs(node)

    return bridges


def target_relation_summary(
    target_relations: list[str],
    initial_metrics: dict[str, Any],
    final_metrics: dict[str, Any],
    relation_expected: dict[str, float],
) -> dict[str, dict[str, float | int]]:
    initial_counts = initial_metrics["relation_counts"]
    final_counts = final_metrics["relation_counts"]
    summary: dict[str, dict[str, float | int]] = {}
    for relation in target_relations:
        expected = float(relation_expected.get(relation, 0.0))
        initial_count = int(initial_counts.get(relation, 0))
        final_count = int(final_counts.get(relation, 0))
        summary[relation] = {
            "expected_eta": expected,
            "initial_count": initial_count,
            "final_count": final_count,
            "initial_deficit": max(expected - initial_count, 0.0),
            "final_deficit": max(expected - final_count, 0.0),
            "initial_surplus": max(initial_count - expected, 0.0),
            "final_surplus": max(final_count - expected, 0.0),
            "removed_count": initial_count - final_count,
        }
    return summary


def choose_safe_deletion(
    triples: list[Triple],
    target_relations: set[str],
    relation_expected: dict[str, float],
    required_components: int,
    required_largest_ratio: float,
    rejection_reasons: Counter[str],
) -> tuple[int | None, dict[str, Any] | None]:
    counts = relation_counts(triples)
    degrees = entity_degrees(triples)
    bridge_edges = weak_connectivity_bridge_edges(triples)
    scored: list[tuple[float, int, int, str, str, str, int, Triple]] = []

    for index, triple in enumerate(triples):
        h, r, t = triple
        if r not in target_relations:
            continue
        expected = float(relation_expected.get(r, 0.0))
        observed = int(counts.get(r, 0))
        if observed < expected:
            rejection_reasons["relation_already_underfilled"] += 1
            continue
        if observed - 1 < expected:
            rejection_reasons["would_reduce_relation_below_eta"] += 1
            continue
        min_degree = min(degrees[h], degrees[t])
        if min_degree <= 1:
            rejection_reasons["endpoint_degree_not_redundant"] += 1
            continue
        surplus = observed - expected
        scored.append(
            (
                float(min_degree),
                int(degrees[h] + degrees[t]),
                int(surplus),
                r,
                h,
                t,
                index,
                triple,
            )
        )

    scored.sort(key=lambda row: (-row[0], -row[1], -row[2], row[3], row[4], row[5]))

    for _, _, _, _, _, _, index, triple in scored:
        h, r, t = triple
        if h != t and edge_key(h, t) in bridge_edges:
            rejection_reasons["would_disconnect_graph"] += 1
            continue
        return index, {
            "h": h,
            "r": r,
            "t": t,
            "relation_count_before": counts[r],
            "relation_count_after": counts[r] - 1,
            "endpoint_degrees_before": {"h": degrees[h], "t": degrees[t]},
            "connectivity_after": {
                "weak_component_count": required_components,
                "largest_weak_component_ratio": required_largest_ratio,
                "checked_by": "undirected_bridge_test_then_post_acceptance_full_metrics",
            },
        }

    if scored:
        rejection_reasons["no_connectivity_safe_candidate"] += 1
    else:
        rejection_reasons["no_eta_and_endpoint_safe_candidate"] += 1
    return None, None


def write_jsonl_graph(path: Path, triples: list[Triple]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for index, (h, r, t) in enumerate(triples, start=1):
            row = {
                "triple_id": f"C2_{index:08d}",
                "h": h,
                "r": r,
                "t": t,
            }
            f.write(json.dumps(row, sort_keys=True) + "\n")


def check_hard_constraints(
    metrics: dict[str, Any],
    args: argparse.Namespace,
    output_duplicate_count: int,
) -> dict[str, dict[str, Any]]:
    checks = {
        "weak_component_count": {
            "expected": args.require_weak_components,
            "actual": metrics["weak_component_count"],
            "passed": metrics["weak_component_count"] == args.require_weak_components,
        },
        "largest_weak_component_ratio": {
            "minimum": args.require_largest_ratio,
            "actual": metrics["largest_weak_component_ratio"],
            "passed": metrics["largest_weak_component_ratio"] >= args.require_largest_ratio,
        },
        "allocated_relations_observed": {
            "minimum": args.min_allocated_relations_observed,
            "actual": metrics["allocated_relations_observed"],
            "passed": metrics["allocated_relations_observed"]
            >= args.min_allocated_relations_observed,
        },
        "zero_allocated_relations": {
            "maximum": args.max_zero_allocated_relations,
            "actual": metrics["zero_allocated_relations"],
            "passed": metrics["zero_allocated_relations"] <= args.max_zero_allocated_relations,
        },
        "total_deficit": {
            "maximum": args.max_total_deficit,
            "actual": metrics["total_deficit"],
            "passed": metrics["total_deficit"] <= args.max_total_deficit,
        },
        "total_surplus": {
            "maximum": args.max_final_surplus,
            "actual": metrics["total_surplus"],
            "passed": metrics["total_surplus"] <= args.max_final_surplus,
        },
        "duplicate_triple_count": {
            "expected": args.require_duplicate_count,
            "actual": output_duplicate_count,
            "passed": output_duplicate_count == args.require_duplicate_count,
        },
    }
    return checks


def check_strong_thresholds(metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    per_relation = metrics["per_relation_expected_observed"]
    target_relations = ("P31", "P279", "P131")

    def relation_observed(relation: str) -> int:
        row = per_relation.get(relation, {})
        return int(row.get("observed_count", 0))

    def relation_surplus(relation: str) -> float:
        row = per_relation.get(relation, {})
        return float(row.get("surplus", 0.0))

    combined_surplus = sum(relation_surplus(relation) for relation in target_relations)
    checks = {
        "total_deficit_le_2019": {
            "threshold": 2019,
            "actual": metrics["total_deficit"],
            "passed": metrics["total_deficit"] <= 2019,
        },
        "total_surplus_le_6581": {
            "threshold": 6581,
            "actual": metrics["total_surplus"],
            "passed": metrics["total_surplus"] <= 6581,
        },
        "combined_P31_P279_P131_surplus_lt_6166": {
            "threshold": 6166,
            "actual": combined_surplus,
            "passed": combined_surplus < 6166,
        },
        "P31_observed_lt_5953": {
            "threshold": 5953,
            "actual": relation_observed("P31"),
            "passed": relation_observed("P31") < 5953,
        },
        "P279_observed_lt_748": {
            "threshold": 748,
            "actual": relation_observed("P279"),
            "passed": relation_observed("P279") < 748,
        },
        "P131_observed_lt_344": {
            "threshold": 344,
            "actual": relation_observed("P131"),
            "passed": relation_observed("P131") < 344,
        },
    }
    return checks


def all_checks_pass(checks: dict[str, dict[str, Any]]) -> bool:
    return all(bool(row["passed"]) for row in checks.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--input-graph", required=True, type=Path)
    parser.add_argument("--allocation", required=True, type=Path)
    parser.add_argument("--output-graph", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    parser.add_argument("--parent-candidate-id", required=True)
    parser.add_argument("--parent-graph-sha256", required=True)
    parser.add_argument("--allocation-sha256", required=True)
    parser.add_argument("--target-relation", action="append", required=True)
    parser.add_argument("--max-removals", required=True, type=int)
    parser.add_argument("--batch-size", required=True, type=int)
    parser.add_argument("--require-weak-components", required=True, type=int)
    parser.add_argument("--require-largest-ratio", required=True, type=float)
    parser.add_argument("--min-allocated-relations-observed", required=True, type=int)
    parser.add_argument("--max-zero-allocated-relations", required=True, type=int)
    parser.add_argument("--max-total-deficit", required=True, type=float)
    parser.add_argument("--max-final-surplus", required=True, type=float)
    parser.add_argument("--require-duplicate-count", required=True, type=int)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting --output-graph. The C2 command template does not pass this.",
    )
    return parser.parse_args()


def base_report(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "candidate_id": "C2",
        "label": "targeted_generic_pruning_from_B0",
        "parent_candidate_id": args.parent_candidate_id,
        "input_graph": {
            "path": str(args.input_graph),
            "expected_sha256": args.parent_graph_sha256,
            "actual_sha256": None,
        },
        "allocation": {
            "path": str(args.allocation),
            "expected_sha256": args.allocation_sha256,
            "actual_sha256": None,
        },
        "config_path": str(args.config),
        "config_consistency_checks": {},
        "candidate_status": "not_generated",
        "output_written": False,
        "output_graph": {
            "path": str(args.output_graph),
            "sha256": None,
            "written": False,
        },
        "target_relations": sorted(set(args.target_relation or [])),
        "max_removals": args.max_removals,
        "batch_size": args.batch_size,
        "accepted_deletion_count": 0,
        "rejected_deletion_count": 0,
        "rejection_reasons": {},
        "stop_reason": None,
        "initial_metrics": None,
        "final_metrics": None,
        "per_target_relation_before_after": {},
        "removed_triples_first_100": [],
        "removed_triples_total_count": 0,
        "hard_constraint_check_results": {},
        "passes_minimum_thresholds": False,
        "strong_threshold_check_results": {},
        "passes_strong_thresholds": False,
        "minimum_threshold_policy": {
            "description": (
                "Minimum thresholds determine generated candidate status. "
                "Pre-generation failures exit nonzero. If an output graph is written, "
                "the generator exits 0 even when minimum thresholds fail so the "
                "standard evaluator can still run under set -e."
            ),
            "required_for_generated_passed_minimum_thresholds": [
                "weak_component_count",
                "largest_weak_component_ratio",
                "allocated_relations_observed",
                "zero_allocated_relations",
                "total_deficit",
                "total_surplus",
                "duplicate_triple_count",
            ],
        },
        "strong_threshold_policy": {
            "description": (
                "Strong thresholds are decision support only. They are reported but "
                "do not control generator exit status."
            ),
            "checks": [
                "total_deficit <= 2019",
                "total_surplus <= 6581",
                "combined P31+P279+P131 surplus < 6166",
                "P31 observed < 5953",
                "P279 observed < 748",
                "P131 observed < 344",
            ],
        },
        "exact_command_arguments": {
            "argv": sys.argv,
            "parsed_args": {
                key: str(value) if isinstance(value, Path) else value
                for key, value in vars(args).items()
            },
        },
        "errors": [],
        "notes": [
            "Input graph rows are de-duplicated before pruning.",
            "Deletion candidates are limited to target relations.",
            "Batch size greater than 1 is refused by this first C2 generator.",
            "Output graph rows contain h, r, t, and triple_id.",
            "Run the standard evaluator after generation for final accept/reject tracking.",
        ],
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fail_with_report(
    args: argparse.Namespace,
    report: dict[str, Any],
    message: str,
    exit_code: int = 2,
) -> int:
    report["errors"].append(message)
    report["stop_reason"] = "failed_before_generation"
    report["candidate_status"] = "failed_before_generation"
    write_report(args.output_report, report)
    print(message, file=sys.stderr)
    return exit_code


def main() -> int:
    args = parse_args()
    report = base_report(args)

    if args.batch_size != 1:
        return fail_with_report(
            args,
            report,
            "Batch size greater than 1 is not implemented safely; rerun with --batch-size 1.",
        )
    if args.max_removals < 0:
        return fail_with_report(args, report, "--max-removals must be nonnegative.")
    if args.output_graph.exists() and not args.overwrite:
        return fail_with_report(
            args,
            report,
            f"Refusing to overwrite existing output graph: {args.output_graph}",
        )
    if not args.input_graph.is_file():
        return fail_with_report(args, report, f"Missing input graph: {args.input_graph}")
    if not args.allocation.is_file():
        return fail_with_report(args, report, f"Missing allocation JSON: {args.allocation}")
    if not args.config.is_file():
        return fail_with_report(args, report, f"Missing config JSON: {args.config}")

    try:
        config = load_config(args.config)
    except Exception as exc:
        return fail_with_report(args, report, f"Invalid config JSON: {exc}")

    checks = config_consistency_checks(config, args)
    report["config_consistency_checks"] = checks
    if not all_checks_pass(checks):
        return fail_with_report(
            args,
            report,
            "Config consistency check failed; refusing to generate C2.",
        )

    actual_parent_hash = sha256_file(args.input_graph)
    actual_allocation_hash = sha256_file(args.allocation)
    report["input_graph"]["actual_sha256"] = actual_parent_hash
    report["allocation"]["actual_sha256"] = actual_allocation_hash

    if actual_parent_hash != args.parent_graph_sha256:
        return fail_with_report(
            args,
            report,
            "Parent graph SHA256 mismatch; refusing to generate C2.",
        )
    if actual_allocation_hash != args.allocation_sha256:
        return fail_with_report(
            args,
            report,
            "Allocation SHA256 mismatch; refusing to generate C2.",
        )

    graph = read_graph(args.input_graph)
    allocation = load_allocation(args.allocation)
    relation_expected = allocation["relation_expected"]
    report["allocation_extraction"] = {
        "raw_keys": allocation["raw_keys"],
        "positive_allocation_rows": allocation["positive_allocation_rows"],
        "eta_field_precedence": allocation["eta_field_precedence"],
    }

    current_triples = list(graph.triples)
    initial_metrics = graph_metrics(
        current_triples,
        relation_expected,
        raw_total_rows=graph.raw_total_rows,
        duplicate_triple_count=graph.duplicate_triple_count,
    )
    report["initial_metrics"] = initial_metrics

    target_relations = set(args.target_relation)
    removed_triples: list[dict[str, Any]] = []
    rejection_reasons: Counter[str] = Counter()
    stop_reason = "max_removals_reached"

    while len(removed_triples) < args.max_removals:
        delete_index, removal_info = choose_safe_deletion(
            current_triples,
            target_relations,
            relation_expected,
            args.require_weak_components,
            args.require_largest_ratio,
            rejection_reasons,
        )
        if delete_index is None or removal_info is None:
            stop_reason = "no_safe_deletion_remaining"
            break

        removed = current_triples.pop(delete_index)
        removal_info["accepted_order"] = len(removed_triples) + 1
        removal_info["h"], removal_info["r"], removal_info["t"] = removed
        removed_triples.append(removal_info)

        post_metrics = graph_metrics(current_triples, relation_expected)
        if post_metrics["weak_component_count"] != args.require_weak_components:
            stop_reason = "internal_error_connectivity_guard_failed_after_acceptance"
            report["errors"].append(stop_reason)
            break
        if post_metrics["largest_weak_component_ratio"] < args.require_largest_ratio:
            stop_reason = "internal_error_largest_ratio_guard_failed_after_acceptance"
            report["errors"].append(stop_reason)
            break

    final_metrics = graph_metrics(current_triples, relation_expected)
    checks = check_hard_constraints(
        final_metrics,
        args,
        output_duplicate_count=0,
    )
    passes = all_checks_pass(checks)
    strong_checks = check_strong_thresholds(final_metrics)
    strong_passes = all_checks_pass(strong_checks)

    report["accepted_deletion_count"] = len(removed_triples)
    report["rejected_deletion_count"] = int(sum(rejection_reasons.values()))
    report["rejection_reasons"] = dict(sorted(rejection_reasons.items()))
    report["stop_reason"] = stop_reason
    report["final_metrics"] = final_metrics
    report["per_target_relation_before_after"] = target_relation_summary(
        sorted(target_relations),
        initial_metrics,
        final_metrics,
        relation_expected,
    )
    report["removed_triples_first_100"] = removed_triples[:100]
    report["removed_triples_total_count"] = len(removed_triples)
    report["hard_constraint_check_results"] = checks
    report["passes_minimum_thresholds"] = passes
    report["strong_threshold_check_results"] = strong_checks
    report["passes_strong_thresholds"] = strong_passes

    if len(removed_triples) == 0 and not passes:
        report["candidate_status"] = "not_generated_failed_minimum_thresholds"
        report["errors"].append(
            "No deletion was possible and final constraints do not pass; no graph was written."
        )
        write_report(args.output_report, report)
        return 1

    write_jsonl_graph(args.output_graph, current_triples)
    output_hash = sha256_file(args.output_graph)
    report["output_graph"]["sha256"] = output_hash
    report["output_graph"]["written"] = True
    report["output_written"] = True
    report["candidate_status"] = (
        "generated_passed_minimum_thresholds"
        if passes
        else "generated_failed_minimum_thresholds"
    )
    write_report(args.output_report, report)

    if not passes:
        print(
            "C2 candidate failed minimum thresholds; graph and report were written. "
            "Run the standard evaluator before rejection tracking.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
