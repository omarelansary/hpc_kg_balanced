#!/usr/bin/env python3
"""C6.3 redundancy audit for safe deletion candidates after additions."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from c6_common import (
    DEFAULT_ALLOCATION,
    DEFAULT_B0_GRAPH,
    SCHEMA_VERSION,
    compute_graph_metrics,
    ensure_run_dir,
    load_allocation,
    load_graph_records,
    safe_deletion_rows,
    sha256_file,
    write_csv_rows,
    write_json,
)


FIELDNAMES = [
    "h",
    "r",
    "t",
    "patterns",
    "relation_surplus_before_b0",
    "relation_surplus_after_addition",
    "relation_overfilled",
    "pattern_overfilled",
    "pair_count_after_addition",
    "bridge_before_additions",
    "bridge_after_additions",
    "safe_before_additions",
    "safe_after_additions",
    "safe_after_not_before",
    "surplus_reduction_score",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir")
    parser.add_argument("--graph", default=str(DEFAULT_B0_GRAPH))
    parser.add_argument("--allocation", default=str(DEFAULT_ALLOCATION))
    parser.add_argument("--added-graph")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = ensure_run_dir(args.run_id, args.run_dir)
    added_graph = Path(args.added_graph) if args.added_graph else run_dir / "c6_added_graph.jsonl"
    if args.dry_run:
        print(json.dumps({"status": "dry_run", "run_dir": str(run_dir), "added_graph": str(added_graph)}, indent=2))
        return 0
    if not added_graph.exists():
        raise FileNotFoundError(f"missing added graph: {added_graph}")
    allocation = load_allocation(args.allocation)
    b0_records = load_graph_records(args.graph)
    added_records = load_graph_records(added_graph, source="c6_added_graph")
    rows = safe_deletion_rows(b0_records, added_records, allocation)
    by_relation = Counter(row["r"] for row in rows)
    before_metrics = compute_graph_metrics([record.triple for record in b0_records], allocation)
    after_addition_metrics = compute_graph_metrics([record.triple for record in added_records], allocation)
    write_csv_rows(run_dir / "c6_safe_deletion_candidates.csv", rows, FIELDNAMES)
    report = {
        "schema_version": f"{SCHEMA_VERSION}.redundancy-audit",
        "input_paths": {
            "b0_graph": args.graph,
            "added_graph": str(added_graph),
            "allocation": args.allocation,
        },
        "input_hashes": {
            "b0_graph": sha256_file(args.graph),
            "added_graph": sha256_file(added_graph),
            "allocation": sha256_file(args.allocation),
        },
        "before_metrics": before_metrics,
        "after_addition_metrics": after_addition_metrics,
        "safe_deletion_candidate_count": len(rows),
        "safe_after_not_before_count": sum(1 for row in rows if row["safe_after_not_before"]),
        "safe_deletion_candidates_by_relation": dict(sorted(by_relation.items())),
        "audit_note": (
            "A row is structurally safe after additions if removing the triple leaves the "
            "undirected entity projection connected. Final deletion still rechecks constraints cumulatively."
        ),
    }
    write_json(run_dir / "c6_redundancy_audit.json", report)
    print(
        json.dumps(
            {
                "status": "passed",
                "run_dir": str(run_dir),
                "safe_deletion_candidate_count": len(rows),
                "safe_after_not_before_count": report["safe_after_not_before_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

