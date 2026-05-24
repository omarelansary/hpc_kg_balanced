#!/usr/bin/env python3
"""Probe C5-H2 diversity-aware auxiliary move reranking."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.allocation_metrics import load_allocation  # noqa: E402
from src.kg_pipeline.evaluation.candidate_report import sha256_file  # noqa: E402
from src.kg_pipeline.evaluation.graph_io import Triple, load_graph_triples  # noqa: E402
from tools.graph_candidate_generation import c5_generate_h2_auxiliary_connectivity_candidate as gen  # noqa: E402

CAPS = (25, 50, 100, 151)
STRATEGIES = (
    "baseline_current_ranking",
    "p17_cap_25_percent",
    "p17_cap_40_percent",
    "max_per_aux_relation_10",
    "max_per_aux_relation_20",
    "relation_diversity_penalty_light",
    "relation_diversity_penalty_strong",
)
EXPERIMENT_DIR = Path("experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix")
DIVERSITY_PROBE_DIR = EXPERIMENT_DIR / "diversity_probe"
REPORT_DIR = EXPERIMENT_DIR / "reports" / "diversity_reranking"
REPORT_JSON = REPORT_DIR / "diversity_reranking_report.json"
REPORT_MD = REPORT_DIR / "diversity_reranking_summary.md"
REPORT_TSV = REPORT_DIR / "diversity_reranking_table.tsv"
CAP_SWEEP_REPORT = EXPERIMENT_DIR / "reports/cap_sweep/cap_sweep_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=gen.DEFAULT_CONFIG)
    parser.add_argument("--policy", type=Path, default=gen.DEFAULT_POLICY)
    parser.add_argument("--cap-sweep-report", type=Path, default=CAP_SWEEP_REPORT)
    parser.add_argument("--caps", nargs="+", type=int, default=list(CAPS))
    parser.add_argument("--strategies", nargs="+", default=list(STRATEGIES))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def run_paths(strategy: str, cap: int) -> dict[str, Path]:
    base = DIVERSITY_PROBE_DIR / strategy / f"cap_{cap}"
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


def all_output_paths(strategies: list[str], caps: list[int]) -> list[Path]:
    paths = [REPORT_JSON, REPORT_MD, REPORT_TSV]
    for strategy in strategies:
        for cap in caps:
            paths.extend(run_paths(strategy, cap).values())
    return paths


def refuse_overwrite(paths: list[Path], force: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing[:20])
        suffix = "" if len(existing) <= 20 else f" and {len(existing) - 20} more"
        raise FileExistsError(f"Refusing to overwrite diversity probe outputs without --force: {names}{suffix}")


def ensure_parents(paths: dict[str, Path]) -> None:
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)


def triple_key(edge: dict[str, str]) -> Triple:
    return edge["h"], edge["r"], edge["t"]


def strategy_relation_allowed(strategy: str, relation_counts: Counter[str], relation: str, cap: int) -> bool:
    if strategy == "p17_cap_25_percent" and relation == "P17":
        return relation_counts[relation] < math.floor(cap * 0.25)
    if strategy == "p17_cap_40_percent" and relation == "P17":
        return relation_counts[relation] < math.floor(cap * 0.40)
    if strategy == "max_per_aux_relation_10":
        return relation_counts[relation] < 10
    if strategy == "max_per_aux_relation_20":
        return relation_counts[relation] < 20
    return True


def strategy_rank(move: dict[str, Any], strategy: str, relation_counts: Counter[str]) -> tuple[Any, ...]:
    target = triple_key(move["target_edge"])
    candidate = triple_key(move["candidate"])
    relation = candidate[1]
    surplus_delta = float(move["canonical_surplus_delta"])
    deficit_delta = float(move["canonical_deficit_delta"])
    duplicate_strength = int(move.get("duplicate_provenance_count") or 0)
    base_tail = (
        -duplicate_strength,
        move.get("source_stage") or "",
        move.get("provenance_type") or "",
        int(move["cut_id"]),
        target,
        candidate,
    )
    if strategy == "relation_diversity_penalty_light":
        return (surplus_delta, deficit_delta, relation_counts[relation], relation, *base_tail)
    if strategy == "relation_diversity_penalty_strong":
        return (surplus_delta, deficit_delta, relation_counts[relation] * 10, relation_counts[relation], relation, *base_tail)
    return gen.rank_move(move)


def select_moves_with_strategy(
    moves: list[dict[str, Any]],
    graph_triples: set[Triple],
    allocation: dict[str, Any],
    policy: dict[str, Any],
    cap: int,
    strategy: str,
) -> dict[str, Any]:
    relation_expected = allocation["relation_expected"]
    canonical_triples = set(graph_triples)
    auxiliary_triples: set[Triple] = set()
    canonical_relation_counts = Counter(r for _h, r, _t in canonical_triples)
    auxiliary_relation_counts: Counter[str] = Counter()
    baseline_metrics = gen.compare_relation_counts_to_allocation(canonical_relation_counts, allocation)
    baseline_surplus = float(baseline_metrics["total_surplus"])
    baseline_deficit = float(baseline_metrics["total_deficit"])
    thresholds = policy["thresholds"]
    selected: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    used_targets: set[Triple] = set()
    used_candidates: set[Triple] = set()
    remaining = list(moves)

    while len(selected) < cap and remaining:
        picked_index: int | None = None
        ordered = sorted(enumerate(remaining), key=lambda item: strategy_rank(item[1], strategy, auxiliary_relation_counts))
        for index, move in ordered:
            target = triple_key(move["target_edge"])
            candidate = triple_key(move["candidate"])
            relation = candidate[1]
            if target in used_targets:
                skipped["target_edge_already_used"] += 1
                picked_index = index
                break
            if candidate in used_candidates:
                skipped["auxiliary_candidate_already_used"] += 1
                picked_index = index
                break
            if not strategy_relation_allowed(strategy, auxiliary_relation_counts, relation, cap):
                skipped[f"{strategy}_relation_limit"] += 1
                picked_index = index
                break
            if target not in canonical_triples:
                skipped["target_edge_not_in_current_canonical_graph"] += 1
                picked_index = index
                break
            if candidate in canonical_triples or candidate in auxiliary_triples:
                skipped["candidate_duplicate_in_current_graph"] += 1
                picked_index = index
                break
            if relation in relation_expected:
                skipped["candidate_relation_is_allocated"] += 1
                picked_index = index
                break
            if not move.get("source_row_found"):
                skipped["source_row_missing"] += 1
                picked_index = index
                break

            current_delta = gen.current_relation_delta(canonical_relation_counts, relation_expected, target[1])
            if not (float(current_delta["surplus_delta"]) < float(thresholds["require_surplus_delta_lt"])):
                skipped["selected_move_not_surplus_reducing"] += 1
                picked_index = index
                break
            if float(current_delta["deficit_delta"]) > float(thresholds["require_total_deficit_delta_le"]):
                skipped["selected_move_increases_deficit"] += 1
                picked_index = index
                break

            trial_canonical = set(canonical_triples)
            trial_auxiliary = set(auxiliary_triples)
            trial_canonical.remove(target)
            trial_auxiliary.add(candidate)
            constraints = gen.hard_constraint_check(trial_canonical, trial_auxiliary, allocation)
            if not constraints["passes"]:
                skipped["interaction_breaks_hard_constraints"] += 1
                picked_index = index
                break
            trial_surplus_delta = float(constraints["canonical_total_surplus"]) - baseline_surplus
            trial_deficit_delta = float(constraints["canonical_total_deficit"]) - baseline_deficit
            if trial_deficit_delta > float(thresholds["require_total_deficit_delta_le"]):
                skipped["cumulative_deficit_increase"] += 1
                picked_index = index
                break

            canonical_triples = trial_canonical
            auxiliary_triples = trial_auxiliary
            canonical_relation_counts[target[1]] -= 1
            auxiliary_relation_counts[relation] += 1
            used_targets.add(target)
            used_candidates.add(candidate)
            selected.append(
                {
                    **move,
                    "selection_rank": len(selected) + 1,
                    "current_move_balance_delta": current_delta,
                    "post_move_constraints": constraints,
                    "cumulative_canonical_surplus_delta": trial_surplus_delta,
                    "cumulative_canonical_deficit_delta": trial_deficit_delta,
                    "diversity_strategy": strategy,
                }
            )
            picked_index = index
            break

        if picked_index is None:
            break
        remaining.pop(picked_index)

    final_metrics = gen.compare_relation_counts_to_allocation(canonical_relation_counts, allocation)
    return {
        "selected": selected,
        "skipped_reasons": dict(sorted(skipped.items())),
        "canonical_triples": canonical_triples,
        "auxiliary_triples": auxiliary_triples,
        "removed_triples": set(graph_triples) - canonical_triples,
        "baseline_surplus": baseline_surplus,
        "baseline_deficit": baseline_deficit,
        "final_surplus": float(final_metrics["total_surplus"]),
        "final_deficit": float(final_metrics["total_deficit"]),
        "canonical_surplus_delta": float(final_metrics["total_surplus"]) - baseline_surplus,
        "canonical_deficit_delta": float(final_metrics["total_deficit"]) - baseline_deficit,
    }


def classify_run(report: dict[str, Any] | None, error: str | None = None) -> str:
    if error or report is None:
        return "failed_policy"
    classification = report["acceptance_classification"]
    if classification == "c5_h2_candidate_passed_policy":
        return "passed_policy"
    if classification == "c5_h2_no_moves_selected":
        return "no_moves_selected"
    return "failed_policy"


def run_probe_case(
    strategy: str,
    cap: int,
    config_path: Path,
    policy_path: Path,
    config: dict[str, Any],
    policy: dict[str, Any],
    c5_report: dict[str, Any],
    score_audit: dict[str, Any],
    c4_2_report: dict[str, Any],
    graph_triples: set[Triple],
    allocation: dict[str, Any],
    moves: list[dict[str, Any]],
    scan_metadata: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Path]]:
    paths = run_paths(strategy, cap)
    ensure_parents(paths)
    started = time.time()
    selection = select_moves_with_strategy(moves, graph_triples, allocation, policy, cap, strategy)
    selection["candidate_moves_available"] = moves
    rows = gen.edge_rows(selection["canonical_triples"], selection["selected"], selection["selected"])
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
        selection_result=selection,
        paths=paths,
        started=started,
        finished=finished,
    )
    report["diversity_strategy"] = strategy
    gen.write_outputs(paths, rows, report)
    return report, paths


def result_row(strategy: str, cap: int, report: dict[str, Any] | None, paths: dict[str, Path], error: str | None = None) -> dict[str, Any]:
    if report is None:
        return {"strategy": strategy, "cap": cap, "classification": classify_run(report, error), "error": error}
    selection = report["selection_summary"]
    full_graph = report["evaluation"]["full_graph"]["graph_metrics"]
    canonical_graph = report["evaluation"]["canonical_only"]["graph_metrics"]
    edge_accounting = report["edge_accounting"]
    aux_dist = edge_accounting["auxiliary_relation_distribution"]
    aux_count = int(edge_accounting["auxiliary_unallocated_observed_edges"])
    p17_count = int(aux_dist.get("P17", 0))
    return {
        "strategy": strategy,
        "cap": cap,
        "classification": classify_run(report),
        "acceptance_classification": report["acceptance_classification"],
        "selected_auxiliary_edges": selection["selected_auxiliary_edges"],
        "canonical_edges_removed": selection["removed_canonical_edges"],
        "canonical_surplus_delta": selection["canonical_surplus_delta"],
        "canonical_deficit_delta": selection["canonical_deficit_delta"],
        "full_weak_components": full_graph["weak_component_count"],
        "canonical_only_weak_components": canonical_graph["weak_component_count"],
        "full_graph_triples": full_graph["unique_triples"],
        "canonical_only_triples": canonical_graph["unique_triples"],
        "auxiliary_relation_count": edge_accounting["unallocated_auxiliary_relation_count"],
        "auxiliary_relation_distribution": aux_dist,
        "p17_count": p17_count,
        "p17_share": p17_count / aux_count if aux_count else 0.0,
        "top_auxiliary_relations": sorted(aux_dist.items(), key=lambda item: (-item[1], item[0]))[:10],
        "graph_sha256": edge_accounting["graph_sha256"],
        "report_path": str(paths["report"]),
        "manifest_path": str(paths["manifest"]),
    }


def recommendation(rows: list[dict[str, Any]], cap_sweep: dict[str, Any]) -> dict[str, Any]:
    passed = [row for row in rows if row.get("classification") == "passed_policy"]
    if not passed:
        return {
            "recommendation": "reject_C5_H2",
            "best_strategy": None,
            "best_cap": None,
            "reason": "No diversity strategy produced a policy-passing candidate.",
        }

    baseline_by_cap = {
        row["cap"]: row
        for row in rows
        if row["strategy"] == "baseline_current_ranking" and row.get("classification") == "passed_policy"
    }
    candidates: list[dict[str, Any]] = []
    for row in passed:
        baseline = baseline_by_cap.get(row["cap"])
        if not baseline:
            continue
        surplus_cost = abs(float(baseline["canonical_surplus_delta"])) - abs(float(row["canonical_surplus_delta"]))
        p17_reduction = float(baseline["p17_share"]) - float(row["p17_share"])
        candidates.append({**row, "surplus_cost": surplus_cost, "p17_reduction": p17_reduction})

    meaningful = [
        row
        for row in candidates
        if row["strategy"] != "baseline_current_ranking"
        and row["p17_reduction"] >= 0.20
        and row["surplus_cost"] <= max(5, row["cap"] * 0.20)
    ]
    if meaningful:
        best = sorted(
            meaningful,
            key=lambda row: (
                -float(row["p17_reduction"]),
                float(row["surplus_cost"]),
                int(row["selected_auxiliary_edges"]),
                int(row["canonical_only_weak_components"]),
                row["strategy"],
            ),
        )[0]
        return {
            "recommendation": "use_diversity_penalty_candidate",
            "best_strategy": best["strategy"],
            "best_cap": best["cap"],
            "reason": "A diversity-aware strategy substantially reduces P17 concentration with acceptable surplus cost.",
            "p17_reduction": best["p17_reduction"],
            "surplus_cost": best["surplus_cost"],
            "registry_update_supported": False,
        }

    return {
        "recommendation": "continue_with_H3_synthetic_audit",
        "best_strategy": None,
        "best_cap": None,
        "reason": (
            "Diversity reranking does not provide a clearly superior observed-auxiliary candidate; the remaining "
            "observed H2 space is still auxiliary-dependent and limited by available cut-crossing evidence."
        ),
        "registry_update_supported": False,
        "cap_sweep_recommendation": (cap_sweep.get("recommendation") or {}).get("recommendation"),
    }


def write_table(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "strategy",
        "cap",
        "classification",
        "selected_auxiliary_edges",
        "canonical_edges_removed",
        "canonical_surplus_delta",
        "canonical_deficit_delta",
        "full_weak_components",
        "canonical_only_weak_components",
        "auxiliary_relation_count",
        "p17_count",
        "p17_share",
        "graph_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_summary(path: Path, rows: list[dict[str, Any]], rec: dict[str, Any]) -> None:
    lines = [
        "# C5-H2 Diversity Reranking Probe",
        "",
        f"Recommendation: `{rec['recommendation']}`",
        "",
        "| Strategy | Cap | Status | Aux | Surplus delta | Deficit delta | Canonical WCC | P17 | P17 share |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| `{strategy}` | {cap} | `{status}` | {aux} | {surplus} | {deficit} | {canon_wcc} | {p17} | {share:.3f} |".format(
                strategy=row.get("strategy"),
                cap=row.get("cap"),
                status=row.get("classification"),
                aux=row.get("selected_auxiliary_edges", ""),
                surplus=row.get("canonical_surplus_delta", ""),
                deficit=row.get("canonical_deficit_delta", ""),
                canon_wcc=row.get("canonical_only_weak_components", ""),
                p17=row.get("p17_count", ""),
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
            "This is a probe-only reranking experiment. It does not update the registry and does not make C5-H2 a canonical allocation-faithful candidate.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    caps = list(dict.fromkeys(args.caps))
    strategies = list(dict.fromkeys(args.strategies))
    unknown = sorted(set(strategies) - set(STRATEGIES))
    if unknown:
        raise ValueError(f"Unknown strategies: {unknown}")
    config_path = gen.resolve_path(args.config)
    policy_path = gen.resolve_path(args.policy)
    cap_sweep_path = gen.resolve_path(args.cap_sweep_report)
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
        print("strategies=" + ",".join(strategies))
        print("caps=" + ",".join(str(cap) for cap in caps))
        for strategy in strategies:
            for cap in caps:
                print(f"{strategy}_cap_{cap}_dir={DIVERSITY_PROBE_DIR / strategy / f'cap_{cap}'}")
        print(f"summary_report={REPORT_JSON}")
        print("outputs_written=false")
        return 0

    output_paths = [REPORT_JSON, REPORT_MD, REPORT_TSV]
    for strategy in strategies:
        for cap in caps:
            output_paths.extend(run_paths(strategy, cap).values())
    if not args.force:
        existing = [path for path in output_paths if path.exists()]
        if existing:
            names = ", ".join(str(path) for path in existing[:20])
            suffix = "" if len(existing) <= 20 else f" and {len(existing) - 20} more"
            raise FileExistsError(f"Refusing to overwrite diversity reranking outputs without --force: {names}{suffix}")

    started = time.time()
    c5_report = gen.load_json(gen.resolve_path(gen.DEFAULT_C5_REPORT))
    score_audit = gen.load_json(gen.resolve_path(gen.DEFAULT_SCORE_AUDIT))
    c4_2_report = gen.load_json(gen.resolve_path(gen.DEFAULT_C4_2_REPORT))
    cap_sweep_report = gen.load_json(cap_sweep_path)
    graph_triples = set(load_graph_triples(gen.resolve_path(config["parent_graph_path"])))
    allocation = load_allocation(gen.resolve_path(config["allocation_path"]))
    moves, scan_metadata = gen.build_h2_moves(config, c5_report)

    rows: list[dict[str, Any]] = []
    for strategy in strategies:
        for cap in caps:
            paths = run_paths(strategy, cap)
            try:
                report, paths = run_probe_case(
                    strategy,
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
                rows.append(result_row(strategy, cap, report, paths))
            except Exception as exc:  # pragma: no cover - recorded in report.
                rows.append(result_row(strategy, cap, None, paths, error=str(exc)))

    rec = recommendation(rows, cap_sweep_report)
    finished = time.time()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": "c5-h2-diversity-reranking-probe-v1",
        "probe_id": "C5_H2_diversity_reranking",
        "candidate_id": config["candidate_id"],
        "parent_candidate_id": config["parent_candidate_id"],
        "status": "probe_only_no_registry_update",
        "strategies": strategies,
        "caps": caps,
        "inputs": {
            "config": {"path": gen.repo_relative(config_path), "sha256": sha256_file(config_path)},
            "policy": {"path": gen.repo_relative(policy_path), "sha256": sha256_file(policy_path)},
            "cap_sweep_report": {"path": gen.repo_relative(cap_sweep_path), "sha256": sha256_file(cap_sweep_path)},
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
            "Per-strategy graphs are probe artifacts, not registry candidates.",
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

    print(f"diversity_reranking_report={REPORT_JSON}")
    print(f"diversity_reranking_table={REPORT_TSV}")
    print(f"recommendation={rec['recommendation']}")
    if rec.get("best_strategy"):
        print(f"best_strategy={rec['best_strategy']}")
        print(f"best_cap={rec['best_cap']}")
    for row in rows:
        print(
            "strategy={strategy}\tcap={cap}\tstatus={status}\taux={aux}\t"
            "surplus_delta={surplus}\tp17_share={share:.3f}".format(
                strategy=row.get("strategy"),
                cap=row.get("cap"),
                status=row.get("classification"),
                aux=row.get("selected_auxiliary_edges", ""),
                surplus=row.get("canonical_surplus_delta", ""),
                share=float(row.get("p17_share") or 0.0),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
