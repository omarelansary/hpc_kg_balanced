"""Pure allocation/export helpers for Phase I pattern groups."""

from __future__ import annotations

from typing import Mapping

import numpy as np

from src.kg_building.bidirectional_triple_allocation import allocate_for_patterns

from .genericity_matrix import build_weight_matrix


def run_phase3_allocation(
    pattern_groups: dict[str, list[str]],
    eta_per_group: dict[str, int],
    relations_universe: list[str],
    adjacency: np.ndarray,
    *,
    matrix_mode: str,
    temperature: float,
    epsilon: float,
    integerize: bool,
) -> tuple[np.ndarray, dict]:
    """Run allocation over all non-empty pattern groups and return selected matrix plus results."""
    weight_matrix = build_weight_matrix(adjacency, matrix_mode=matrix_mode)

    non_empty_groups = {name: relations for name, relations in pattern_groups.items() if len(relations) > 0}
    non_empty_eta = {name: int(eta_per_group.get(name, 0)) for name in non_empty_groups}
    if not non_empty_groups:
        return weight_matrix, {}

    results = allocate_for_patterns(
        W=weight_matrix,
        relations_universe=relations_universe,
        pattern_groups=non_empty_groups,
        eta_per_group=non_empty_eta,
        temperature=float(temperature),
        epsilon=float(epsilon),
        integerize=bool(integerize),
    )
    return weight_matrix, results


def allocation_results_to_rows(
    alloc_results: Mapping[str, object],
    relations_universe: list[str],
    weight_matrix: np.ndarray,
    *,
    relation_dom_rng_class: Mapping[str, str] | None = None,
) -> list[dict[str, object]]:
    """Convert allocation results to the dashboard allocation JSON row format."""
    rows: list[dict[str, object]] = []
    relation_dom_rng_class = relation_dom_rng_class or {}

    for pattern, result in alloc_results.items():
        idx = [relations_universe.index(relation) for relation in result.relations]
        _ = weight_matrix[np.ix_(idx, idx)]
        for i, relation in enumerate(result.relations):
            row = {
                "pattern": pattern,
                "relation": relation,
                "eta_total": int(result.eta_total),
                "forward_score": float(result.forward_scores[i]),
                "backward_score": float(result.backward_scores[i]),
                "p_forward": float(result.p_forward[i]),
                "p_backward": float(result.p_backward[i]),
                "p_avg": float(result.p_avg[i]),
                "eta_expected": float(result.eta_expected[i]),
                "eta_integer": int(result.eta_integer[i]),
            }
            if relation_dom_rng_class:
                row["relation_dom_rng_class"] = relation_dom_rng_class.get(str(relation), "UNKNOWN")
            rows.append(row)

    return sorted(rows, key=lambda row: (str(row["pattern"]), -int(row["eta_integer"]), -float(row["eta_expected"])))


def build_allocation_payload(
    *,
    config: dict[str, object],
    eta_per_group: dict[str, int],
    pattern_groups: dict[str, list[str]],
    relations_universe: list[str],
    allocation_rows: list[dict[str, object]],
) -> dict[str, object]:
    """Build the allocation JSON payload exported by the dashboard."""
    return {
        "config": config,
        "eta_per_group": eta_per_group,
        "pattern_groups": pattern_groups,
        "relations_universe": relations_universe,
        "allocations": allocation_rows,
    }


def positive_eta_relations(allocation_rows: list[dict[str, object]]) -> list[str]:
    """Return positive-eta relations while preserving first-seen allocation row order."""
    out: list[str] = []
    seen: set[str] = set()
    for row in allocation_rows:
        relation = row.get("relation")
        if not isinstance(relation, str):
            continue
        eta = int(row.get("eta_integer", 0) or 0)
        if eta > 0 and relation not in seen:
            seen.add(relation)
            out.append(relation)
    return out


def normalize_allocation_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return stable allocation rows for semantic comparison."""
    normalized = []
    for row in rows:
        normalized.append(
            {
                "pattern": str(row["pattern"]),
                "relation": str(row["relation"]),
                "eta_total": int(row["eta_total"]),
                "eta_integer": int(row["eta_integer"]),
                "eta_expected": float(row["eta_expected"]),
            }
        )
    return sorted(normalized, key=lambda row: (row["pattern"], row["relation"]))
