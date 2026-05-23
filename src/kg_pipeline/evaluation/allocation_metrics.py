"""Allocation loading and relation-level balance metrics."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def extract_eta(row: dict[str, Any]) -> float:
    """Extract eta with the evaluator-compatible precedence."""
    for key in ("eta_integer", "eta", "eta_expected"):
        value = row.get(key)
        if value is not None:
            return float(value)
    return 0.0


def load_allocation_payload(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_allocation(path: str | Path) -> dict[str, Any]:
    """Load allocation JSON and normalize positive eta rows."""
    data = load_allocation_payload(path)
    allocations = data.get("allocations") or []
    pattern_groups = data.get("pattern_groups") or {}
    eta_per_group = data.get("eta_per_group") or {}

    relation_expected: dict[str, float] = defaultdict(float)
    relation_patterns: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pattern_expected: dict[str, float] = defaultdict(float)
    positive_rows = 0

    for row in allocations:
        relation = row.get("relation")
        pattern = row.get("pattern")
        if not relation:
            continue
        eta = extract_eta(row)
        if eta <= 0:
            continue
        relation = str(relation)
        positive_rows += 1
        relation_expected[relation] += eta
        relation_patterns[relation].append({"pattern": pattern, "eta": eta})
        if pattern:
            pattern_expected[str(pattern)] += eta

    return {
        "raw_payload": data,
        "raw_keys": sorted(data.keys()),
        "config": data.get("config"),
        "eta_per_group": eta_per_group,
        "pattern_groups": pattern_groups,
        "pattern_groups_relation_counts": {
            pattern: len(relations) for pattern, relations in sorted(pattern_groups.items())
        },
        "positive_allocation_rows": positive_rows,
        "relation_expected": dict(sorted(relation_expected.items())),
        "relation_patterns": {k: v for k, v in sorted(relation_patterns.items())},
        "pattern_expected": dict(sorted(pattern_expected.items())),
        "extraction_notes": {
            "eta_field_precedence": ["eta_integer", "eta", "eta_expected"],
            "allocation_relations_definition": "unique relations with positive extracted eta",
            "pattern_observed_definition": (
                "observed relation counts apportioned across that relation's positive "
                "allocation rows in proportion to row eta; this avoids double-counting "
                "multi-pattern relations"
            ),
        },
    }


def relation_expected_count_map(allocation: dict[str, Any]) -> dict[str, float]:
    return dict(allocation["relation_expected"])


def observed_relation_counts(relation_counts: dict[str, int] | Counter[str]) -> Counter[str]:
    return Counter({str(relation): int(count) for relation, count in relation_counts.items()})


def compare_relation_counts_to_allocation(
    relation_counts: dict[str, int] | Counter[str],
    allocation: dict[str, Any],
) -> dict[str, Any]:
    """Compare observed unique relation counts to expected allocation eta."""
    observed_counts = observed_relation_counts(relation_counts)
    relation_expected = relation_expected_count_map(allocation)
    relation_patterns = allocation["relation_patterns"]
    allocated_relations = set(relation_expected)

    per_relation: list[dict[str, Any]] = []
    total_expected = 0.0
    total_observed = 0
    total_deficit = 0.0
    total_surplus = 0.0
    observed_allocated = 0
    zero_allocated: list[str] = []

    for relation in sorted(allocated_relations):
        expected = float(relation_expected[relation])
        observed = int(observed_counts.get(relation, 0))
        deficit = max(expected - observed, 0.0)
        surplus = max(observed - expected, 0.0)
        total_expected += expected
        total_observed += observed
        total_deficit += deficit
        total_surplus += surplus
        if observed > 0:
            observed_allocated += 1
        else:
            zero_allocated.append(relation)
        per_relation.append(
            {
                "relation": relation,
                "expected_eta": expected,
                "observed_count": observed,
                "deficit": deficit,
                "surplus": surplus,
                "patterns": [p["pattern"] for p in relation_patterns.get(relation, [])],
            }
        )

    top_overfilled = sorted(
        (row for row in per_relation if row["surplus"] > 0),
        key=lambda row: (-row["surplus"], row["relation"]),
    )[:25]
    top_underfilled = sorted(
        (row for row in per_relation if row["deficit"] > 0),
        key=lambda row: (-row["deficit"], row["relation"]),
    )[:25]

    return {
        "relation_count_source": "unique_relation_counts",
        "triple_count_source": "unique_triples",
        "evaluation_note": "Allocation metrics are computed from unique triples.",
        "allocation_relation_count": len(allocated_relations),
        "allocated_relations_observed": observed_allocated,
        "zero_allocated_relations": len(zero_allocated),
        "zero_allocated_relation_ids": zero_allocated,
        "total_expected_eta": total_expected,
        "total_observed_allocated_triples": total_observed,
        "total_deficit": total_deficit,
        "total_surplus": total_surplus,
        "per_relation_expected_observed": per_relation,
        "top_overfilled_relations": top_overfilled,
        "top_underfilled_relations": top_underfilled,
    }

