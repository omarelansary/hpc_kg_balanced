#!/usr/bin/env python3
"""Run a bounded C5-H2 auxiliary-edge cap sweep."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.allocation_metrics import load_allocation  # noqa: E402
from src.kg_pipeline.evaluation.candidate_report import sha256_file  # noqa: E402
from src.kg_pipeline.evaluation.graph_io import load_graph_triples  # noqa: E402
from tools.graph_candidate_generation import c5_generate_h2_auxiliary_connectivity_candidate as gen  # noqa: E402

CAPS = (10, 25, 50, 100, 151)
EXPERIMENT_DIR = Path("experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix")
CAP_SWEEP_DIR = EXPERIMENT_DIR / "cap_sweep"
REPORT_DIR = EXPERIMENT_DIR / "reports" / "cap_sweep"
REPORT_JSON = REPORT_DIR / "cap_sweep_report.json"
REPORT_MD = REPORT_DIR / "cap_sweep_summary.md"
REPORT_TSV = REPORT_DIR / "cap_sweep_table.tsv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=gen.DEFAULT_CONFIG)
    parser.add_argument("--policy", type=Path, default=gen.DEFAULT_POLICY)
    parser.add_argument("--caps", nargs="+", type=int, default=list(CAPS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def cap_paths(cap: int) -> dict[str, Path]:
    base = CAP_SWEEP_DIR / f"cap_{cap}"
    output_dir = base / "outputs"
    report_dir = base / "reports"
    return {
        "graph": output_dir / "graph.jsonl",
        "canonical_edges": output_dir / "canonical_edges.jsonl",
        "auxiliary_edges": output_dir / "auxiliary_edges.jsonl",
        "removed_canonical_edges": output_dir / "removed_canonical_edges.jsonl",
        "report": report_dir / "report.json",
        "summary": report_dir / "summary.md",
        "relation_quota_report": report_dir / "relation_quota_report.tsv",
        "pattern_balance_report": report_dir / "pattern_balance_report.tsv",
        "manifest": report_dir / "manifest.json",
        "auxiliary_edge_report": report_dir / "auxiliary_edge_report.tsv",
        "removed_edge_report": report_dir / "removed_edge_report.tsv",
    }


def all_output_paths(caps: list[int]) -> list[Path]:
    paths = [REPORT_JSON, REPORT_MD, REPORT_TSV]
    for cap in caps:
        paths.extend(cap_paths(cap).values())
    return paths


def refuse_overwrite(paths: list[Path], force: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing[:20])
        suffix = "" if len(existing) <= 20 else f" and {len(existing) - 20} more"
        raise FileExistsError(f"Refusing to overwrite C5-H2 cap sweep outputs without --force: {names}{suffix}")


def ensure_parents(paths: dict[str, Path]) -> None:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)


def classify_cap(report: dict[str, Any] | None, error: str | None = None) -> str:
    if error:
        return "generator_error"
    if report is None:
        return "generator_error"
    classification = report.get("acceptance_classification")
    if classification == "c5_h2_candidate_passed_policy":
        return "passed_policy"
    if classification == "c5_h2_no_moves_selected":
        return "no_moves_selected"
    return "failed_policy"


def cap_row(cap: int, report: dict[str, Any] | None, paths: dict[str, Path], error: str | None = None) -> dict[str, Any]:
    if report is None:
        return {
            "cap": cap,
            "status": classify_cap(report, error),
            "error": error,
        }
    selection = report["selection_summary"]
    full_graph = report["evaluation"]["full_graph"]["graph_metrics"]
    canonical_graph = report["evaluation"]["canonical_only"]["graph_metrics"]
    edge_accounting = report["edge_accounting"]
    aux_dist = edge_accounting["auxiliary_relation_distribution"]
    aux_count = int(edge_accounting["auxiliary_unallocated_observed_edges"])
    p17_count = int(aux_dist.get("P17", 0))
    p17_share = p17_count / aux_count if aux_count else 0.0
    return {
        "cap": cap,
        "status": classify_cap(report, error),
        "acceptance_classification": report["acceptance_classification"],
        "auxiliary_edges_selected": selection["selected_auxiliary_edges"],
        "canonical_edges_removed": selection["removed_canonical_edges"],
        "canonical_surplus_delta": selection["canonical_surplus_delta"],
        "canonical_deficit_delta": selection["canonical_deficit_delta"],
        "full_graph_weak_components": full_graph["weak_component_count"],
        "canonical_only_weak_components": canonical_graph["weak_component_count"],
        "full_graph_triples": full_graph["unique_triples"],
        "canonical_only_triples": canonical_graph["unique_triples"],
        "auxiliary_relation_count": edge_accounting["unallocated_auxiliary_relation_count"],
        "auxiliary_relation_distribution": aux_dist,
        "p17_auxiliary_count": p17_count,
        "p17_share": p17_share,
        "graph_sha256": edge_accounting["graph_sha256"],
        "auxiliary_edges_sha256": edge_accounting["auxiliary_edges_sha256"],
        "removed_edges_sha256": edge_accounting["removed_canonical_edges_sha256"],
        "report_path": str(paths["report"]),
        "manifest_path": str(paths["manifest"]),
    }


def generate_cap(
    cap: int,
    config_path: Path,
    policy_path: Path,
    config: dict[str, Any],
    policy: dict[str, Any],
    c5_report: dict[str, Any],
    score_audit: dict[str, Any],
    c4_2_report: dict[str, Any],
    graph_triples: set[tuple[str, str, str]],
    allocation: dict[str, Any],
    moves: list[dict[str, Any]],
    scan_metadata: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Path]]:
    paths = cap_paths(cap)
    ensure_parents(paths)
    started = time.time()
    selection_result = gen.select_moves(moves, graph_triples, allocation, policy, cap)
    selection_result["candidate_moves_available"] = moves
    rows = gen.edge_rows(
        selection_result["canonical_triples"],
        selection_result["selected"],
        selection_result["selected"],
    )
    gen.write_jsonl(paths["graph"], rows["graph"])
    gen.write_jsonl(paths["canonical_edges"], rows["canonical_edges"])
    gen.write_jsonl(paths["auxiliary_edges"], rows["auxiliary_edges"])
    gen.write_jsonl(paths["removed_canonical_edges"], rows["removed_canonical_edges"])
    finished = time.time()
    report = gen.build_report(
        args=SimpleNamespace(max_auxiliary_edges=cap),
        config_path=config_path,
        policy_path=policy_path,
        config=config,
        policy=policy,
        c5_report=c5_report,
        score_audit=score_audit,
        c4_2_report=c4_2_report,
        scan_metadata=scan_metadata,
        selection_result=selection_result,
        paths=paths,
        started=started,
        finished=finished,
    )
    gen.write_outputs(paths, rows, report)
    return report, paths


def recommendation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    passed = [row for row in rows if row.get("status") == "passed_policy"]
    if not passed:
        return {
            "recommendation": "reject_C5_H2",
            "best_cap": None,
            "reason": "No tested cap passed the C5-H2 policy.",
        }

    for row in passed:
        row["surplus_reduction_per_auxiliary"] = (
            abs(float(row["canonical_surplus_delta"])) / max(int(row["auxiliary_edges_selected"]), 1)
        )
        row["p17_penalty"] = float(row["p17_share"])
        row["fragmentation_penalty"] = int(row["canonical_only_weak_components"])

    low_cost = min(passed, key=lambda row: (int(row["auxiliary_edges_selected"]), -row["surplus_reduction_per_auxiliary"]))
    best_surplus = min(passed, key=lambda row: (float(row["canonical_surplus_delta"]), int(row["auxiliary_edges_selected"])))
    high_concentration = any(float(row["p17_share"]) >= 0.75 for row in passed)
    tiny_improvement = abs(float(best_surplus["canonical_surplus_delta"])) / 6702.0 < 0.05
    high_fragmentation = all(int(row["canonical_only_weak_components"]) > 1 for row in passed)

    if tiny_improvement or high_concentration or high_fragmentation:
        rec = "continue_with_diversity_penalty"
        reason = (
            "All passing caps remain auxiliary-dependent; improvement is small relative to B0 surplus and P17 "
            "concentration remains high."
        )
    else:
        rec = "register_low_cap_experimental_candidate"
        reason = "A low cap offers a meaningful surplus improvement without severe auxiliary concentration."

    return {
        "recommendation": rec,
        "best_cap": low_cost["cap"],
        "best_surplus_cap": best_surplus["cap"],
        "reason": reason,
        "registry_update_supported": False,
        "notes": [
            "Do not claim canonical allocation-faithful improvement.",
            "A registry update still requires human decision and artifact preservation.",
        ],
    }


def write_table(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "cap",
        "status",
        "acceptance_classification",
        "auxiliary_edges_selected",
        "canonical_edges_removed",
        "canonical_surplus_delta",
        "canonical_deficit_delta",
        "full_graph_weak_components",
        "canonical_only_weak_components",
        "full_graph_triples",
        "canonical_only_triples",
        "auxiliary_relation_count",
        "p17_auxiliary_count",
        "p17_share",
        "graph_sha256",
        "auxiliary_edges_sha256",
        "removed_edges_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_summary(path: Path, rows: list[dict[str, Any]], rec: dict[str, Any]) -> None:
    lines = [
        "# C5-H2 Auxiliary Cap Sweep",
        "",
        f"Recommendation: `{rec['recommendation']}`",
        "",
        "| Cap | Status | Aux edges | Surplus delta | Deficit delta | Full WCC | Canonical WCC | P17 count | P17 share |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {cap} | `{status}` | {aux} | {surplus} | {deficit} | {full_wcc} | {canon_wcc} | {p17} | {share:.3f} |".format(
                cap=row.get("cap"),
                status=row.get("status"),
                aux=row.get("auxiliary_edges_selected", ""),
                surplus=row.get("canonical_surplus_delta", ""),
                deficit=row.get("canonical_deficit_delta", ""),
                full_wcc=row.get("full_graph_weak_components", ""),
                canon_wcc=row.get("canonical_only_weak_components", ""),
                p17=row.get("p17_auxiliary_count", ""),
                share=float(row.get("p17_share") or 0.0),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            rec["reason"],
            "",
            "The sweep supports preserving C5-H2 as experimental evidence, but it does not support a registry update yet.",
            "Auxiliary edges remain unallocated observed support and are not canonical benchmark triples.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    caps = list(dict.fromkeys(args.caps))
    config_path = gen.resolve_path(args.config)
    policy_path = gen.resolve_path(args.policy)
    config = gen.load_c5_config(config_path)
    gen.validate_config(config)
    policy = gen.load_policy(policy_path)
    for cap in caps:
        if cap <= 0:
            raise ValueError(f"Invalid cap: {cap}")
        if cap > int(policy["thresholds"]["max_auxiliary_edges_probe_upper_bound"]):
            raise ValueError(f"Cap {cap} exceeds policy probe upper bound")

    if args.dry_run:
        print("dry_run=true")
        print("caps=" + ",".join(str(cap) for cap in caps))
        for cap in caps:
            print(f"cap_{cap}_dir={CAP_SWEEP_DIR / f'cap_{cap}'}")
        print(f"summary_report={REPORT_JSON}")
        print("outputs_written=false")
        return 0

    refuse_overwrite(all_output_paths(caps), args.force)
    started = time.time()
    c5_report = gen.load_json(gen.resolve_path(gen.DEFAULT_C5_REPORT))
    score_audit = gen.load_json(gen.resolve_path(gen.DEFAULT_SCORE_AUDIT))
    c4_2_report = gen.load_json(gen.resolve_path(gen.DEFAULT_C4_2_REPORT))
    graph_triples = set(load_graph_triples(gen.resolve_path(config["parent_graph_path"])))
    allocation = load_allocation(gen.resolve_path(config["allocation_path"]))
    moves, scan_metadata = gen.build_h2_moves(config, c5_report)

    rows: list[dict[str, Any]] = []
    for cap in caps:
        try:
            report, paths = generate_cap(
                cap,
                config_path,
                policy_path,
                config,
                policy,
                c5_report,
                score_audit,
                c4_2_report,
                graph_triples,
                allocation,
                moves,
                scan_metadata,
            )
            rows.append(cap_row(cap, report, paths))
        except Exception as exc:  # pragma: no cover - reported to JSON for auditability.
            rows.append(cap_row(cap, None, cap_paths(cap), error=str(exc)))

    rec = recommendation(rows)
    finished = time.time()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "c5-h2-cap-sweep-report-v1",
        "sweep_id": "C5_H2_auxiliary_cap_sweep",
        "candidate_id": config["candidate_id"],
        "parent_candidate_id": config["parent_candidate_id"],
        "caps": caps,
        "status": "cap_sweep_completed",
        "inputs": {
            "config": {"path": gen.repo_relative(config_path), "sha256": sha256_file(config_path)},
            "policy": {"path": gen.repo_relative(policy_path), "sha256": sha256_file(policy_path)},
            "generator": {
                "path": "tools/graph_candidate_generation/c5_generate_h2_auxiliary_connectivity_candidate.py",
                "sha256": sha256_file(REPO_ROOT / "tools/graph_candidate_generation/c5_generate_h2_auxiliary_connectivity_candidate.py"),
            },
        },
        "candidate_moves_available": len(moves),
        "rows": rows,
        "recommendation": rec,
        "notes": [
            "No WDQS query was made.",
            "No LLM call was made.",
            "No synthetic triples were created.",
            "candidate_registry.v1.json was not updated.",
            "C5-H2 auxiliary unallocated observed edges are not canonical benchmark triples.",
        ],
        "runtime": {
            "started_on": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "finished_on": datetime.fromtimestamp(finished, timezone.utc).isoformat(),
            "elapsed_seconds": round(finished - started, 6),
        },
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_table(REPORT_TSV, rows)
    write_summary(REPORT_MD, rows, rec)

    print(f"cap_sweep_report={REPORT_JSON}")
    print(f"cap_sweep_table={REPORT_TSV}")
    print(f"recommendation={rec['recommendation']}")
    for row in rows:
        print(
            "cap={cap}\tstatus={status}\taux={aux}\tsurplus_delta={surplus}\t"
            "deficit_delta={deficit}\tp17_share={share:.3f}".format(
                cap=row.get("cap"),
                status=row.get("status"),
                aux=row.get("auxiliary_edges_selected", ""),
                surplus=row.get("canonical_surplus_delta", ""),
                deficit=row.get("canonical_deficit_delta", ""),
                share=float(row.get("p17_share") or 0.0),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
