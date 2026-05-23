"""Weak-connectivity metrics for graph candidate evaluation."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from .graph_io import Triple, unique_triples


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.rank: dict[str, int] = {}

    def add(self, item: str) -> None:
        if item not in self.parent:
            self.parent[item] = item
            self.rank[item] = 0

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            parent = self.parent[item]
            self.parent[item] = root
            item = parent
        return root

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1

    def component_sizes(self) -> list[int]:
        counts: Counter[str] = Counter()
        for item in list(self.parent):
            counts[self.find(item)] += 1
        return list(counts.values())


def component_sizes_for_triples(triples: Iterable[Triple]) -> list[int]:
    uf = UnionFind()
    for h, _r, t in unique_triples(triples):
        uf.union(h, t)
    return uf.component_sizes()


def summarize_connectivity(triples: Iterable[Triple]) -> dict[str, Any]:
    """Compute weak component metrics from unique triples."""
    unique = unique_triples(triples)
    entities: set[str] = set()
    uf = UnionFind()
    for h, _r, t in unique:
        entities.add(h)
        entities.add(t)
        uf.union(h, t)

    component_sizes = uf.component_sizes()
    largest_component_size = max(component_sizes) if component_sizes else 0
    largest_component_ratio = largest_component_size / len(entities) if entities else 0.0
    return {
        "weak_component_count": len(component_sizes),
        "largest_weak_component_size": largest_component_size,
        "largest_weak_component_ratio": largest_component_ratio,
        "component_sizes": sorted(component_sizes, reverse=True),
        "connectivity_note": "Weak connectivity is computed from unique triples.",
    }

