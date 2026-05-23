"""Pure relation support and genericity matrix helpers."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


MATRIX_MODE_OPTIONS = [
    "log1p_balanced_norm",
    "log1p_row_norm",
    "log1p_col_norm",
    "adjacency_log1p",
    "adjacency_support",
    "two_hop_log1p",
]


def _unique_preserve(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, str) and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def build_square_adjacency_matrix(
    df_pairs: pd.DataFrame,
    *,
    min_support: int,
    extra_relations: Optional[list[str]] = None,
) -> tuple[list[str], np.ndarray]:
    """Build square adjacency from filtered pair counts with support thresholding."""
    edge_sum = df_pairs.groupby(["r1", "r2"], as_index=False)["total"].sum()
    edge_sum = edge_sum[edge_sum["total"] >= int(min_support)].copy()

    nodes: set[str] = set()
    if not edge_sum.empty:
        nodes.update(edge_sum["r1"].tolist())
        nodes.update(edge_sum["r2"].tolist())
    if extra_relations:
        nodes.update(extra_relations)
    relations_universe = sorted(nodes)

    n = len(relations_universe)
    adjacency = np.zeros((n, n), dtype=float)
    rel_to_idx = {relation: i for i, relation in enumerate(relations_universe)}
    for row in edge_sum.itertuples(index=False):
        i = rel_to_idx[row.r1]
        j = rel_to_idx[row.r2]
        adjacency[i, j] = float(row.total)
    return relations_universe, adjacency


def build_weight_matrix(adjacency: np.ndarray, *, matrix_mode: str) -> np.ndarray:
    """Build relation-weight matrix from adjacency counts."""

    def _row_normalize(matrix: np.ndarray) -> np.ndarray:
        sums = matrix.sum(axis=1, keepdims=True)
        return np.divide(matrix, sums, out=np.zeros_like(matrix), where=sums > 0)

    def _col_normalize(matrix: np.ndarray) -> np.ndarray:
        sums = matrix.sum(axis=0, keepdims=True)
        return np.divide(matrix, sums, out=np.zeros_like(matrix), where=sums > 0)

    if matrix_mode == "adjacency_support":
        return adjacency.copy()
    if matrix_mode == "adjacency_log1p":
        return np.log1p(adjacency)
    if matrix_mode == "two_hop_log1p":
        return np.log1p(adjacency @ adjacency)
    if matrix_mode == "log1p_row_norm":
        return _row_normalize(np.log1p(adjacency))
    if matrix_mode == "log1p_col_norm":
        return _col_normalize(np.log1p(adjacency))
    if matrix_mode == "log1p_balanced_norm":
        base = np.log1p(adjacency)
        return 0.5 * (_row_normalize(base) + _col_normalize(base))
    raise ValueError(f"Unknown matrix_mode: {matrix_mode}")


def extract_relation_submatrix(
    matrix: np.ndarray,
    relations_universe: list[str],
    relations: list[str],
) -> tuple[list[str], np.ndarray]:
    """Slice a square matrix down to a relation subset while preserving order."""
    rel_to_idx = {relation: i for i, relation in enumerate(relations_universe)}
    rels = [relation for relation in _unique_preserve(relations) if relation in rel_to_idx]
    if not rels:
        return [], np.zeros((0, 0), dtype=float)
    idx = [rel_to_idx[relation] for relation in rels]
    return rels, matrix[np.ix_(idx, idx)]


def matrix_to_nested_json_dict(relations: list[str], matrix: np.ndarray) -> dict[str, dict[str, float]]:
    """Serialize a square matrix into the JSON shape expected by Stage1 genericity."""
    out: dict[str, dict[str, float]] = {}
    for i, r_from in enumerate(relations):
        row: dict[str, float] = {}
        for j, r_to in enumerate(relations):
            value = float(matrix[i, j])
            if value != 0.0:
                row[r_to] = value
        out[r_from] = row
    return out
