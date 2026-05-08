#!/usr/bin/env python3
"""Evaluate one graph candidate against one allocation manifest.

This script is intentionally standalone and read-only with respect to graph and
allocation inputs. It writes a JSON report and a compact Markdown summary.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def read_graph(path: Path) -> dict[str, Any]:
    raw_relation_counts: Counter[str] = Counter()
    unique_relation_counts: Counter[str] = Counter()
    unique_triples: set[tuple[str, str, str]] = set()
    raw_total_rows = 0

    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {"h", "r", "t"}
            missing = required - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV graph missing required columns: {sorted(missing)}")
            for row in reader:
                h, r, t = row["h"], row["r"], row["t"]
                raw_total_rows += 1
                raw_relation_counts[r] += 1
                unique_triples.add((h, r, t))
    elif suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                try:
                    h, r, t = obj["h"], obj["r"], obj["t"]
                except KeyError as exc:
                    raise ValueError(f"JSONL graph line {line_no} missing key {exc}") from exc
                raw_total_rows += 1
                raw_relation_counts[r] += 1
                unique_triples.add((h, r, t))
    else:
        raise ValueError(f"Unsupported graph extension {path.suffix!r}; use .csv or .jsonl")

    entities: set[str] = set()
    uf = UnionFind()
    for h, r, t in unique_triples:
        entities.update((h, t))
        unique_relation_counts[r] += 1
        uf.union(h, t)

    component_sizes = uf.component_sizes()
    largest_component_size = max(component_sizes) if component_sizes else 0
    largest_component_ratio = (
        largest_component_size / len(entities) if entities else 0.0
    )
    duplicate_triple_count = raw_total_rows - len(unique_triples)
    return {
        "raw_total_rows": raw_total_rows,
        "total_triples": len(unique_triples),
        "unique_triples": len(unique_triples),
        "duplicate_triple_count": duplicate_triple_count,
        "unique_entities": len(entities),
        "unique_relations": len(unique_relation_counts),
        "weak_component_count": len(component_sizes),
        "largest_weak_component_size": largest_component_size,
        "largest_weak_component_ratio": largest_component_ratio,
        "raw_relation_counts": dict(sorted(raw_relation_counts.items())),
        "unique_relation_counts": dict(sorted(unique_relation_counts.items())),
        "relation_counts": dict(sorted(unique_relation_counts.items())),
        "raw_relation_count_distribution": relation_count_distribution(raw_relation_counts),
        "unique_relation_count_distribution": relation_count_distribution(unique_relation_counts),
        "relation_count_distribution": relation_count_distribution(unique_relation_counts),
        "evaluation_notes": [
            "Allocation metrics are computed from unique triples.",
            "relation_counts is an alias for unique_relation_counts.",
            "Connectivity and entity counts are computed from unique triples.",
        ],
    }


def relation_count_distribution(relation_counts: Counter[str]) -> dict[str, Any]:
    values = sorted(relation_counts.values())
    if not values:
        return {
            "min": 0,
            "max": 0,
            "mean": 0.0,
            "median": 0.0,
            "histogram": {},
        }
    histogram: dict[str, int] = {}
    for value in values:
        if value < 10:
            bucket = "1-9"
        elif value < 50:
            bucket = "10-49"
        elif value < 100:
            bucket = "50-99"
        elif value < 250:
            bucket = "100-249"
        elif value < 500:
            bucket = "250-499"
        elif value < 1000:
            bucket = "500-999"
        else:
            bucket = "1000+"
        histogram[bucket] = histogram.get(bucket, 0) + 1
    return {
        "min": values[0],
        "max": values[-1],
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "histogram": histogram,
    }


def load_allocation(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    allocations = data.get("allocations") or []
    pattern_groups = data.get("pattern_groups") or {}
    eta_per_group = data.get("eta_per_group") or {}

    relation_expected: dict[str, float] = defaultdict(float)
    relation_patterns: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pattern_expected: dict[str, float] = defaultdict(float)
    positive_rows = 0

    for row in allocations:
        relation = row.get("relation")
        pattern = row.get("pattern")
        if not relation:
            continue
        eta = extract_eta(row)
        if eta <= 0:
            continue
        positive_rows += 1
        relation_expected[relation] += eta
        relation_patterns[relation].append({"pattern": pattern, "eta": eta})
        if pattern:
            pattern_expected[pattern] += eta

    return {
        "raw_keys": sorted(data.keys()),
        "config": data.get("config"),
        "eta_per_group": eta_per_group,
        "pattern_groups_relation_counts": {
            pattern: len(relations) for pattern, relations in sorted(pattern_groups.items())
        },
        "positive_allocation_rows": positive_rows,
        "relation_expected": dict(sorted(relation_expected.items())),
        "relation_patterns": {k: v for k, v in sorted(relation_patterns.items())},
        "pattern_expected": dict(sorted(pattern_expected.items())),
        "extraction_notes": {
            "eta_field_precedence": ["eta_integer", "eta", "eta_expected"],
            "allocation_relations_definition": "unique relations with positive extracted eta",
            "pattern_observed_definition": (
                "observed relation counts apportioned across that relation's positive "
                "allocation rows in proportion to row eta; this avoids double-counting "
                "multi-pattern relations"
            ),
        },
    }


def extract_eta(row: dict[str, Any]) -> float:
    for key in ("eta_integer", "eta", "eta_expected"):
        value = row.get(key)
        if value is not None:
            return float(value)
    return 0.0


def compare_to_allocation(graph: dict[str, Any], allocation: dict[str, Any]) -> dict[str, Any]:
    relation_counts = Counter(graph["relation_counts"])
    relation_expected = allocation["relation_expected"]
    relation_patterns = allocation["relation_patterns"]
    allocated_relations = set(relation_expected)

    per_relation: list[dict[str, Any]] = []
    total_expected = 0.0
    total_observed = 0
    total_deficit = 0.0
    total_surplus = 0.0
    observed_allocated = 0
    zero_allocated: list[str] = []

    for relation in sorted(allocated_relations):
        expected = relation_expected[relation]
        observed = int(relation_counts.get(relation, 0))
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
        per_relation.append(
            {
                "relation": relation,
                "expected_eta": expected,
                "observed_count": observed,
                "deficit": deficit,
                "surplus": surplus,
                "patterns": [p["pattern"] for p in relation_patterns.get(relation, [])],
            }
        )

    pattern_observed: dict[str, float] = defaultdict(float)
    for relation, observed in relation_counts.items():
        rows = relation_patterns.get(relation, [])
        row_eta_total = sum(row["eta"] for row in rows)
        if not rows or row_eta_total <= 0:
            continue
        for row in rows:
            pattern = row["pattern"]
            if pattern:
                pattern_observed[pattern] += observed * (row["eta"] / row_eta_total)

    pattern_level: list[dict[str, Any]] = []
    for pattern in sorted(set(allocation["pattern_expected"]) | set(pattern_observed)):
        expected = float(allocation["pattern_expected"].get(pattern, 0.0))
        observed = float(pattern_observed.get(pattern, 0.0))
        pattern_level.append(
            {
                "pattern": pattern,
                "expected_eta": expected,
                "observed_count_apportioned": observed,
                "deficit": max(expected - observed, 0.0),
                "surplus": max(observed - expected, 0.0),
            }
        )

    top_overfilled = sorted(
        (row for row in per_relation if row["surplus"] > 0),
        key=lambda row: (-row["surplus"], row["relation"]),
    )[:25]
    top_underfilled = sorted(
        (row for row in per_relation if row["deficit"] > 0),
        key=lambda row: (-row["deficit"], row["relation"]),
    )[:25]

    return {
        "relation_count_source": "unique_relation_counts",
        "triple_count_source": "unique_triples",
        "evaluation_note": "Allocation metrics are computed from unique triples.",
        "allocation_relation_count": len(allocated_relations),
        "allocated_relations_observed": observed_allocated,
        "zero_allocated_relations": len(zero_allocated),
        "zero_allocated_relation_ids": zero_allocated,
        "total_expected_eta": total_expected,
        "total_observed_allocated_triples": total_observed,
        "total_deficit": total_deficit,
        "total_surplus": total_surplus,
        "per_relation_expected_observed": per_relation,
        "pattern_level_expected_observed": pattern_level,
        "top_overfilled_relations": top_overfilled,
        "top_underfilled_relations": top_underfilled,
    }


def default_summary_path(report_path: Path) -> Path:
    name = report_path.name
    if name.endswith(".report.json"):
        return report_path.with_name(name[: -len(".report.json")] + ".summary.md")
    if report_path.suffix == ".json":
        return report_path.with_suffix(".summary.md")
    return report_path.with_suffix(report_path.suffix + ".summary.md")


def write_summary(report: dict[str, Any], summary_path: Path) -> None:
    g = report["graph_metrics"]
    a = report["allocation_metrics"]
    top_under = a["top_underfilled_relations"][:10]
    top_over = a["top_overfilled_relations"][:10]

    lines = [
        f"# Graph Candidate Summary: {report['candidate'].get('label') or report['graph_path']}",
        "",
        "## Inputs",
        "",
        f"- Graph: `{report['graph_path']}`",
        f"- Graph SHA256: `{report['graph_sha256']}`",
        f"- Allocation: `{report['allocation_path']}`",
        f"- Allocation SHA256: `{report['allocation_sha256']}`",
        "",
        "## Core Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Raw graph rows | {g['raw_total_rows']} |",
        f"| Total triples (unique, allocation basis) | {g['total_triples']} |",
        f"| Unique triples | {g['unique_triples']} |",
        f"| Duplicate triple count | {g['duplicate_triple_count']} |",
        f"| Unique entities | {g['unique_entities']} |",
        f"| Unique relations | {g['unique_relations']} |",
        f"| Weak component count | {g['weak_component_count']} |",
        f"| Largest weak component ratio | {g['largest_weak_component_ratio']:.12g} |",
        f"| Allocation relations | {a['allocation_relation_count']} |",
        f"| Allocated relations observed | {a['allocated_relations_observed']} |",
        f"| Zero allocated relations | {a['zero_allocated_relations']} |",
        f"| Total expected eta | {a['total_expected_eta']:.12g} |",
        f"| Observed allocated triples | {a['total_observed_allocated_triples']} |",
        f"| Total deficit | {a['total_deficit']:.12g} |",
        f"| Total surplus | {a['total_surplus']:.12g} |",
        "",
        "## Pattern Metrics",
        "",
        "| Pattern | Expected Eta | Observed | Deficit | Surplus |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in a["pattern_level_expected_observed"]:
        lines.append(
            "| {pattern} | {expected_eta:.12g} | {observed_count_apportioned:.12g} | "
            "{deficit:.12g} | {surplus:.12g} |".format(**row)
        )

    lines.extend(["", "## Top Underfilled Relations", "", "| Relation | Expected | Observed | Deficit |", "| --- | ---: | ---: | ---: |"])
    for row in top_under:
        lines.append(
            f"| {row['relation']} | {row['expected_eta']:.12g} | {row['observed_count']} | {row['deficit']:.12g} |"
        )

    lines.extend(["", "## Top Overfilled Relations", "", "| Relation | Expected | Observed | Surplus |", "| --- | ---: | ---: | ---: |"])
    for row in top_over:
        lines.append(
            f"| {row['relation']} | {row['expected_eta']:.12g} | {row['observed_count']} | {row['surplus']:.12g} |"
        )

    lines.extend(
        [
            "",
            "## Extraction Notes",
            "",
            "- Allocation eta field precedence: `eta_integer`, then `eta`, then `eta_expected`.",
            "- Allocation relations are unique relations with positive extracted eta.",
            "- Eta and allocation metrics use unique triples, not raw graph rows.",
            "- Pattern observed counts are apportioned by per-relation eta weights to avoid double-counting multi-pattern relations.",
            "- Connectivity, entity counts, and default relation counts are computed from unique triples.",
            "- This evaluator reads graph and allocation inputs and writes reports only; it does not modify inputs.",
            "",
        ]
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path, help="CSV or JSONL graph path")
    parser.add_argument("--allocation", required=True, type=Path, help="Allocation JSON path")
    parser.add_argument("--output-report", required=True, type=Path, help="JSON report path")
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=None,
        help="Markdown summary path; defaults beside report",
    )
    parser.add_argument("--candidate-id", default=None)
    parser.add_argument("--label", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    graph_path = args.graph
    allocation_path = args.allocation
    if not graph_path.is_file():
        raise FileNotFoundError(graph_path)
    if not allocation_path.is_file():
        raise FileNotFoundError(allocation_path)

    graph = read_graph(graph_path)
    allocation = load_allocation(allocation_path)
    allocation_metrics = compare_to_allocation(graph, allocation)

    report = {
        "candidate": {"candidate_id": args.candidate_id, "label": args.label},
        "graph_path": str(graph_path),
        "allocation_path": str(allocation_path),
        "graph_sha256": sha256_file(graph_path),
        "allocation_sha256": sha256_file(allocation_path),
        "graph_metrics": graph,
        "evaluation_notes": [
            "Allocation metrics are computed from unique triples.",
            "Raw graph rows and duplicate_triple_count are reported for duplicate-safety auditing.",
            "The input graph and allocation files are read only and are never modified.",
        ],
        "allocation_extraction": {
            "raw_keys": allocation["raw_keys"],
            "config": allocation["config"],
            "eta_per_group": allocation["eta_per_group"],
            "pattern_groups_relation_counts": allocation["pattern_groups_relation_counts"],
            "positive_allocation_rows": allocation["positive_allocation_rows"],
            "extraction_notes": allocation["extraction_notes"],
        },
        "allocation_metrics": allocation_metrics,
    }

    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary_path = args.output_summary or default_summary_path(args.output_report)
    write_summary(report, summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
