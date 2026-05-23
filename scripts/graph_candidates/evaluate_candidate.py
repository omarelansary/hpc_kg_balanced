#!/usr/bin/env python3
"""Evaluate an existing graph candidate and write standard report artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.candidate_report import evaluate_candidate  # noqa: E402
from src.kg_pipeline.registry.candidate_registry import candidate_by_id, load_registry  # noqa: E402

GENERATED_BY = "scripts/graph_candidates/evaluate_candidate.py"
MANIFEST_SCHEMA_VERSION = "kg-candidate-evaluation-manifest-v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--allocation", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--label", default=None)
    parser.add_argument("--parent-candidate-id", default=None)
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-write", action="store_true", help="Compute and print summary without writing outputs")
    return parser.parse_args()


def output_paths(out_dir: Path) -> dict[str, Path]:
    return {
        "report": out_dir / "report.json",
        "summary": out_dir / "summary.md",
        "relation_quota_report": out_dir / "relation_quota_report.tsv",
        "pattern_balance_report": out_dir / "pattern_balance_report.tsv",
        "manifest": out_dir / "manifest.json",
    }


def refuse_overwrite(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite existing output files without --force: {names}")


def fmt(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def relation_status(row: dict[str, Any]) -> str:
    if float(row["deficit"]) > 0:
        return "underfilled"
    if float(row["surplus"]) > 0:
        return "overfilled"
    return "met"


def registry_lookup(
    registry_path: Path | None,
    candidate_id: str,
    graph_path: Path,
    allocation_path: Path,
) -> dict[str, Any] | None:
    if registry_path is None:
        return None
    registry = load_registry(registry_path)
    row = candidate_by_id(registry, candidate_id)
    result: dict[str, Any] = {
        "registry_path": str(registry_path),
        "found": row is not None,
    }
    if not row:
        return result

    registered_graph = row.get("graph_path")
    registered_allocation = row.get("allocation_path")
    result.update(
        {
            "role": row.get("role"),
            "status": row.get("status"),
            "decision": row.get("decision"),
            "report_schema": row.get("report_schema"),
            "registered_graph_path": registered_graph,
            "registered_allocation_path": registered_allocation,
            "graph_path_matches": paths_match(graph_path, registered_graph),
            "allocation_path_matches": paths_match(allocation_path, registered_allocation),
        }
    )
    return result


def paths_match(observed: Path, registered: str | None) -> bool | None:
    if not registered:
        return None
    registered_path = Path(registered)
    if not registered_path.is_absolute():
        registered_path = REPO_ROOT / registered_path
    observed_path = observed if observed.is_absolute() else REPO_ROOT / observed
    try:
        return observed_path.resolve() == registered_path.resolve()
    except FileNotFoundError:
        return observed_path == registered_path


def enrich_report(
    report: dict[str, Any],
    candidate_id: str,
    label: str | None,
    parent_candidate_id: str | None,
    registry_info: dict[str, Any] | None,
) -> dict[str, Any]:
    report["candidate_id"] = candidate_id
    report["label"] = label
    report["parent_candidate_id"] = parent_candidate_id
    report["generated_by"] = GENERATED_BY
    report["candidate"] = {
        "candidate_id": candidate_id,
        "label": label,
        "parent_candidate_id": parent_candidate_id,
    }
    if registry_info is not None:
        report["registry_lookup"] = registry_info
    return report


def write_summary(report: dict[str, Any], path: Path) -> None:
    graph = report["graph_metrics"]
    allocation = report["allocation_metrics"]
    pattern_rows = allocation["pattern_level_expected_observed"]
    lines = [
        f"# Candidate Evaluation Summary: {report['candidate_id']}",
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
        f"| Raw graph rows | {graph['raw_total_rows']} |",
        f"| Unique triples | {graph['unique_triples']} |",
        f"| Duplicate triples | {graph['duplicate_triple_count']} |",
        f"| Unique entities | {graph['unique_entities']} |",
        f"| Unique relations | {graph['unique_relations']} |",
        f"| Weak components | {graph['weak_component_count']} |",
        f"| Largest weak component ratio | {fmt(graph['largest_weak_component_ratio'])} |",
        f"| Allocated relations observed | {allocation['allocated_relations_observed']} |",
        f"| Zero allocated relations | {allocation['zero_allocated_relations']} |",
        f"| Total deficit | {fmt(allocation['total_deficit'])} |",
        f"| Total surplus | {fmt(allocation['total_surplus'])} |",
        "",
        "## Pattern Balance",
        "",
        "| Pattern | Expected | Observed | Deficit | Surplus |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in pattern_rows:
        lines.append(
            "| {pattern} | {expected} | {observed} | {deficit} | {surplus} |".format(
                pattern=row["pattern"],
                expected=fmt(row["expected_eta"]),
                observed=fmt(row["observed_count_apportioned"]),
                deficit=fmt(row["deficit"]),
                surplus=fmt(row["surplus"]),
            )
        )
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- This CLI evaluates existing graph files only; it does not generate or prune graphs.",
            "- Allocation metrics use unique triples, not raw graph rows.",
            "- Pattern observed counts are eta-apportioned to avoid double-counting multi-pattern relations.",
            "- No WDQS query, LLM call, or graph artifact modification is performed.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_relation_quota_report(report: dict[str, Any], path: Path) -> None:
    rows = report["allocation_metrics"]["per_relation_expected_observed"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["relation", "expected", "observed", "surplus", "deficit", "status"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "relation": row["relation"],
                    "expected": fmt(row["expected_eta"]),
                    "observed": row["observed_count"],
                    "surplus": fmt(row["surplus"]),
                    "deficit": fmt(row["deficit"]),
                    "status": relation_status(row),
                }
            )


def write_pattern_balance_report(report: dict[str, Any], path: Path) -> None:
    rows = report["allocation_metrics"]["pattern_level_expected_observed"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["pattern", "expected", "observed", "surplus", "deficit"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "pattern": row["pattern"],
                    "expected": fmt(row["expected_eta"]),
                    "observed": fmt(row["observed_count_apportioned"]),
                    "surplus": fmt(row["surplus"]),
                    "deficit": fmt(row["deficit"]),
                }
            )


def build_manifest(
    report: dict[str, Any],
    output_files: dict[str, Path],
    candidate_id: str,
    label: str | None,
    parent_candidate_id: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "label": label,
        "parent_candidate_id": parent_candidate_id,
        "graph_path": report["graph_path"],
        "graph_sha256": report["graph_sha256"],
        "allocation_path": report["allocation_path"],
        "allocation_sha256": report["allocation_sha256"],
        "outputs": {name: str(path) for name, path in output_files.items()},
        "generated_by": GENERATED_BY,
        "notes": [
            "This command evaluates an existing graph only.",
            "No graph was generated or modified.",
            "No WDQS query was made.",
            "No LLM call was made.",
        ],
    }


def write_outputs(report: dict[str, Any], out_dir: Path, force: bool) -> dict[str, Path]:
    paths = output_paths(out_dir)
    refuse_overwrite(paths, force)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths["report"].write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_summary(report, paths["summary"])
    write_relation_quota_report(report, paths["relation_quota_report"])
    write_pattern_balance_report(report, paths["pattern_balance_report"])
    manifest = build_manifest(
        report=report,
        output_files=paths,
        candidate_id=report["candidate_id"],
        label=report.get("label"),
        parent_candidate_id=report.get("parent_candidate_id"),
    )
    paths["manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths


def print_compact_summary(report: dict[str, Any], no_write: bool) -> None:
    graph = report["graph_metrics"]
    allocation = report["allocation_metrics"]
    print(f"candidate_id={report['candidate_id']}")
    if report.get("label"):
        print(f"label={report['label']}")
    print(f"graph={report['graph_path']}")
    print(f"graph_sha256={report['graph_sha256']}")
    print(f"allocation={report['allocation_path']}")
    print(f"allocation_sha256={report['allocation_sha256']}")
    print(
        "metrics="
        f"unique_triples={graph['unique_triples']}, "
        f"unique_entities={graph['unique_entities']}, "
        f"unique_relations={graph['unique_relations']}, "
        f"weak_components={graph['weak_component_count']}, "
        f"largest_weak_component_ratio={fmt(graph['largest_weak_component_ratio'])}, "
        f"duplicate_triples={graph['duplicate_triple_count']}, "
        f"total_surplus={fmt(allocation['total_surplus'])}, "
        f"total_deficit={fmt(allocation['total_deficit'])}"
    )
    print(f"no_write={str(no_write).lower()}")


def main() -> int:
    args = parse_args()
    if not args.graph.is_file():
        raise FileNotFoundError(args.graph)
    if not args.allocation.is_file():
        raise FileNotFoundError(args.allocation)
    if args.registry is not None and not args.registry.is_file():
        raise FileNotFoundError(args.registry)

    registry_info = registry_lookup(
        registry_path=args.registry,
        candidate_id=args.candidate_id,
        graph_path=args.graph,
        allocation_path=args.allocation,
    )
    report = evaluate_candidate(
        graph_path=args.graph,
        allocation_path=args.allocation,
        candidate_id=args.candidate_id,
        label=args.label,
    )
    enrich_report(
        report=report,
        candidate_id=args.candidate_id,
        label=args.label,
        parent_candidate_id=args.parent_candidate_id,
        registry_info=registry_info,
    )

    if args.no_write:
        print_compact_summary(report, no_write=True)
        return 0

    paths = write_outputs(report, args.out_dir, args.force)
    print_compact_summary(report, no_write=False)
    print("outputs=" + ", ".join(f"{name}:{path}" for name, path in paths.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
