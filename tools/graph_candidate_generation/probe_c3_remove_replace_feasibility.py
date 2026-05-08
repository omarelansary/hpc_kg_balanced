#!/usr/bin/env python3
"""Probe C3 remove-and-replace feasibility without generating a graph.

The probe tests whether eligible replacement edges can preserve weak
connectivity when target-generic B0 edges are removed. It writes reports only;
it never writes a graph candidate and never queries WDQS.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_B0 = Path(
    "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/"
    "stage12_path_repair_prod/largest_component.csv"
)
DEFAULT_ALLOCATION = Path("src/Pruning graph/bidirectional_allocation_results5k.json")
DEFAULT_ELIGIBLE_POOL = Path(
    "artifacts/frozen_candidate_pools/C3_replacement_pool_v1/eligible_v1/"
    "eligible_replacement_candidates.jsonl"
)
DEFAULT_C2_REPORT = Path("experiments/graph_candidates/C2_targeted_generic_pruning/reports/prune_report.json")
DEFAULT_OUTPUT_DIR = Path("experiments/graph_candidates/C3_remove_replace_generic_connectivity/probe_v1")

EXPECTED_B0_SHA256 = "c443b124dd727976ca9c082dc91f1b8bb66d82ff117b05a926bc6ad21a5fe4b9"
EXPECTED_ALLOCATION_SHA256 = "a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb"
TARGET_RELATIONS = {"P31", "P279", "P131"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def read_graph(path: Path) -> tuple[list[tuple[str, str, str]], set[tuple[str, str, str]], set[str], Counter[str]]:
    triples: list[tuple[str, str, str]] = []
    unique: set[tuple[str, str, str]] = set()
    entities: set[str] = set()
    relation_counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not {"h", "r", "t"}.issubset(reader.fieldnames or []):
            raise ValueError(f"B0 graph must have h,r,t columns: {path}")
        for row in reader:
            triple = (row["h"], row["r"], row["t"])
            if triple in unique:
                continue
            unique.add(triple)
            triples.append(triple)
            entities.add(triple[0])
            entities.add(triple[2])
            relation_counts[triple[1]] += 1
    return triples, unique, entities, relation_counts


def load_allocation(path: Path) -> dict[str, int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    allocations = data.get("allocations")
    if not isinstance(allocations, list):
        raise ValueError(f"Allocation JSON has no top-level allocations list: {path}")
    eta: dict[str, int] = {}
    for row in allocations:
        if not isinstance(row, dict):
            continue
        relation = row.get("relation")
        if not isinstance(relation, str) or not relation:
            continue
        value = None
        for key in ("eta_integer", "eta", "eta_expected"):
            if row.get(key) is not None:
                value = row[key]
                break
        if value is None:
            continue
        eta[relation] = int(round(float(value)))
    return eta


def load_eligible(path: Path, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"Eligible pool row is not an object at line {line_number}")
            if row.get("r") in TARGET_RELATIONS:
                raise ValueError(f"Eligible pool contains target-generic relation at line {line_number}")
            if row.get("relation_allocation_status") in {"overfilled", "unallocated"}:
                raise ValueError(f"Eligible pool contains bad allocation status at line {line_number}")
            if row.get("endpoint_overlap_with_b0") == "none":
                raise ValueError(f"Eligible pool contains endpoint_overlap none at line {line_number}")
            rows.append(row)
            if len(rows) >= limit:
                break
    return rows


def build_undirected(
    triples: list[tuple[str, str, str]]
) -> tuple[dict[str, set[str]], Counter[tuple[str, str]], Counter[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    pair_counts: Counter[tuple[str, str]] = Counter()
    degrees: Counter[str] = Counter()
    for h, _r, t in triples:
        if h == t:
            degrees[h] += 2
            continue
        a, b = sorted((h, t))
        pair_counts[(a, b)] += 1
        adjacency[h].add(t)
        adjacency[t].add(h)
        degrees[h] += 1
        degrees[t] += 1
    return adjacency, pair_counts, degrees


def weak_component_count(adjacency: dict[str, set[str]], entities: set[str]) -> tuple[int, int]:
    seen: set[str] = set()
    largest = 0
    count = 0
    for node in entities:
        if node in seen:
            continue
        count += 1
        size = 0
        queue = deque([node])
        seen.add(node)
        while queue:
            current = queue.popleft()
            size += 1
            for nxt in adjacency.get(current, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        largest = max(largest, size)
    return count, largest


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
            else:
                dfs(nxt, node)
                low[node] = min(low[node], low[nxt])
                if low[nxt] > tin[node]:
                    bridges.add(tuple(sorted((node, nxt))))

    for node in adjacency:
        if node not in tin:
            dfs(node, None)
    return bridges


def component_side_after_removal(
    adjacency: dict[str, set[str]], start: str, blocked_pair: tuple[str, str]
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


def metric_parts(relation: str, count: int, eta: dict[str, int]) -> tuple[int, int]:
    expected = eta.get(relation)
    if expected is None:
        return 0, 0
    return max(expected - count, 0), max(count - expected, 0)


def balance_delta_for_swap(
    remove_relation: str,
    add_relation: str,
    relation_counts: Counter[str],
    eta: dict[str, int],
) -> dict[str, Any]:
    remove_before_deficit, remove_before_surplus = metric_parts(
        remove_relation, relation_counts[remove_relation], eta
    )
    remove_after_deficit, remove_after_surplus = metric_parts(
        remove_relation, relation_counts[remove_relation] - 1, eta
    )
    add_before_deficit, add_before_surplus = metric_parts(add_relation, relation_counts[add_relation], eta)
    add_after_deficit, add_after_surplus = metric_parts(add_relation, relation_counts[add_relation] + 1, eta)

    deficit_delta = (remove_after_deficit - remove_before_deficit) + (
        add_after_deficit - add_before_deficit
    )
    surplus_delta = (remove_after_surplus - remove_before_surplus) + (
        add_after_surplus - add_before_surplus
    )
    return {
        "deficit_delta": deficit_delta,
        "surplus_delta": surplus_delta,
        "remove_relation": {
            "relation": remove_relation,
            "observed_before": relation_counts[remove_relation],
            "observed_after": relation_counts[remove_relation] - 1,
            "eta": eta.get(remove_relation),
            "deficit_delta": remove_after_deficit - remove_before_deficit,
            "surplus_delta": remove_after_surplus - remove_before_surplus,
        },
        "add_relation": {
            "relation": add_relation,
            "observed_before": relation_counts[add_relation],
            "observed_after": relation_counts[add_relation] + 1,
            "eta": eta.get(add_relation),
            "deficit_delta": add_after_deficit - add_before_deficit,
            "surplus_delta": add_after_surplus - add_before_surplus,
        },
    }


def load_c2_accepted_targets(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    report = json.loads(path.read_text(encoding="utf-8"))
    rows = report.get("removed_triples_first_100")
    if not isinstance(rows, list):
        return []
    targets: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if all(isinstance(row.get(key), str) for key in ("h", "r", "t")):
            targets.append(
                {
                    "h": row["h"],
                    "r": row["r"],
                    "t": row["t"],
                    "target_source": "c2_accepted_deletion",
                    "accepted_order": row.get("accepted_order"),
                }
            )
    return targets


def select_targets(
    triples: list[tuple[str, str, str]],
    c2_targets: list[dict[str, Any]],
    pair_counts: Counter[tuple[str, str]],
    bridges: set[tuple[str, str]],
    degrees: Counter[str],
    max_targets: int,
) -> list[dict[str, Any]]:
    by_triple = {triple: triple for triple in triples}
    selected: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in c2_targets:
        triple = (row["h"], row["r"], row["t"])
        if triple in by_triple and triple[1] in TARGET_RELATIONS and triple not in seen:
            selected.append(dict(row))
            seen.add(triple)
    bridge_like: list[tuple[Any, dict[str, Any]]] = []
    for h, r, t in triples:
        if r not in TARGET_RELATIONS:
            continue
        triple = (h, r, t)
        if triple in seen:
            continue
        pair = tuple(sorted((h, t)))
        is_bridge = pair_counts[pair] == 1 and pair in bridges
        if not is_bridge:
            continue
        min_degree = min(degrees[h], degrees[t])
        max_degree = max(degrees[h], degrees[t])
        bridge_like.append(
            (
                (min_degree, max_degree, r, h, t),
                {
                    "h": h,
                    "r": r,
                    "t": t,
                    "target_source": "computed_b0_bridge_like",
                    "accepted_order": None,
                },
            )
        )
    for _key, row in sorted(bridge_like, key=lambda item: item[0]):
        if len(selected) >= max_targets:
            break
        triple = (row["h"], row["r"], row["t"])
        if triple not in seen:
            selected.append(row)
            seen.add(triple)
    return selected


def evaluate_target(
    target: dict[str, Any],
    eligible_rows: list[dict[str, Any]],
    adjacency: dict[str, set[str]],
    entities: set[str],
    pair_counts: Counter[tuple[str, str]],
    bridges: set[tuple[str, str]],
    graph_triples: set[tuple[str, str, str]],
    relation_counts: Counter[str],
    eta: dict[str, int],
    allocated_relations: set[str],
) -> dict[str, Any]:
    h, r, t = target["h"], target["r"], target["t"]
    pair = tuple(sorted((h, t)))
    is_bridge = pair_counts[pair] == 1 and pair in bridges
    deletion_safe = not is_bridge
    side: set[str] | None = None
    smaller_side_size = None
    if is_bridge:
        side = component_side_after_removal(adjacency, h, pair)
        other_size = len(entities) - len(side)
        smaller_side_size = min(len(side), other_size)

    feasible_swaps: list[dict[str, Any]] = []
    tested_replacements = 0
    rejected_counts: Counter[str] = Counter()

    target_after_count = relation_counts[r] - 1
    if r in allocated_relations and target_after_count <= 0:
        return {
            **target,
            "is_bridge": is_bridge,
            "deletion_safe_without_replacement": deletion_safe,
            "requires_replacement": is_bridge,
            "smaller_side_size_if_bridge": smaller_side_size,
            "tested_replacements": 0,
            "feasible_replacement_count": 0,
            "rejection_counts": {"would_lose_allocated_relation": len(eligible_rows)},
            "best_feasible_swaps": [],
        }

    for candidate in eligible_rows:
        tested_replacements += 1
        ch, cr, ct = candidate["h"], candidate["r"], candidate["t"]
        candidate_triple = (ch, cr, ct)
        if candidate_triple in graph_triples:
            rejected_counts["duplicate_triple"] += 1
            continue
        if cr in TARGET_RELATIONS or candidate.get("is_target_generic_relation") is True:
            rejected_counts["adds_target_generic_relation"] += 1
            continue
        if candidate.get("relation_allocation_status") in {"overfilled", "unallocated"}:
            rejected_counts["bad_candidate_allocation_status"] += 1
            continue
        if is_bridge:
            if side is None or ch not in entities or ct not in entities:
                rejected_counts["cannot_reconnect_bridge_endpoint_not_in_b0"] += 1
                continue
            if (ch in side) == (ct in side):
                rejected_counts["does_not_cross_removed_bridge_cut"] += 1
                continue

        delta = balance_delta_for_swap(r, cr, relation_counts, eta)
        if delta["deficit_delta"] > 0:
            rejected_counts["would_increase_total_deficit"] += 1
            continue
        if delta["surplus_delta"] >= 0:
            rejected_counts["would_not_reduce_total_surplus"] += 1
            continue

        feasible_swaps.append(
            {
                "target_edge": {"h": h, "r": r, "t": t},
                "replacement_edge": {
                    "candidate_id": candidate.get("candidate_id"),
                    "h": ch,
                    "r": cr,
                    "t": ct,
                    "score": candidate.get("score"),
                    "path_group_id": candidate.get("path_group_id"),
                    "path_group_size": candidate.get("path_group_size"),
                    "path_group_score": candidate.get("path_group_score"),
                    "source_stage": candidate.get("source_stage"),
                    "provenance_type": candidate.get("provenance_type"),
                    "endpoint_overlap_with_b0": candidate.get("endpoint_overlap_with_b0"),
                    "relation_allocation_status": candidate.get("relation_allocation_status"),
                },
                "connectivity_effect": {
                    "preserves_weak_component_count_1": True,
                    "target_deletion_safe_without_replacement": deletion_safe,
                    "replacement_crosses_removed_bridge_cut": bool(is_bridge),
                },
                "balance_effect": delta,
                "net_balance_rank": {
                    "surplus_reduction": -delta["surplus_delta"],
                    "deficit_reduction": -delta["deficit_delta"],
                    "candidate_score": candidate.get("score", 0),
                },
            }
        )

    feasible_swaps.sort(
        key=lambda row: (
            -row["net_balance_rank"]["surplus_reduction"],
            -row["net_balance_rank"]["deficit_reduction"],
            -int(row["net_balance_rank"].get("candidate_score") or 0),
            row["replacement_edge"]["candidate_id"] or "",
        )
    )
    return {
        **target,
        "is_bridge": is_bridge,
        "deletion_safe_without_replacement": deletion_safe,
        "requires_replacement": is_bridge,
        "smaller_side_size_if_bridge": smaller_side_size,
        "tested_replacements": tested_replacements,
        "feasible_replacement_count": len(feasible_swaps),
        "rejection_counts": dict(sorted(rejected_counts.items())),
        "best_feasible_swaps": feasible_swaps[:10],
    }


def write_summary(path: Path, report: dict[str, Any]) -> None:
    top_swaps = report["best_feasible_swaps"][:10]
    lines = [
        "# C3 Remove-And-Replace Feasibility Probe v1",
        "",
        "Status: feasibility probe only. No graph candidate was generated.",
        "",
        "## Inputs",
        "",
        f"- B0 graph: `{report['inputs']['b0_graph']['path']}`",
        f"- B0 SHA256: `{report['inputs']['b0_graph']['sha256']}`",
        f"- Allocation: `{report['inputs']['allocation']['path']}`",
        f"- Allocation SHA256: `{report['inputs']['allocation']['sha256']}`",
        f"- Eligible pool: `{report['inputs']['eligible_pool']['path']}`",
        f"- Eligible pool SHA256: `{report['inputs']['eligible_pool']['sha256']}`",
        "",
        "## Results",
        "",
        f"- Target edges tested: `{report['summary']['target_edges_tested']}`",
        f"- Replacement candidates loaded: `{report['summary']['replacement_candidates_loaded']}`",
        f"- Replacement pair tests performed: `{report['summary']['replacement_pair_tests_performed']}`",
        f"- Deletions already safe without replacement: `{report['summary']['target_deletions_already_safe_without_replacement']}`",
        f"- Targets requiring replacement: `{report['summary']['targets_requiring_replacement']}`",
        f"- Targets with at least one feasible replacement: `{report['summary']['targets_with_at_least_one_feasible_replacement']}`",
        f"- Targets requiring replacement with feasible replacement: `{report['summary']['targets_requiring_replacement_with_feasible_replacement']}`",
        f"- Targets with no feasible replacement: `{report['summary']['targets_with_no_feasible_replacement']}`",
        f"- Total feasible swaps found: `{report['summary']['total_feasible_swaps_found']}`",
        "",
        "## Recommendation",
        "",
        report["recommendation"]["text"],
        "",
        "## Strongest Swap Examples",
        "",
    ]
    if top_swaps:
        lines.extend(
            [
                "| Target | Replacement | Surplus delta | Deficit delta | Candidate score | Provenance |",
                "| --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for swap in top_swaps:
            target = swap["target_edge"]
            repl = swap["replacement_edge"]
            bal = swap["balance_effect"]
            lines.append(
                f"| `{target['h']} {target['r']} {target['t']}` | "
                f"`{repl['h']} {repl['r']} {repl['t']}` | "
                f"{bal['surplus_delta']} | {bal['deficit_delta']} | "
                f"{repl.get('score')} | `{repl.get('provenance_type')}` |"
            )
    else:
        lines.append("No feasible swaps were found under the probe policy.")
    lines.extend(
        [
            "",
            "## Runtime Notes",
            "",
            f"- Started: `{report['runtime']['started_on']}`",
            f"- Finished: `{report['runtime']['finished_on']}`",
            f"- Elapsed seconds: `{report['runtime']['elapsed_seconds']}`",
            "",
            "## Notes",
            "",
            "- This probe used bridge analysis on B0 rather than writing modified graph files.",
            "- No live WDQS query was made.",
            "- `docs/reconstruction/graph_candidates.tsv` was not edited.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe C3 remove-and-replace feasibility.")
    parser.add_argument("--b0-graph", type=Path, default=DEFAULT_B0)
    parser.add_argument("--allocation", type=Path, default=DEFAULT_ALLOCATION)
    parser.add_argument("--eligible-pool", type=Path, default=DEFAULT_ELIGIBLE_POOL)
    parser.add_argument("--c2-report", type=Path, default=DEFAULT_C2_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-target-edges", type=int, default=500)
    parser.add_argument("--max-replacement-candidates", type=int, default=990)
    parser.add_argument("--top-swaps", type=int, default=50)
    args = parser.parse_args()

    started = time.time()
    started_on = datetime.now(timezone.utc).isoformat()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit(f"Refusing to overwrite non-empty probe directory: {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    b0_sha = sha256_file(args.b0_graph)
    allocation_sha = sha256_file(args.allocation)
    eligible_sha = sha256_file(args.eligible_pool)
    if b0_sha != EXPECTED_B0_SHA256:
        raise SystemExit(f"B0 hash mismatch: expected {EXPECTED_B0_SHA256}, observed {b0_sha}")
    if allocation_sha != EXPECTED_ALLOCATION_SHA256:
        raise SystemExit(
            f"Allocation hash mismatch: expected {EXPECTED_ALLOCATION_SHA256}, observed {allocation_sha}"
        )

    triples, graph_triples, entities, relation_counts = read_graph(args.b0_graph)
    eta = load_allocation(args.allocation)
    allocated_relations = set(eta)
    eligible_rows = load_eligible(args.eligible_pool, args.max_replacement_candidates)
    adjacency, pair_counts, degrees = build_undirected(triples)
    weak_components, largest_component_size = weak_component_count(adjacency, entities)
    bridges = find_simple_bridges(adjacency)
    real_bridges = {pair for pair in bridges if pair_counts[pair] == 1}
    c2_targets = load_c2_accepted_targets(args.c2_report)
    targets = select_targets(
        triples,
        c2_targets,
        pair_counts,
        real_bridges,
        degrees,
        args.max_target_edges,
    )

    target_results = [
        evaluate_target(
            target,
            eligible_rows,
            adjacency,
            entities,
            pair_counts,
            real_bridges,
            graph_triples,
            relation_counts,
            eta,
            allocated_relations,
        )
        for target in targets
    ]

    all_swaps = [swap for result in target_results for swap in result["best_feasible_swaps"]]
    all_swaps.sort(
        key=lambda row: (
            -row["net_balance_rank"]["surplus_reduction"],
            -row["net_balance_rank"]["deficit_reduction"],
            -int(row["net_balance_rank"].get("candidate_score") or 0),
            row["replacement_edge"]["candidate_id"] or "",
        )
    )
    total_feasible_swaps = sum(result["feasible_replacement_count"] for result in target_results)
    requiring = [result for result in target_results if result["requires_replacement"]]
    safe_without = [result for result in target_results if result["deletion_safe_without_replacement"]]
    with_feasible = [result for result in target_results if result["feasible_replacement_count"] > 0]
    requiring_with_feasible = [
        result for result in requiring if result["feasible_replacement_count"] > 0
    ]
    no_feasible = [result for result in target_results if result["feasible_replacement_count"] == 0]
    c2_source_count = sum(1 for result in target_results if result["target_source"] == "c2_accepted_deletion")
    bridge_source_count = sum(1 for result in target_results if result["target_source"] == "computed_b0_bridge_like")

    replacement_relation_effects: Counter[str] = Counter()
    target_relation_effects: Counter[str] = Counter()
    for result in target_results:
        for swap in result["best_feasible_swaps"]:
            replacement_relation_effects[swap["replacement_edge"]["r"]] += 1
            target_relation_effects[swap["target_edge"]["r"]] += 1

    recommend_bounded = total_feasible_swaps > 0
    recommend_bridge_rescue = bool(requiring_with_feasible)
    if recommend_bridge_rescue:
        recommendation_text = (
            "Implementing a full C3 bridge-rescue generator is recommended as a bounded "
            "experiment because at least one connectivity-critical target edge had a feasible "
            "replacement under the current hard constraints."
        )
    elif recommend_bounded:
        recommendation_text = (
            "A bounded safe-edge remove-and-replace generator is worth implementing only as a "
            "limited experiment: feasible swaps exist for deletion-safe target edges, but the "
            "eligible pool did not rescue any tested connectivity-critical bridge-like target "
            "edges. Do not frame this as solving the C2 connectivity blocker."
        )
    else:
        recommendation_text = (
            "A full C3 generator is not recommended yet because the probe found no feasible swaps "
            "under the current hard constraints."
        )

    finished_on = datetime.now(timezone.utc).isoformat()
    elapsed = round(time.time() - started, 3)
    report = {
        "probe_id": "C3_remove_replace_feasibility_probe_v1",
        "created_on": finished_on,
        "inputs": {
            "b0_graph": {"path": args.b0_graph.as_posix(), "sha256": b0_sha},
            "allocation": {"path": args.allocation.as_posix(), "sha256": allocation_sha},
            "eligible_pool": {
                "path": args.eligible_pool.as_posix(),
                "sha256": eligible_sha,
                "loaded_candidate_count": len(eligible_rows),
            },
            "c2_report": {
                "path": args.c2_report.as_posix(),
                "accepted_deletion_targets_recovered": len(c2_targets),
                "would_disconnect_rejected_targets_recovered": 0,
                "would_disconnect_rejected_targets_note": (
                    "C2 prune_report.json has aggregate would_disconnect_graph counts but no "
                    "per-target rejected triple list."
                ),
            },
        },
        "limits": {
            "max_target_edges": args.max_target_edges,
            "max_replacement_candidates_per_target": args.max_replacement_candidates,
            "top_swaps_in_report": args.top_swaps,
        },
        "b0_connectivity": {
            "weak_component_count": weak_components,
            "largest_component_size": largest_component_size,
            "entity_count": len(entities),
            "unique_triples": len(graph_triples),
            "unique_relations": len(relation_counts),
            "allocated_relation_count": len(allocated_relations),
            "simple_bridge_pair_count": len(real_bridges),
        },
        "summary": {
            "target_edges_tested": len(target_results),
            "target_edges_from_c2_accepted_deletions": c2_source_count,
            "target_edges_from_computed_b0_bridge_like": bridge_source_count,
            "replacement_candidates_loaded": len(eligible_rows),
            "replacement_pair_tests_performed": sum(
                result["tested_replacements"] for result in target_results
            ),
            "target_deletions_already_safe_without_replacement": len(safe_without),
            "targets_requiring_replacement": len(requiring),
            "targets_with_at_least_one_feasible_replacement": len(with_feasible),
            "targets_requiring_replacement_with_feasible_replacement": len(
                requiring_with_feasible
            ),
            "targets_with_no_feasible_replacement": len(no_feasible),
            "total_feasible_swaps_found": total_feasible_swaps,
        },
        "scoring_policy": {
            "feasible_swap_requirements": [
                "preserve weak_component_count = 1",
                "preserve all allocated relations",
                "avoid duplicate triples",
                "do not add P31/P279/P131",
                "do not add overfilled or unallocated relations",
                "improve or preserve total deficit",
                "reduce total surplus net of added replacement edge and removed generic edge",
            ],
            "connectivity_method": (
                "For non-bridge target edges, deletion is connectivity-safe. For bridge target "
                "edges, a replacement is connectivity-feasible only if it connects the two sides "
                "of the removed bridge cut."
            ),
        },
        "relation_level_effects_from_recorded_best_swaps": {
            "removed_target_relations": dict(sorted(target_relation_effects.items())),
            "added_replacement_relations": dict(sorted(replacement_relation_effects.items())),
        },
        "best_feasible_swaps": all_swaps[: args.top_swaps],
        "target_results": target_results,
        "recommendation": {
            "implement_full_c3_generator": recommend_bridge_rescue,
            "implement_bounded_safe_edge_swap_generator": recommend_bounded,
            "text": recommendation_text,
            "caveat": (
                "This is a feasibility probe. It did not write a candidate graph and only records "
                "the top feasible swaps per target, not an optimized global swap sequence."
            ),
        },
        "runtime": {
            "started_on": started_on,
            "finished_on": finished_on,
            "elapsed_seconds": elapsed,
            "notes": [
                "No live WDQS query was made.",
                "No graph candidate was written.",
                "B0 was loaded read-only.",
                "docs/reconstruction/graph_candidates.tsv was not edited.",
            ],
        },
    }

    report_path = args.output_dir / "feasibility_probe_report.json"
    summary_path = args.output_dir / "feasibility_probe_summary.md"
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n")
    write_summary(summary_path, report)

    print(
        json.dumps(
            {
                "report": report_path.as_posix(),
                "summary": summary_path.as_posix(),
                "target_edges_tested": len(target_results),
                "total_feasible_swaps_found": total_feasible_swaps,
                "targets_requiring_replacement_with_feasible_replacement": len(
                    requiring_with_feasible
                ),
                "implement_full_c3_generator": recommend_bridge_rescue,
                "implement_bounded_safe_edge_swap_generator": recommend_bounded,
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
