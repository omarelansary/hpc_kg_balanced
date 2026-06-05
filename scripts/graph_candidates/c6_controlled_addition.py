#!/usr/bin/env python3
"""C6.1 deterministic observed canonical addition-only generator."""

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
    read_census,
    select_additions,
    sha256_file,
    write_csv_rows,
    write_graph_csv,
    write_graph_jsonl,
    write_json,
)


DEFAULT_CONFIG = {
    "mode": "internal_only",
    "max_additions": 2000,
    "allowed_candidate_classes": ["internal"],
    "require_allocated_relation": True,
    "allow_auxiliary": False,
    "allow_synthetic": False,
    "preserve_connected": True,
    "preserve_relation_coverage": True,
    "composition_addition_policy": "penalize_or_forbid_if_overfilled",
    "new_entity_budget": 0,
    "random_seed": 0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir")
    parser.add_argument("--graph", default=str(DEFAULT_B0_GRAPH))
    parser.add_argument("--allocation", default=str(DEFAULT_ALLOCATION))
    parser.add_argument("--census")
    parser.add_argument("--config")
    parser.add_argument("--max-additions", type=int)
    parser.add_argument("--mode")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_config(path: str | None) -> dict:
    config = dict(DEFAULT_CONFIG)
    if path:
        config.update(json.loads(Path(path).read_text(encoding="utf-8")))
    return config


def main() -> int:
    args = parse_args()
    run_dir = ensure_run_dir(args.run_id, args.run_dir)
    census_path = Path(args.census) if args.census else run_dir / "c6_candidate_census.csv"
    config = load_config(args.config)
    if args.max_additions is not None:
        config["max_additions"] = args.max_additions
    if args.mode:
        config["mode"] = args.mode
        if args.mode == "internal_then_semi_internal":
            config["allowed_candidate_classes"] = ["internal", "semi_internal"]
            config.setdefault("new_entity_budget", 500)

    if args.dry_run:
        print(json.dumps({"status": "dry_run", "run_dir": str(run_dir), "config": config}, indent=2))
        return 0

    if not census_path.exists():
        raise FileNotFoundError(f"missing census file: {census_path}")
    b0_records = load_graph_records(args.graph)
    b0_triples = [record.triple for record in b0_records]
    allocation = load_allocation(args.allocation)
    before_metrics = compute_graph_metrics(b0_triples, allocation)
    census_rows = read_census(census_path)
    additions, rejection_reasons = select_additions(census_rows, b0_triples, allocation, config)
    added_records = list(b0_records) + additions
    added_triples = [record.triple for record in added_records]
    after_metrics = compute_graph_metrics(added_triples, allocation)

    additions_csv = [
        {
            "h": record.h,
            "r": record.r,
            "t": record.t,
            "candidate_score": record.provenance.get("candidate_score"),
            "candidate_class": record.provenance.get("candidate_class"),
            "pattern_memberships": record.provenance.get("pattern_memberships"),
            "source_path": record.provenance.get("source_path"),
            "source_line": record.provenance.get("source_line"),
        }
        for record in additions
    ]
    by_relation = Counter(record.r for record in additions)
    by_pattern = Counter()
    for record in additions:
        memberships = str(record.provenance.get("pattern_memberships") or "").split("|")
        for membership in memberships:
            if membership:
                by_pattern[membership] += 1

    write_graph_jsonl(run_dir / "c6_added_graph.jsonl", added_records)
    write_graph_csv(run_dir / "c6_added_graph.csv", added_records)
    write_csv_rows(
        run_dir / "c6_additions.csv",
        additions_csv,
        [
            "h",
            "r",
            "t",
            "candidate_score",
            "candidate_class",
            "pattern_memberships",
            "source_path",
            "source_line",
        ],
    )
    report = {
        "schema_version": f"{SCHEMA_VERSION}.controlled-addition",
        "input_paths": {
            "graph": args.graph,
            "allocation": args.allocation,
            "census": str(census_path),
        },
        "input_hashes": {
            "graph": sha256_file(args.graph),
            "allocation": sha256_file(args.allocation),
            "census": sha256_file(census_path),
        },
        "config": config,
        "before_metrics": before_metrics,
        "after_metrics": after_metrics,
        "candidates_considered": len(census_rows),
        "accepted_additions": len(additions),
        "rejection_reasons": rejection_reasons,
        "additions_by_relation": dict(sorted(by_relation.items())),
        "additions_by_pattern": dict(sorted(by_pattern.items())),
        "internal_additions": sum(1 for row in additions_csv if row["candidate_class"] == "internal"),
        "semi_internal_additions": sum(1 for row in additions_csv if row["candidate_class"] == "semi_internal"),
        "external_additions": sum(1 for row in additions_csv if row["candidate_class"] == "external"),
        "claim_boundary": (
            "Addition-only can improve underfilled patterns and density, but does not directly "
            "remove existing composition surplus."
        ),
    }
    write_json(run_dir / "c6_addition_report.json", report)
    print(
        json.dumps(
            {
                "status": "passed",
                "run_dir": str(run_dir),
                "accepted_additions": len(additions),
                "weak_component_count": after_metrics["weak_component_count"],
                "allocated_relation_coverage_count": after_metrics["allocated_relation_coverage_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

