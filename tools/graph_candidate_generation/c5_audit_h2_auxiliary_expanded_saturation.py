#!/usr/bin/env python3
"""Audit expanded C5-H2 auxiliary support over frozen local evidence only.

This audit expands the earlier C5-H2 saturation check from the bounded C4/C5
cut-crossing report to the full B0 surplus bridge-target universe available in
the frozen local candidate sources. It writes compact evidence reports only; it
does not write a graph candidate.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.allocation_metrics import (  # noqa: E402
    compare_relation_counts_to_allocation,
    load_allocation,
)
from src.kg_pipeline.evaluation.candidate_report import evaluate_candidate, sha256_file  # noqa: E402
from src.kg_pipeline.evaluation.connectivity_metrics import summarize_connectivity  # noqa: E402
from src.kg_pipeline.evaluation.graph_io import Triple, load_graph_triples  # noqa: E402
from tools.graph_candidate_generation.c4_audit_replacement_pool_against_bridge_cuts import (  # noqa: E402
    find_simple_bridges_iterative,
)
from tools.graph_candidate_generation.c4_probe_bridge_aware_replace_add import (  # noqa: E402
    build_undirected,
    relation_delta,
    repo_relative,
    resolve_path,
)
from tools.graph_candidate_generation.c4_search_local_cut_crossing_candidates import (  # noqa: E402
    candidate_sources,
    extract_triple,
    iter_jsonl_triples,
)

EXPERIMENT_DIR = Path("experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix")
REPORT_DIR = EXPERIMENT_DIR / "reports" / "auxiliary_expanded_saturation"
REPORT_JSON = REPORT_DIR / "expanded_auxiliary_saturation_report.json"
REPORT_MD = REPORT_DIR / "expanded_auxiliary_saturation_summary.md"
REPORT_TSV = REPORT_DIR / "expanded_auxiliary_saturation_table.tsv"

DEFAULT_CONFIG = EXPERIMENT_DIR / "configs" / "config.template.json"
DEFAULT_POLICY = EXPERIMENT_DIR / "configs" / "h2_generator_policy.template.json"
DEFAULT_C5_REPORT = EXPERIMENT_DIR / "reports" / "probe_only" / "c5_h1_h2_probe_report.json"
DEFAULT_C4_2_REPORT = Path(
    "experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/"
    "local_cut_crossing_candidate_search.json"
)

B0_SURPLUS = 6702.0
SURPLUS_REDUCTION_THRESHOLD = 670.0
MAX_SINGLE_AUX_RELATION_SHARE = 0.40
KEY_RELATIONS = ("P31", "P279", "P131")
EXACT_MATCHING_EDGE_LIMIT = 250000

STRATEGIES = (
    "baseline_current_ranking_no_cap",
    "relation_diversity_penalty_light_no_cap",
    "relation_diversity_penalty_strong_no_cap",
    "max_per_aux_relation_10_no_cap",
    "max_per_aux_relation_20_no_cap",
    "p17_cap_25_percent_no_cap",
    "fragmentation_penalty_light_no_cap",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--c5-report", type=Path, default=DEFAULT_C5_REPORT)
    parser.add_argument("--c4-2-report", type=Path, default=DEFAULT_C4_2_REPORT)
    parser.add_argument("--strategies", nargs="+", default=list(STRATEGIES))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def refuse_overwrite(force: bool) -> None:
    existing = [path for path in (REPORT_JSON, REPORT_MD, REPORT_TSV) if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite expanded saturation reports without --force: {names}")


def triple_dict(triple: Triple) -> dict[str, str]:
    h, r, t = triple
    return {"h": h, "r": r, "t": t}


def triple_from_dict(edge: dict[str, str]) -> Triple:
    return edge["h"], edge["r"], edge["t"]


def edge_pair(h: str, t: str) -> tuple[str, str]:
    return tuple(sorted((h, t)))


def fmt(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.12g}"
    if value is None:
        return ""
    return str(value)


def load_c5_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    for key in ("allowed_live_sources", "allowed_wdqs", "allowed_llm", "allowed_synthetic_pattern_derived"):
        if config.get(key) is not False:
            raise ValueError(f"Expanded C5-H2 audit requires {key}=false")
    return config


def component_map_without_bridges(
    adjacency: dict[str, set[str]],
    bridge_pairs: set[tuple[str, str]],
) -> tuple[dict[str, int], dict[int, set[str]]]:
    component_by_node: dict[str, int] = {}
    members: dict[int, set[str]] = {}
    component_id = 0
    for start in sorted(adjacency):
        if start in component_by_node:
            continue
        seen = {start}
        queue = deque([start])
        component_by_node[start] = component_id
        while queue:
            node = queue.popleft()
            for nxt in adjacency.get(node, set()):
                if edge_pair(node, nxt) in bridge_pairs:
                    continue
                if nxt in seen:
                    continue
                seen.add(nxt)
                component_by_node[nxt] = component_id
                queue.append(nxt)
        members[component_id] = seen
        component_id += 1
    return component_by_node, members


def build_bridge_forest(
    component_by_node: dict[str, int],
    component_members: dict[int, set[str]],
    bridge_pairs: set[tuple[str, str]],
) -> dict[str, Any]:
    tree: dict[int, set[int]] = defaultdict(set)
    bridge_edge_by_components: dict[tuple[int, int], tuple[str, str]] = {}
    for left, right in sorted(bridge_pairs):
        left_component = component_by_node[left]
        right_component = component_by_node[right]
        if left_component == right_component:
            continue
        key = tuple(sorted((left_component, right_component)))
        tree[left_component].add(right_component)
        tree[right_component].add(left_component)
        bridge_edge_by_components[key] = (left, right)

    parent: dict[int, int | None] = {}
    depth: dict[int, int] = {}
    subtree_entity_count: dict[int, int] = {}
    root_entity_count: dict[int, int] = {}
    roots: list[int] = []
    all_components = sorted(component_members)
    for root in all_components:
        if root in parent:
            continue
        roots.append(root)
        parent[root] = None
        depth[root] = 0
        order = [root]
        stack = [root]
        while stack:
            node = stack.pop()
            for nxt in sorted(tree.get(node, set())):
                if nxt in parent:
                    continue
                parent[nxt] = node
                depth[nxt] = depth[node] + 1
                order.append(nxt)
                stack.append(nxt)
        total = 0
        for node in reversed(order):
            count = len(component_members[node])
            for child in tree.get(node, set()):
                if parent.get(child) == node:
                    count += subtree_entity_count[child]
            subtree_entity_count[node] = count
            total += len(component_members[node])
        for node in order:
            root_entity_count[node] = total

    return {
        "tree": {component: set(neighbors) for component, neighbors in tree.items()},
        "parent": parent,
        "depth": depth,
        "subtree_entity_count": subtree_entity_count,
        "root_entity_count": root_entity_count,
        "bridge_edge_by_components": bridge_edge_by_components,
        "roots": roots,
    }


def bridge_path_component_edges(left: int, right: int, forest: dict[str, Any]) -> list[tuple[int, int]]:
    parent: dict[int, int | None] = forest["parent"]
    depth: dict[int, int] = forest["depth"]
    if left not in parent or right not in parent:
        return []
    a = left
    b = right
    out: list[tuple[int, int]] = []
    while depth[a] > depth[b]:
        p = parent[a]
        if p is None:
            return []
        out.append(tuple(sorted((a, p))))
        a = p
    while depth[b] > depth[a]:
        p = parent[b]
        if p is None:
            return []
        out.append(tuple(sorted((b, p))))
        b = p
    while a != b:
        pa = parent[a]
        pb = parent[b]
        if pa is None or pb is None:
            return []
        out.append(tuple(sorted((a, pa))))
        out.append(tuple(sorted((b, pb))))
        a = pa
        b = pb
    return out


def bridge_side_sizes(component_left: int, component_right: int, forest: dict[str, Any]) -> tuple[int, int]:
    parent: dict[int, int | None] = forest["parent"]
    subtree: dict[int, int] = forest["subtree_entity_count"]
    root_totals: dict[int, int] = forest["root_entity_count"]
    if parent.get(component_left) == component_right:
        child = component_left
    elif parent.get(component_right) == component_left:
        child = component_right
    else:
        return 0, 0
    child_size = subtree[child]
    total = root_totals[child]
    return min(child_size, total - child_size), max(child_size, total - child_size)


def pattern_delta_for_remove(allocation: dict[str, Any], relation: str) -> dict[str, float]:
    rows = allocation.get("relation_patterns", {}).get(relation, [])
    total_eta = sum(float(row.get("eta", 0.0)) for row in rows)
    if total_eta <= 0:
        return {}
    out: dict[str, float] = defaultdict(float)
    for row in rows:
        pattern = row.get("pattern")
        if not pattern:
            continue
        out[str(pattern)] -= float(row.get("eta", 0.0)) / total_eta
    return dict(sorted(out.items()))


def build_target_universe(
    graph_triples: set[Triple],
    allocation: dict[str, Any],
) -> dict[str, Any]:
    relation_counts = Counter(r for _h, r, _t in graph_triples)
    relation_expected = allocation["relation_expected"]
    adjacency, pair_counts, _degrees = build_undirected(graph_triples)
    simple_bridges = find_simple_bridges_iterative(adjacency)
    bridge_pairs = {pair for pair in simple_bridges if pair_counts[pair] == 1}
    component_by_node, component_members = component_map_without_bridges(adjacency, bridge_pairs)
    forest = build_bridge_forest(component_by_node, component_members, bridge_pairs)

    target_by_id: dict[int, dict[str, Any]] = {}
    target_ids_by_component_edge: dict[tuple[int, int], list[int]] = defaultdict(list)
    target_stats = Counter()
    surplus_relations = {
        relation
        for relation, count in relation_counts.items()
        if relation in relation_expected and count > float(relation_expected[relation])
    }
    for triple in sorted(graph_triples):
        h, r, t = triple
        delta = relation_delta(relation_counts, relation_expected, r, None)
        surplus_reducing = float(delta["surplus_delta"]) < 0 and float(delta["deficit_delta"]) <= 0
        pair = edge_pair(h, t)
        bridge_critical = h != t and pair in bridge_pairs and pair_counts[pair] == 1
        if bridge_critical and surplus_reducing:
            target_stats["surplus_bridge_targets"] += 1
            left_component = component_by_node[h]
            right_component = component_by_node[t]
            component_edge = tuple(sorted((left_component, right_component)))
            smaller, larger = bridge_side_sizes(left_component, right_component, forest)
            target_id = len(target_by_id)
            target = {
                "target_id": target_id,
                "target_edge": triple_dict(triple),
                "target_relation": r,
                "relation_surplus_before": max(float(relation_counts[r]) - float(relation_expected.get(r, 0.0)), 0.0),
                "balance_delta_if_removed": delta,
                "pattern_total_delta": pattern_delta_for_remove(allocation, r),
                "bridge_pair": list(pair),
                "component_edge": list(component_edge),
                "smaller_side_size": smaller,
                "larger_side_size": larger,
            }
            target_by_id[target_id] = target
            target_ids_by_component_edge[component_edge].append(target_id)
        elif bridge_critical:
            target_stats["non_surplus_bridge_targets"] += 1
        elif surplus_reducing:
            target_stats["surplus_non_bridge_targets"] += 1
        else:
            target_stats["non_surplus_non_bridge_triples"] += 1

    return {
        "relation_counts": relation_counts,
        "relation_expected": relation_expected,
        "adjacency": adjacency,
        "pair_counts": pair_counts,
        "simple_bridge_pairs": simple_bridges,
        "bridge_critical_pairs": bridge_pairs,
        "component_by_node": component_by_node,
        "component_members": component_members,
        "bridge_forest": forest,
        "target_by_id": target_by_id,
        "target_ids_by_component_edge": dict(target_ids_by_component_edge),
        "target_stats": target_stats,
        "surplus_relations": surplus_relations,
    }


def source_row_metadata(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    keys = (
        "candidate_id",
        "source_stage",
        "provenance_type",
        "relation_allocation_status",
        "duplicate_provenance_count",
        "endpoint_overlap_with_b0",
        "source_artifact",
        "source_event_type",
        "source_record_index",
        "source_sha256",
        "path_group_id",
        "path_group_size",
    )
    return {key: row.get(key) for key in keys if row.get(key) is not None}


def candidate_sort_key(move: dict[str, Any]) -> tuple[Any, ...]:
    target = triple_from_dict(move["target_edge"])
    candidate = triple_from_dict(move["candidate"])
    return (
        float(move["canonical_surplus_delta"]),
        float(move["canonical_deficit_delta"]),
        -int(move.get("duplicate_provenance_count") or 0),
        move.get("source_stage") or "",
        move.get("provenance_type") or "",
        int(move["target_id"]),
        target,
        candidate,
    )


def scan_sources_expanded(
    graph_triples: set[Triple],
    allocation: dict[str, Any],
    target_context: dict[str, Any],
) -> dict[str, Any]:
    entities = {node for h, _r, t in graph_triples for node in (h, t)}
    relation_expected = target_context["relation_expected"]
    relation_counts = target_context["relation_counts"]
    component_by_node = target_context["component_by_node"]
    forest = target_context["bridge_forest"]
    target_by_id: dict[int, dict[str, Any]] = target_context["target_by_id"]
    target_ids_by_component_edge: dict[tuple[int, int], list[int]] = target_context["target_ids_by_component_edge"]
    sources = candidate_sources()

    source_stats: dict[str, Counter[str]] = defaultdict(Counter)
    source_relation_counts: dict[str, Counter[str]] = defaultdict(Counter)
    source_exhaustion: dict[str, dict[str, Any]] = {}
    aggregate = Counter()
    moves_by_key: dict[tuple[int, Triple], dict[str, Any]] = {}
    supported_targets: set[int] = set()
    unique_auxiliary_candidates: set[Triple] = set()
    top_examples: list[dict[str, Any]] = []
    target_support_counts: Counter[int] = Counter()

    for source in sources:
        source_id = source["source_id"]
        paths: list[Path] = source["paths"]
        source_exhaustion[source_id] = {
            "source_type": source["source_type"],
            "file_count": len(paths),
            "exhausted_all_listed_files": True,
            "missing_files": 0,
            "paths_first_10": [repo_relative(path) for path in paths[:10]],
        }
        if not paths:
            source_stats[source_id]["missing_or_empty_source_list"] += 1
            continue
        for path in paths:
            if not path.is_file():
                source_stats[source_id]["missing_files"] += 1
                source_exhaustion[source_id]["missing_files"] += 1
                continue
            source_stats[source_id]["files_scanned"] += 1
            source_stats[source_id]["bytes_scanned"] += path.stat().st_size
            for line_number, triple, row in iter_jsonl_triples(path):
                source_stats[source_id]["rows_scanned"] += 1
                aggregate["rows_scanned"] += 1
                if triple is None:
                    source_stats[source_id]["rows_without_parseable_triple"] += 1
                    continue
                h, r, t = triple
                source_stats[source_id]["candidate_triples_parsed"] += 1
                aggregate["candidate_triples_parsed"] += 1
                source_relation_counts[source_id][r] += 1
                h_inside = h in entities
                t_inside = t in entities
                if h_inside and t_inside:
                    source_stats[source_id]["endpoint_inside_b0_both"] += 1
                    aggregate["endpoint_inside_b0_both"] += 1
                elif h_inside or t_inside:
                    source_stats[source_id]["endpoint_inside_b0_one"] += 1
                    aggregate["endpoint_inside_b0_one"] += 1
                    continue
                else:
                    source_stats[source_id]["endpoint_inside_b0_none"] += 1
                    aggregate["endpoint_inside_b0_none"] += 1
                    continue
                if triple in graph_triples:
                    source_stats[source_id]["already_in_b0"] += 1
                    continue
                if r in relation_expected:
                    source_stats[source_id]["allocated_candidate_relation"] += 1
                    continue
                source_stats[source_id]["observed_unallocated_candidate_rows"] += 1
                aggregate["observed_unallocated_candidate_rows"] += 1
                left_component = component_by_node.get(h)
                right_component = component_by_node.get(t)
                if left_component is None or right_component is None or left_component == right_component:
                    source_stats[source_id]["does_not_cross_bridge_component"] += 1
                    continue
                component_edges = bridge_path_component_edges(left_component, right_component, forest)
                target_ids: list[int] = []
                for component_edge in component_edges:
                    target_ids.extend(target_ids_by_component_edge.get(component_edge, []))
                if not target_ids:
                    source_stats[source_id]["crosses_no_surplus_bridge_target"] += 1
                    continue
                source_stats[source_id]["cut_crossing_candidate_rows"] += 1
                aggregate["cut_crossing_candidate_rows"] += 1
                unique_auxiliary_candidates.add(triple)
                metadata = source_row_metadata(row)
                duplicate_count = int(metadata.get("duplicate_provenance_count") or 0)
                for target_id in sorted(set(target_ids)):
                    target = target_by_id[target_id]
                    delta = relation_delta(relation_counts, relation_expected, target["target_relation"], None)
                    surplus_reducing = float(delta["surplus_delta"]) < 0
                    deficit_increase = float(delta["deficit_delta"]) > 0
                    if not surplus_reducing or deficit_increase:
                        continue
                    key = (target_id, triple)
                    previous = moves_by_key.get(key)
                    move = {
                        "target_id": target_id,
                        "cut_id": target_id,
                        "target_edge": target["target_edge"],
                        "target_component_edge": target["component_edge"],
                        "candidate_component_edge": list(sorted((left_component, right_component))),
                        "candidate_crossed_component_edges": [list(edge) for edge in component_edges],
                        "candidate": triple_dict(triple),
                        "candidate_relation_allocated": False,
                        "candidate_observed_source": "frozen_local_evidence",
                        "canonical_surplus_delta": float(delta["surplus_delta"]),
                        "canonical_deficit_delta": float(delta["deficit_delta"]),
                        "pattern_total_delta": target["pattern_total_delta"],
                        "smaller_side_size": target["smaller_side_size"],
                        "larger_side_size": target["larger_side_size"],
                        "source_id": source_id,
                        "source_path": repo_relative(path),
                        "line_number": line_number,
                        "source_row_found": row is not None,
                        "source_stage": str(metadata.get("source_stage") or ""),
                        "provenance_type": str(metadata.get("provenance_type") or ""),
                        "duplicate_provenance_count": duplicate_count,
                        "candidate_id": metadata.get("candidate_id"),
                        "source_metadata": metadata,
                    }
                    if previous is None or candidate_sort_key(move) < candidate_sort_key(previous):
                        moves_by_key[key] = move
                    supported_targets.add(target_id)
                    target_support_counts[target_id] += 1
                    aggregate["cut_crossing_candidate_target_pairs"] += 1
                    if len(top_examples) < 50:
                        top_examples.append(move)

    moves = sorted(moves_by_key.values(), key=candidate_sort_key)
    targets_without_support = sorted(set(target_by_id) - supported_targets)
    source_stats_out = {
        source_id: {
            **dict(sorted(stats.items())),
            "top_20_relations": dict(source_relation_counts[source_id].most_common(20)),
        }
        for source_id, stats in sorted(source_stats.items())
    }
    return {
        "moves": moves,
        "source_stats": source_stats_out,
        "source_exhaustion": source_exhaustion,
        "aggregate_counts": {
            "rows_scanned": aggregate["rows_scanned"],
            "candidate_triples_parsed": aggregate["candidate_triples_parsed"],
            "observed_unallocated_candidate_rows": aggregate["observed_unallocated_candidate_rows"],
            "endpoint_inside_b0_both": aggregate["endpoint_inside_b0_both"],
            "endpoint_inside_b0_one": aggregate["endpoint_inside_b0_one"],
            "endpoint_inside_b0_none": aggregate["endpoint_inside_b0_none"],
            "cut_crossing_candidate_rows": aggregate["cut_crossing_candidate_rows"],
            "cut_crossing_candidate_target_pairs": aggregate["cut_crossing_candidate_target_pairs"],
            "unique_auxiliary_candidates": len(unique_auxiliary_candidates),
            "unique_supported_targets": len(supported_targets),
            "targets_without_support": len(targets_without_support),
            "deduplicated_candidate_moves": len(moves),
        },
        "top_candidate_examples": top_examples[:20],
        "targets_with_highest_support": [
            {
                "target_id": target_id,
                "supporting_candidate_pairs": count,
                "target_edge": target_by_id[target_id]["target_edge"],
            }
            for target_id, count in target_support_counts.most_common(25)
        ],
        "targets_without_support_first_50": [target_by_id[target_id] for target_id in targets_without_support[:50]],
    }


def hopcroft_karp(target_to_candidates: dict[int, set[Triple]]) -> dict[str, Any]:
    targets = sorted(target_to_candidates)
    pair_u: dict[int, Triple | None] = {target: None for target in targets}
    candidates = sorted({candidate for values in target_to_candidates.values() for candidate in values})
    pair_v: dict[Triple, int | None] = {candidate: None for candidate in candidates}
    dist: dict[int, int] = {}

    def bfs() -> bool:
        queue: deque[int] = deque()
        found = False
        for target in targets:
            if pair_u[target] is None:
                dist[target] = 0
                queue.append(target)
            else:
                dist[target] = 10**12
        while queue:
            target = queue.popleft()
            for candidate in target_to_candidates.get(target, set()):
                mate = pair_v[candidate]
                if mate is None:
                    found = True
                elif dist[mate] == 10**12:
                    dist[mate] = dist[target] + 1
                    queue.append(mate)
        return found

    def dfs(target: int) -> bool:
        for candidate in sorted(target_to_candidates.get(target, set())):
            mate = pair_v[candidate]
            if mate is None or (dist[mate] == dist[target] + 1 and dfs(mate)):
                pair_u[target] = candidate
                pair_v[candidate] = target
                return True
        dist[target] = 10**12
        return False

    matching = 0
    while bfs():
        for target in targets:
            if pair_u[target] is None and dfs(target):
                matching += 1
    return {
        "matching_size": matching,
        "matched_target_count": sum(1 for value in pair_u.values() if value is not None),
        "matched_candidate_count": sum(1 for value in pair_v.values() if value is not None),
        "algorithm": "hopcroft_karp_exact_bipartite_target_candidate_matching",
    }


def upper_bounds(moves: list[dict[str, Any]]) -> dict[str, Any]:
    target_to_candidates: dict[int, set[Triple]] = defaultdict(set)
    for move in moves:
        target_to_candidates[int(move["target_id"])].add(triple_from_dict(move["candidate"]))
    unique_targets = len(target_to_candidates)
    unique_candidates = len({candidate for candidates in target_to_candidates.values() for candidate in candidates})
    edge_count = sum(len(candidates) for candidates in target_to_candidates.values())
    simple_bound = min(unique_targets, unique_candidates)
    if not target_to_candidates:
        matching = {
            "matching_size": 0,
            "matched_target_count": 0,
            "matched_candidate_count": 0,
            "algorithm": "not_run_no_edges",
        }
    elif edge_count > EXACT_MATCHING_EDGE_LIMIT:
        matching = {
            "matching_size": simple_bound,
            "matched_target_count": None,
            "matched_candidate_count": None,
            "algorithm": "safe_simple_min_bound_fallback_edge_count_too_large",
            "exact_matching_edge_limit": EXACT_MATCHING_EDGE_LIMIT,
            "edge_count": edge_count,
            "claim_scope": "safe upper bound only; not an exact matching result",
        }
    else:
        matching = hopcroft_karp(target_to_candidates)
    return {
        "unique_supported_targets": unique_targets,
        "unique_auxiliary_candidates": unique_candidates,
        "target_candidate_edge_count": edge_count,
        "simple_min_bound": simple_bound,
        "bipartite_matching_upper_bound": matching,
        "claim_scope": "exact one-to-one target-candidate matching bound before cumulative graph-interaction checks",
    }


def strategy_rank(move: dict[str, Any], strategy: str, aux_relation_counts: Counter[str]) -> tuple[Any, ...]:
    candidate = triple_from_dict(move["candidate"])
    relation = candidate[1]
    base = candidate_sort_key(move)
    if strategy == "relation_diversity_penalty_light_no_cap":
        return (base[0], base[1], aux_relation_counts[relation], relation, *base[2:])
    if strategy == "relation_diversity_penalty_strong_no_cap":
        return (base[0], base[1], aux_relation_counts[relation] * 10, aux_relation_counts[relation], relation, *base[2:])
    if strategy == "fragmentation_penalty_light_no_cap":
        return (base[0], base[1], int(move.get("smaller_side_size") or 0), aux_relation_counts[relation], relation, *base[2:])
    return base


def relation_block_reason(strategy: str, relation: str, aux_counts: Counter[str], selected_count: int) -> str | None:
    if strategy == "max_per_aux_relation_10_no_cap" and aux_counts[relation] >= 10:
        return "relation_concentration_cap_reached"
    if strategy == "max_per_aux_relation_20_no_cap" and aux_counts[relation] >= 20:
        return "relation_concentration_cap_reached"
    if strategy == "p17_cap_25_percent_no_cap" and relation == "P17":
        projected_share = (aux_counts[relation] + 1) / max(selected_count + 1, 1)
        if projected_share > 0.25:
            return "p17_share_cap_reached"
    return None


def current_remove_delta(relation_counts: Counter[str], expected: dict[str, float], relation: str) -> dict[str, Any]:
    return relation_delta(relation_counts, expected, relation, None)


def component_weak_component_count(
    component_ids: set[int],
    base_edges: set[tuple[int, int]],
    removed_base_edges: set[tuple[int, int]],
    auxiliary_edges: set[tuple[int, int]],
) -> int:
    parent = {component: component for component in component_ids}
    rank = {component: 0 for component in component_ids}

    def find(component: int) -> int:
        root = component
        while parent[root] != root:
            root = parent[root]
        while parent[component] != component:
            nxt = parent[component]
            parent[component] = root
            component = nxt
        return root

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root == right_root:
            return
        if rank[left_root] < rank[right_root]:
            left_root, right_root = right_root, left_root
        parent[right_root] = left_root
        if rank[left_root] == rank[right_root]:
            rank[left_root] += 1

    for left, right in base_edges:
        if (left, right) not in removed_base_edges:
            union(left, right)
    for left, right in auxiliary_edges:
        if left != right:
            union(left, right)
    return len({find(component) for component in component_ids})


def connected_after_component_edge_swap(
    edge_counts: Counter[tuple[int, int]],
    neighbors: dict[int, set[int]],
    removed_edge: tuple[int, int],
    added_edge: tuple[int, int],
) -> bool:
    """Return whether removing one component edge and adding one edge preserves connectivity.

    The current component graph is assumed connected. Removing one edge can only
    disconnect it into two pieces; after applying the added edge, connectivity is
    equivalent to reachability between the removed edge endpoints.
    """
    start, goal = removed_edge
    if start == goal:
        return True

    def adjusted_count(left: int, right: int) -> int:
        edge = tuple(sorted((left, right)))
        count = edge_counts.get(edge, 0)
        if edge == removed_edge:
            count -= 1
        if edge == added_edge:
            count += 1
        return count

    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        candidate_neighbors = set(neighbors.get(node, set()))
        if node == added_edge[0]:
            candidate_neighbors.add(added_edge[1])
        elif node == added_edge[1]:
            candidate_neighbors.add(added_edge[0])
        for nxt in candidate_neighbors:
            if nxt in seen or adjusted_count(node, nxt) <= 0:
                continue
            if nxt == goal:
                return True
            seen.add(nxt)
            queue.append(nxt)
    return False


def add_component_edge(
    edge_counts: Counter[tuple[int, int]],
    neighbors: dict[int, set[int]],
    edge: tuple[int, int],
    delta: int,
) -> None:
    edge_counts[edge] += delta
    left, right = edge
    if edge_counts[edge] > 0:
        neighbors[left].add(right)
        neighbors[right].add(left)
        return
    edge_counts.pop(edge, None)
    neighbors[left].discard(right)
    neighbors[right].discard(left)


def ordered_moves_for_strategy(moves: list[dict[str, Any]], strategy: str) -> list[dict[str, Any]]:
    if strategy not in {"relation_diversity_penalty_light_no_cap", "relation_diversity_penalty_strong_no_cap"}:
        return sorted(moves, key=candidate_sort_key)

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for move in sorted(moves, key=candidate_sort_key):
        buckets[triple_from_dict(move["candidate"])[1]].append(move)

    emitted: list[dict[str, Any]] = []
    relation_use_counts: Counter[str] = Counter()
    positions = {relation: 0 for relation in buckets}
    remaining = sum(len(bucket) for bucket in buckets.values())
    penalty_multiplier = 10 if strategy == "relation_diversity_penalty_strong_no_cap" else 1
    while remaining:
        choices = []
        for relation, bucket in buckets.items():
            pos = positions[relation]
            if pos >= len(bucket):
                continue
            move = bucket[pos]
            choices.append((relation_use_counts[relation] * penalty_multiplier, candidate_sort_key(move), relation, move))
        if not choices:
            break
        _penalty, _rank, relation, move = min(choices, key=lambda item: (item[0], item[1], item[2]))
        emitted.append(move)
        relation_use_counts[relation] += 1
        positions[relation] += 1
        remaining -= 1
    return emitted


def select_strategy(
    moves: list[dict[str, Any]],
    graph_triples: set[Triple],
    allocation: dict[str, Any],
    target_context: dict[str, Any],
    strategy: str,
) -> dict[str, Any]:
    relation_expected = allocation["relation_expected"]
    canonical_triples = set(graph_triples)
    auxiliary_triples: set[Triple] = set()
    relation_counts = Counter(r for _h, r, _t in canonical_triples)
    baseline_metrics = compare_relation_counts_to_allocation(relation_counts, allocation)
    baseline_surplus = float(baseline_metrics["total_surplus"])
    baseline_deficit = float(baseline_metrics["total_deficit"])
    baseline_relation_rows = {row["relation"]: row for row in baseline_metrics["per_relation_expected_observed"]}

    selected: list[dict[str, Any]] = []
    skipped = Counter()
    used_targets: set[Triple] = set()
    used_candidates: set[Triple] = set()
    aux_relation_counts: Counter[str] = Counter()
    component_edge_counts: Counter[tuple[int, int]] = Counter(
        {edge: 1 for edge in target_context["bridge_forest"]["bridge_edge_by_components"]}
    )
    component_neighbors: dict[int, set[int]] = defaultdict(set)
    for left, right in component_edge_counts:
        component_neighbors[left].add(right)
        component_neighbors[right].add(left)
    stopping_reason = "source_exhausted"
    processed_candidates = 0

    for move in ordered_moves_for_strategy(moves, strategy):
        processed_candidates += 1
        target = triple_from_dict(move["target_edge"])
        candidate = triple_from_dict(move["candidate"])
        relation = candidate[1]
        if target in used_targets:
            skipped["target_edge_already_used"] += 1
            continue
        if candidate in used_candidates:
            skipped["auxiliary_candidate_already_used"] += 1
            continue
        if target not in canonical_triples:
            skipped["target_edge_not_in_current_canonical_graph"] += 1
            continue
        if candidate in canonical_triples or candidate in auxiliary_triples:
            skipped["candidate_duplicate_in_current_graph"] += 1
            continue
        if relation in relation_expected:
            skipped["candidate_relation_is_allocated"] += 1
            continue
        block = relation_block_reason(strategy, relation, aux_relation_counts, len(selected))
        if block:
            skipped[block] += 1
            continue
        delta = current_remove_delta(relation_counts, relation_expected, target[1])
        if float(delta["surplus_delta"]) >= 0:
            skipped["target_relation_no_longer_surplus_reducing"] += 1
            continue
        if float(delta["deficit_delta"]) > 0:
            skipped["target_removal_would_increase_deficit"] += 1
            continue
        trial_canonical = set(canonical_triples)
        trial_auxiliary = set(auxiliary_triples)
        trial_canonical.remove(target)
        trial_auxiliary.add(candidate)
        full_triples = trial_canonical | trial_auxiliary
        duplicate_triples = len(trial_canonical) + len(trial_auxiliary) - len(full_triples)
        trial_counts = Counter(relation_counts)
        trial_counts[target[1]] -= 1
        allocation_metrics = compare_relation_counts_to_allocation(trial_counts, allocation)
        target_component_edge = tuple(sorted(int(value) for value in move["target_component_edge"]))
        candidate_component_edge = tuple(sorted(int(value) for value in move["candidate_component_edge"]))
        if duplicate_triples != 0:
            skipped["duplicate_triple_after_move"] += 1
            continue
        if not connected_after_component_edge_swap(
            component_edge_counts,
            component_neighbors,
            target_component_edge,
            candidate_component_edge,
        ):
            skipped["full_graph_would_fragment"] += 1
            continue
        if target_component_edge not in {
            tuple(sorted(int(value) for value in edge))
            for edge in move.get("candidate_crossed_component_edges", [])
        }:
            skipped["candidate_does_not_cover_target_bridge_cut"] += 1
            continue
        if allocation_metrics["allocated_relations_observed"] != len(relation_expected):
            skipped["canonical_relation_coverage_would_drop"] += 1
            continue
        if allocation_metrics["zero_allocated_relations"] != 0:
            skipped["zero_allocated_relation_would_appear"] += 1
            continue
        if float(allocation_metrics["total_deficit"]) - baseline_deficit > 0:
            skipped["cumulative_deficit_would_increase"] += 1
            continue

        canonical_triples = trial_canonical
        auxiliary_triples = trial_auxiliary
        relation_counts = trial_counts
        add_component_edge(component_edge_counts, component_neighbors, target_component_edge, -1)
        add_component_edge(component_edge_counts, component_neighbors, candidate_component_edge, 1)
        used_targets.add(target)
        used_candidates.add(candidate)
        aux_relation_counts[relation] += 1
        selected.append(
            {
                **move,
                "selection_rank": len(selected) + 1,
                "current_move_balance_delta": delta,
                "cumulative_canonical_surplus_delta": float(allocation_metrics["total_surplus"]) - baseline_surplus,
                "cumulative_canonical_deficit_delta": float(allocation_metrics["total_deficit"]) - baseline_deficit,
            }
        )
    if not selected:
        stopping_reason = "no_moves_selected"

    final_metrics = compare_relation_counts_to_allocation(relation_counts, allocation)
    final_relation_rows = {row["relation"]: row for row in final_metrics["per_relation_expected_observed"]}
    full_triples = set(canonical_triples) | set(auxiliary_triples)
    full_connectivity = summarize_connectivity(full_triples)
    canonical_connectivity = summarize_connectivity(canonical_triples)
    removed_triples = set(graph_triples) - canonical_triples
    removed_relation_counts = Counter(r for _h, r, _t in removed_triples)
    selected_count = len(selected)
    max_relation_count = max(aux_relation_counts.values(), default=0)
    max_relation_share = max_relation_count / selected_count if selected_count else 0.0
    canonical_surplus_delta = float(final_metrics["total_surplus"]) - baseline_surplus
    canonical_deficit_delta = float(final_metrics["total_deficit"]) - baseline_deficit
    surplus_reduction = abs(canonical_surplus_delta)
    duplicate_triples = len(canonical_triples) + len(auxiliary_triples) - len(full_triples)
    composition_delta = sum(float((move.get("pattern_total_delta") or {}).get("composition", 0.0)) for move in selected)
    key_relation_deltas = {}
    for relation in KEY_RELATIONS:
        before = baseline_relation_rows.get(relation, {"surplus": 0.0, "deficit": 0.0, "observed_count": 0})
        after = final_relation_rows.get(relation, {"surplus": 0.0, "deficit": 0.0, "observed_count": 0})
        key_relation_deltas[relation] = {
            "observed_delta": int(after["observed_count"]) - int(before["observed_count"]),
            "surplus_delta": float(after["surplus"]) - float(before["surplus"]),
            "deficit_delta": float(after["deficit"]) - float(before["deficit"]),
        }
    thresholds = {
        "surplus_reduction_gte_670": surplus_reduction >= SURPLUS_REDUCTION_THRESHOLD,
        "deficit_delta_le_0": canonical_deficit_delta <= 0,
        "full_graph_weak_components_eq_1": full_connectivity["weak_component_count"] == 1,
        "canonical_relation_coverage_eq_139": final_metrics["allocated_relations_observed"] == 139,
        "duplicate_triples_eq_0": duplicate_triples == 0,
        "max_single_auxiliary_relation_share_le_0_40": max_relation_share <= MAX_SINGLE_AUX_RELATION_SHARE,
    }
    return {
        "strategy": strategy,
        "selected_auxiliary_edge_count": selected_count,
        "removed_canonical_edge_count": len(removed_triples),
        "canonical_surplus_before": baseline_surplus,
        "canonical_surplus_after": float(final_metrics["total_surplus"]),
        "canonical_surplus_delta": canonical_surplus_delta,
        "canonical_deficit_before": baseline_deficit,
        "canonical_deficit_after": float(final_metrics["total_deficit"]),
        "canonical_deficit_delta": canonical_deficit_delta,
        "composition_surplus_delta": composition_delta,
        "key_relation_deltas": key_relation_deltas,
        "remaining_total_surplus": float(final_metrics["total_surplus"]),
        "remaining_total_deficit": float(final_metrics["total_deficit"]),
        "full_graph_weak_components": full_connectivity["weak_component_count"],
        "canonical_only_weak_components": canonical_connectivity["weak_component_count"],
        "canonical_only_largest_component_ratio": canonical_connectivity["largest_weak_component_ratio"],
        "duplicate_triple_count": duplicate_triples,
        "allocated_relations_observed": final_metrics["allocated_relations_observed"],
        "zero_allocated_relations": final_metrics["zero_allocated_relations"],
        "auxiliary_relation_count": len(aux_relation_counts),
        "auxiliary_relation_distribution": dict(sorted(aux_relation_counts.items())),
        "p17_count": aux_relation_counts.get("P17", 0),
        "p17_share": aux_relation_counts.get("P17", 0) / selected_count if selected_count else 0.0,
        "max_single_auxiliary_relation_count": max_relation_count,
        "max_single_auxiliary_relation_share": max_relation_share,
        "top_20_auxiliary_relations": sorted(aux_relation_counts.items(), key=lambda item: (-item[1], item[0]))[:20],
        "top_20_removed_canonical_relations": sorted(removed_relation_counts.items(), key=lambda item: (-item[1], item[0]))[:20],
        "skipped_reason_counts": dict(sorted(skipped.items())),
        "stopping_reason": stopping_reason,
        "candidate_moves_processed": processed_candidates,
        "candidate_moves_unprocessed": max(len(moves) - processed_candidates, 0),
        "auxiliary_cost_per_surplus_removed": selected_count / surplus_reduction if surplus_reduction else None,
        "surplus_reduction_ratio_of_b0_surplus": surplus_reduction / B0_SURPLUS,
        "surplus_reduction_percent_of_b0_surplus": 100.0 * surplus_reduction / B0_SURPLUS,
        "decision_thresholds": thresholds,
        "crosses_decision_thresholds": all(thresholds.values()),
        "selected_examples": selected[:20],
    }


def baseline_summary(parent_graph: Path, allocation_path: Path) -> dict[str, Any]:
    report = evaluate_candidate(parent_graph, allocation_path, "B0", "B0 provisional connected baseline")
    graph = report["graph_metrics"]
    allocation = report["allocation_metrics"]
    composition = next(
        (row for row in allocation["pattern_level_expected_observed"] if row["pattern"] == "composition"),
        None,
    )
    return {
        "unique_canonical_triples": graph["unique_triples"],
        "unique_entities": graph["unique_entities"],
        "unique_relations": graph["unique_relations"],
        "weak_components": graph["weak_component_count"],
        "largest_component_ratio": graph["largest_weak_component_ratio"],
        "duplicate_triple_count": graph["duplicate_triple_count"],
        "allocated_relations_observed": allocation["allocated_relations_observed"],
        "zero_allocated_relations": allocation["zero_allocated_relations"],
        "total_surplus": allocation["total_surplus"],
        "total_deficit": allocation["total_deficit"],
        "composition_surplus": composition["surplus"] if composition else None,
    }


def recommendation(rows: list[dict[str, Any]], scan: dict[str, Any]) -> dict[str, Any]:
    passing = [row for row in rows if row["crosses_decision_thresholds"]]
    if passing:
        best = max(passing, key=lambda row: abs(float(row["canonical_surplus_delta"])))
        return {
            "recommendation": "continue_to_best_auxiliary_candidate_generation",
            "best_strategy": best["strategy"],
            "step2_candidate_generation_justified": True,
            "reason": "At least one expanded frozen-source strategy crosses the surplus, constraint, and relation-diversity thresholds.",
        }
    if not scan["moves"]:
        return {
            "recommendation": "blocked_by_source_boundary",
            "best_strategy": None,
            "step2_candidate_generation_justified": False,
            "reason": "No surplus-reducing observed unallocated cut-crossing moves were found in the expanded frozen source scan.",
        }
    best = max(rows, key=lambda row: (abs(float(row["canonical_surplus_delta"])), -float(row["max_single_auxiliary_relation_share"])))
    failed_full_connectivity = any(
        row["full_graph_weak_components"] != 1
        and abs(float(row["canonical_surplus_delta"])) >= SURPLUS_REDUCTION_THRESHOLD
        for row in rows
    )
    failed_concentration = any(row["max_single_auxiliary_relation_share"] > MAX_SINGLE_AUX_RELATION_SHARE for row in rows)
    if best["selected_auxiliary_edge_count"] == 0:
        return {
            "recommendation": "close_auxiliary_branch_insufficient_gain",
            "best_strategy": best["strategy"],
            "step2_candidate_generation_justified": False,
            "reason": "Expanded frozen evidence produced candidate moves, but hard constraints prevented useful auxiliary selection.",
        }
    if failed_full_connectivity:
        return {
            "recommendation": "close_auxiliary_branch_connectivity_failure",
            "best_strategy": best["strategy"],
            "step2_candidate_generation_justified": False,
            "reason": (
                "Expanded frozen-source strategies can reduce surplus, but at least one otherwise-large strategy "
                "fails the cumulative full-graph connectivity threshold. This is a connectivity failure, not an "
                "insufficient-gain result."
            ),
            "failed_full_connectivity_in_any_strategy": True,
            "failed_auxiliary_relation_concentration_in_any_strategy": failed_concentration,
        }
    return {
        "recommendation": "close_auxiliary_branch_insufficient_gain",
        "best_strategy": best["strategy"],
        "step2_candidate_generation_justified": False,
        "reason": (
            "No expanded frozen-source strategy crosses all Step 2 thresholds. "
            "Large surplus reductions are not sufficient when final full connectivity, duplicate, coverage, "
            "deficit, and auxiliary relation-concentration checks are considered."
        ),
        "failed_full_connectivity_in_any_strategy": failed_full_connectivity,
        "failed_auxiliary_relation_concentration_in_any_strategy": failed_concentration,
    }


def write_table(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "strategy",
        "selected_auxiliary_edge_count",
        "removed_canonical_edge_count",
        "canonical_surplus_delta",
        "canonical_deficit_delta",
        "composition_surplus_delta",
        "remaining_total_surplus",
        "remaining_total_deficit",
        "full_graph_weak_components",
        "canonical_only_weak_components",
        "canonical_only_largest_component_ratio",
        "auxiliary_relation_count",
        "p17_count",
        "p17_share",
        "max_single_auxiliary_relation_share",
        "surplus_reduction_percent_of_b0_surplus",
        "auxiliary_cost_per_surplus_removed",
        "stopping_reason",
        "crosses_decision_thresholds",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: fmt(row.get(field, "")) for field in fields})


def write_summary(path: Path, report: dict[str, Any]) -> None:
    rec = report["recommendation"]
    rows = report["strategy_results"]
    best = next((row for row in rows if row["strategy"] == rec.get("best_strategy")), rows[0] if rows else None)
    universe = report["target_universe"]
    scan = report["expanded_source_scan"]["aggregate_counts"]
    lines = [
        "# C5-H2 Expanded Auxiliary Saturation Audit",
        "",
        f"Recommendation: `{rec['recommendation']}`",
        "",
        "This audit expands C5-H2 from the earlier bounded cut-crossing evidence to all B0 surplus bridge-removal targets found under current frozen local evidence.",
        "It does not write graph JSONL outputs and does not update the candidate registry.",
        "",
        "## Target Universe",
        "",
        f"- Surplus bridge targets: `{universe['surplus_bridge_targets']}`",
        f"- Surplus non-bridge targets: `{universe['surplus_non_bridge_targets']}`",
        f"- Non-surplus bridge targets: `{universe['non_surplus_bridge_targets']}`",
        f"- Surplus relations considered: `{len(universe['surplus_relations'])}`",
        "",
        "## Expanded Frozen Source Scan",
        "",
        f"- Rows scanned: `{scan['rows_scanned']}`",
        f"- Candidate triples parsed: `{scan['candidate_triples_parsed']}`",
        f"- Observed unallocated candidate rows: `{scan['observed_unallocated_candidate_rows']}`",
        f"- Cut-crossing candidate-target pairs: `{scan['cut_crossing_candidate_target_pairs']}`",
        f"- Unique auxiliary candidates: `{scan['unique_auxiliary_candidates']}`",
        f"- Unique supported targets: `{scan['unique_supported_targets']}`",
        f"- Targets without support: `{scan['targets_without_support']}`",
        "",
        "## Upper Bounds",
        "",
        f"- Simple min bound: `{report['upper_bounds']['simple_min_bound']}`",
        f"- Bipartite matching upper bound: `{report['upper_bounds']['bipartite_matching_upper_bound']['matching_size']}`",
        "",
        "## Strategy Results",
        "",
        "| Strategy | Aux | Surplus Delta | Deficit Delta | Canonical WCC | P17 Share | Max Relation Share | B0 Surplus Reduced | Stop | Thresholds |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| `{strategy}` | {aux} | {surplus:.0f} | {deficit:.0f} | {wcc} | {p17:.3f} | {max_share:.3f} | {pct:.3f}% | `{stop}` | `{passed}` |".format(
                strategy=row["strategy"],
                aux=row["selected_auxiliary_edge_count"],
                surplus=float(row["canonical_surplus_delta"]),
                deficit=float(row["canonical_deficit_delta"]),
                wcc=row["canonical_only_weak_components"],
                p17=float(row["p17_share"]),
                max_share=float(row["max_single_auxiliary_relation_share"]),
                pct=float(row["surplus_reduction_percent_of_b0_surplus"]),
                stop=row["stopping_reason"],
                passed=str(row["crosses_decision_thresholds"]).lower(),
            )
        )
    lines.extend(["", "## Decision", "", rec["reason"]])
    if best:
        lines.extend(
            [
                "",
                "## Best Observed Strategy",
                "",
                f"- Strategy: `{best['strategy']}`",
                f"- Selected auxiliary edges: `{best['selected_auxiliary_edge_count']}`",
                f"- Canonical surplus delta: `{best['canonical_surplus_delta']}`",
                f"- B0 surplus reduction: `{best['surplus_reduction_percent_of_b0_surplus']:.3f}%`",
                f"- Canonical deficit delta: `{best['canonical_deficit_delta']}`",
                f"- Full graph weak components: `{best['full_graph_weak_components']}`",
                f"- Canonical-only weak components: `{best['canonical_only_weak_components']}`",
                f"- Max auxiliary relation share: `{best['max_single_auxiliary_relation_share']:.3f}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Evidence Strength",
            "",
            "This result is stronger than the earlier 200-cut bounded C5-H2 saturation audit because it scans all surplus B0 bridge targets available under the current frozen source boundary.",
            "It is still not a global impossibility proof: live WDQS, new source construction, synthetic edges, and unimplemented multi-objective generators remain outside scope.",
            "No WDQS query, LLM call, SLURM submission, synthetic triple generation, graph candidate output, or registry update was performed.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    config_path = resolve_path(args.config)
    policy_path = resolve_path(args.policy)
    c5_report_path = resolve_path(args.c5_report)
    c4_2_report_path = resolve_path(args.c4_2_report)
    config = load_c5_config(config_path)
    policy = load_json(policy_path)
    c5_report = load_json(c5_report_path)
    c4_2_report = load_json(c4_2_report_path)
    parent_graph = resolve_path(config["parent_graph_path"])
    allocation_path = resolve_path(config["allocation_path"])
    print("phase=load_inputs", file=sys.stderr, flush=True)
    graph_triples = set(load_graph_triples(parent_graph))
    allocation = load_allocation(allocation_path)
    print("phase=build_target_universe", file=sys.stderr, flush=True)
    target_context = build_target_universe(graph_triples, allocation)
    print(
        f"phase=scan_sources surplus_bridge_targets={target_context['target_stats']['surplus_bridge_targets']}",
        file=sys.stderr,
        flush=True,
    )
    scan = scan_sources_expanded(graph_triples, allocation, target_context)
    moves = scan.pop("moves")
    print(f"phase=upper_bounds moves={len(moves)}", file=sys.stderr, flush=True)
    bounds = upper_bounds(moves)
    rows = []
    for strategy in args.strategies:
        print(f"phase=select_strategy strategy={strategy}", file=sys.stderr, flush=True)
        rows.append(select_strategy(moves, graph_triples, allocation, target_context, strategy))
    rec = recommendation(rows, {**scan, "moves": moves})
    finished = time.time()
    target_stats = target_context["target_stats"]
    report = {
        "schema_version": "c5-h2-expanded-auxiliary-saturation-audit-v1",
        "audit_id": "C5_H2_expanded_auxiliary_support_saturation",
        "candidate_id": config["candidate_id"],
        "parent_candidate_id": config["parent_candidate_id"],
        "created_by": "tools/graph_candidate_generation/c5_audit_h2_auxiliary_expanded_saturation.py",
        "status": "audit_only_no_graph_generated",
        "inputs": {
            "config": {"path": str(args.config), "sha256": sha256_file(config_path)},
            "policy": {"path": str(args.policy), "sha256": sha256_file(policy_path)},
            "c5_h1_h2_probe_report": {"path": str(args.c5_report), "sha256": sha256_file(c5_report_path)},
            "c4_2_local_cut_crossing_search": {"path": str(args.c4_2_report), "sha256": sha256_file(c4_2_report_path)},
            "parent_graph": {"path": config["parent_graph_path"], "sha256": sha256_file(parent_graph)},
            "allocation": {"path": config["allocation_path"], "sha256": sha256_file(allocation_path)},
        },
        "policy_context": {
            "allowed_edge_classes": policy.get("allowed_edge_classes"),
            "disallowed_edge_classes": policy.get("disallowed_edge_classes"),
            "methodological_acceptance": policy.get("methodological_acceptance"),
        },
        "source_boundary": {
            "old_c5_max_cuts": (c5_report.get("limits") or {}).get("max_cuts"),
            "old_c5_max_candidates": (c5_report.get("limits") or {}).get("max_candidates"),
            "old_c4_2_max_target_edges": (c4_2_report.get("limits") or {}).get("max_target_edges"),
            "expanded_cut_cap": None,
            "expanded_candidate_pair_cap": None,
            "claim_scope": "all current frozen local sources exposed by candidate_sources(), not live WDQS or global candidate space",
        },
        "target_universe": {
            "b0_unique_triples": len(graph_triples),
            "simple_bridge_pairs": len(target_context["simple_bridge_pairs"]),
            "bridge_critical_pairs": len(target_context["bridge_critical_pairs"]),
            "surplus_bridge_targets": target_stats["surplus_bridge_targets"],
            "surplus_non_bridge_targets": target_stats["surplus_non_bridge_targets"],
            "non_surplus_bridge_targets": target_stats["non_surplus_bridge_targets"],
            "non_surplus_non_bridge_triples": target_stats["non_surplus_non_bridge_triples"],
            "surplus_relations": sorted(target_context["surplus_relations"]),
            "target_examples_first_20": list(target_context["target_by_id"].values())[:20],
        },
        "expanded_source_scan": scan,
        "upper_bounds": bounds,
        "baseline_b0_metrics": baseline_summary(parent_graph, allocation_path),
        "decision_thresholds": {
            "minimum_canonical_surplus_reduction": SURPLUS_REDUCTION_THRESHOLD,
            "minimum_canonical_surplus_reduction_ratio": SURPLUS_REDUCTION_THRESHOLD / B0_SURPLUS,
            "maximum_single_auxiliary_relation_share": MAX_SINGLE_AUX_RELATION_SHARE,
            "canonical_deficit_delta_max": 0,
            "full_graph_weak_components_required": 1,
            "canonical_relation_coverage_required": 139,
            "duplicate_triples_required": 0,
        },
        "strategy_results": rows,
        "recommendation": rec,
        "evidence_strength": {
            "proven_under_expanded_frozen_evidence": [
                "surplus bridge target universe for the B0 frozen graph",
                "frozen local source scan through configured candidate source directories",
                "deterministic no-cap greedy strategy outcomes",
                "one-to-one target-candidate matching upper bound before cumulative graph constraints",
            ],
            "not_proven_globally": [
                "all possible live WDQS auxiliary candidates",
                "all possible synthetic pattern-derived candidates",
                "all possible multi-objective graph construction algorithms",
                "global optimality over every candidate graph edit sequence",
            ],
            "old_151_interpretation": "The previous 151-move ceiling was inherited from bounded source evidence; this audit tests whether that was source-bound under current frozen local files.",
        },
        "notes": [
            "No graph JSONL outputs were written by this audit.",
            "No WDQS query was made.",
            "No LLM call was made.",
            "No synthetic triples were used.",
            "No SLURM job was submitted.",
            "candidate_registry.v1.json was not updated.",
            "B0/C1 graph artifacts were read only and not modified.",
        ],
        "runtime": {
            "started_on": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "finished_on": datetime.fromtimestamp(finished, timezone.utc).isoformat(),
            "elapsed_seconds": round(finished - started, 6),
        },
    }
    return report


def main() -> int:
    args = parse_args()
    unknown = sorted(set(args.strategies) - set(STRATEGIES))
    if unknown:
        raise ValueError(f"Unknown strategies: {unknown}")
    if not args.dry_run:
        refuse_overwrite(args.force)
    report = run_audit(args)
    rec = report["recommendation"]
    if args.dry_run:
        scan = report["expanded_source_scan"]["aggregate_counts"]
        print("dry_run=true")
        print(f"surplus_bridge_targets={report['target_universe']['surplus_bridge_targets']}")
        print(f"rows_scanned={scan['rows_scanned']}")
        print(f"cut_crossing_candidate_target_pairs={scan['cut_crossing_candidate_target_pairs']}")
        print(f"unique_supported_targets={scan['unique_supported_targets']}")
        print(f"matching_upper_bound={report['upper_bounds']['bipartite_matching_upper_bound']['matching_size']}")
        print(f"recommendation={rec['recommendation']}")
        print("outputs_written=false")
        return 0

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_summary(REPORT_MD, report)
    write_table(REPORT_TSV, report["strategy_results"])
    scan = report["expanded_source_scan"]["aggregate_counts"]
    best_strategy = rec.get("best_strategy")
    best = next((row for row in report["strategy_results"] if row["strategy"] == best_strategy), None)
    print(f"report={REPORT_JSON}")
    print(f"surplus_bridge_targets={report['target_universe']['surplus_bridge_targets']}")
    print(f"cut_crossing_candidate_target_pairs={scan['cut_crossing_candidate_target_pairs']}")
    print(f"unique_supported_targets={scan['unique_supported_targets']}")
    print(f"matching_upper_bound={report['upper_bounds']['bipartite_matching_upper_bound']['matching_size']}")
    print(f"recommendation={rec['recommendation']}")
    if best:
        print(f"best_strategy={best['strategy']}")
        print(f"best_selected_auxiliary_edges={best['selected_auxiliary_edge_count']}")
        print(f"best_canonical_surplus_delta={best['canonical_surplus_delta']}")
        print(f"best_surplus_reduction_percent={best['surplus_reduction_percent_of_b0_surplus']:.6f}")
    print(f"step2_candidate_generation_justified={str(rec['step2_candidate_generation_justified']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
