#!/usr/bin/env python3
"""C6.0 frozen observed candidate census."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from c6_common import (
    DEFAULT_ALLOCATION,
    DEFAULT_B0_GRAPH,
    DEFAULT_CANDIDATE_GLOB,
    SCHEMA_VERSION,
    candidate_score,
    classify_candidate,
    common_neighbor_count,
    compute_graph_metrics,
    count_entities,
    count_relations,
    discover_default_inputs,
    ensure_run_dir,
    iter_candidate_rows,
    load_allocation,
    load_graph_records,
    pair_counts,
    pattern_status,
    relation_eta_map,
    relation_pattern_map,
    relation_status,
    sha256_file,
    validate_discovered_inputs,
    write_csv_rows,
    write_json,
)


FIELDNAMES = [
    "h",
    "r",
    "t",
    "candidate_class",
    "allocated_relation_flag",
    "relation_eta",
    "relation_observed_count_in_B0",
    "relation_deficit_before",
    "relation_surplus_before",
    "pattern_memberships",
    "underfilled_relation_flag",
    "underfilled_pattern_flag",
    "composition_relation_flag",
    "symmetric_relation_flag",
    "introduces_new_entities_count",
    "endpoint_degree_h",
    "endpoint_degree_t",
    "existing_pair_flag",
    "local_common_neighbors_count",
    "creates_duplicate_flag",
    "candidate_score",
    "relation_deficit_gain",
    "pattern_deficit_gain",
    "symmetric_underfill_gain",
    "existing_endpoint_score",
    "local_common_neighbors_score",
    "alternative_path_or_wedge_score",
    "composition_overfill_penalty",
    "generic_relation_penalty",
    "new_entity_penalty",
    "source_path",
    "source_line",
    "source_stage",
    "source_backend",
    "genericity_score",
    "quality_score",
    "triple_id",
]


def build_census(
    graph_path: Path,
    allocation_path: Path,
    candidate_glob: str,
    max_candidates: int | None,
) -> tuple[list[dict], dict]:
    b0_records = load_graph_records(graph_path)
    b0_triples = [record.triple for record in b0_records]
    b0_set = set(b0_triples)
    b0_entities = {entity for h, _r, t in b0_triples for entity in (h, t)}
    relation_counts = count_relations(b0_triples)
    allocation = load_allocation(allocation_path)
    relation_eta = relation_eta_map(allocation)
    pattern_map = relation_pattern_map(allocation)
    b0_metrics = compute_graph_metrics(b0_triples, allocation)
    pair_count_map = pair_counts(b0_triples)

    import networkx as nx

    graph = nx.Graph()
    graph.add_edges_from((h, t) for h, _r, t in b0_triples)
    degree = dict(graph.degree())

    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    class_counts: Counter[str] = Counter()
    rejection_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()

    for row in iter_candidate_rows(candidate_glob, max_candidates=max_candidates):
        triple = (str(row["h"]), str(row["r"]), str(row["t"]))
        if triple in seen:
            rejection_counts["duplicate_candidate_row"] += 1
            continue
        seen.add(triple)
        candidate_class = classify_candidate(triple[0], triple[2], b0_entities)
        patterns = pattern_map.get(triple[1], [])
        status = relation_status(triple[1], relation_counts, relation_eta)
        pstatus = pattern_status(patterns, b0_metrics)
        out = {
            "h": triple[0],
            "r": triple[1],
            "t": triple[2],
            "candidate_class": candidate_class,
            "allocated_relation_flag": triple[1] in relation_eta,
            "introduces_new_entities_count": count_entities([triple]) - len(
                {entity for entity in (triple[0], triple[2]) if entity in b0_entities}
            ),
            "endpoint_degree_h": degree.get(triple[0], 0),
            "endpoint_degree_t": degree.get(triple[2], 0),
            "existing_pair_flag": pair_count_map.get(tuple(sorted((triple[0], triple[2]))), 0) > 0,
            "local_common_neighbors_count": common_neighbor_count(graph, triple[0], triple[2]),
            "creates_duplicate_flag": triple in b0_set,
            "source_path": row.get("_source_path"),
            "source_line": row.get("_source_line"),
            "source_stage": row.get("source_stage"),
            "source_backend": row.get("source_backend"),
            "genericity_score": row.get("genericity_score"),
            "quality_score": row.get("quality_score"),
            "triple_id": row.get("triple_id"),
            **status,
            **pstatus,
        }
        out.update(candidate_score(out))
        rows.append(out)
        class_counts[candidate_class] += 1
        source_counts[str(row.get("_source_path"))] += 1

    summary = {
        "schema_version": f"{SCHEMA_VERSION}.candidate-census",
        "graph_path": str(graph_path),
        "graph_sha256": sha256_file(graph_path),
        "allocation_path": str(allocation_path),
        "allocation_sha256": sha256_file(allocation_path),
        "candidate_glob": candidate_glob,
        "max_candidates": max_candidates,
        "candidate_rows": len(rows),
        "candidate_class_counts": dict(sorted(class_counts.items())),
        "allocated_candidate_rows": sum(1 for row in rows if row["allocated_relation_flag"]),
        "underfilled_relation_rows": sum(1 for row in rows if row["underfilled_relation_flag"]),
        "underfilled_pattern_rows": sum(1 for row in rows if row["underfilled_pattern_flag"]),
        "symmetric_candidate_rows": sum(1 for row in rows if row["symmetric_relation_flag"]),
        "composition_candidate_rows": sum(1 for row in rows if row["composition_relation_flag"]),
        "duplicate_candidate_rows_rejected": rejection_counts.get("duplicate_candidate_row", 0),
        "source_file_count_with_rows": len(source_counts),
        "top_source_files": source_counts.most_common(10),
        "b0_metrics": {
            "total_triples": b0_metrics["total_triples"],
            "total_entities": b0_metrics["total_entities"],
            "weak_component_count": b0_metrics["weak_component_count"],
            "allocated_relation_coverage_count": b0_metrics["allocated_relation_coverage_count"],
            "total_surplus": b0_metrics["total_surplus"],
            "total_deficit": b0_metrics["total_deficit"],
            "composition_total": b0_metrics["composition_total"],
            "symmetric_deficit": b0_metrics["symmetric_deficit"],
        },
    }
    return rows, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir")
    parser.add_argument("--graph", default=str(DEFAULT_B0_GRAPH))
    parser.add_argument("--allocation", default=str(DEFAULT_ALLOCATION))
    parser.add_argument("--candidate-glob", default=DEFAULT_CANDIDATE_GLOB)
    parser.add_argument("--max-candidates", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inputs = discover_default_inputs()
    missing = validate_discovered_inputs(inputs)
    if missing:
        print(json.dumps({"status": "blocked_missing_inputs", "missing": missing}, indent=2))
        return 1
    run_dir = ensure_run_dir(args.run_id, args.run_dir)
    max_candidates = args.max_candidates if args.max_candidates > 0 else None
    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "dry_run",
                    "run_dir": str(run_dir),
                    "graph": args.graph,
                    "allocation": args.allocation,
                    "candidate_glob": args.candidate_glob,
                    "max_candidates": max_candidates,
                    "discovered_inputs": inputs,
                },
                indent=2,
            )
        )
        return 0
    rows, summary = build_census(
        Path(args.graph),
        Path(args.allocation),
        args.candidate_glob,
        max_candidates,
    )
    write_csv_rows(run_dir / "c6_candidate_census.csv", rows, FIELDNAMES)
    write_json(run_dir / "c6_candidate_census_summary.json", summary)
    print(
        json.dumps(
            {
                "status": "passed",
                "run_dir": str(run_dir),
                "candidate_rows": summary["candidate_rows"],
                "candidate_class_counts": summary["candidate_class_counts"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

