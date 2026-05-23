"""Pattern-level balance metrics derived from allocation payloads."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any


def pattern_group_membership(allocation: dict[str, Any]) -> dict[str, list[str]]:
    """Return pattern group relation membership from a loaded allocation."""
    groups = allocation.get("pattern_groups") or {}
    return {
        str(pattern): [str(relation) for relation in relations]
        for pattern, relations in sorted(groups.items())
    }


def aggregate_observed_by_pattern(
    relation_counts: dict[str, int] | Counter[str],
    allocation: dict[str, Any],
) -> dict[str, float]:
    """Apportion observed relation counts across positive pattern rows.

    This preserves the existing graph candidate evaluator behavior: if one
    relation contributes positive eta to multiple pattern rows, the observed
    relation count is split by that relation's per-row eta weights.
    """
    observed_counts = Counter({str(relation): int(count) for relation, count in relation_counts.items()})
    relation_patterns = allocation["relation_patterns"]

    pattern_observed: dict[str, float] = defaultdict(float)
    for relation, observed in observed_counts.items():
        rows = relation_patterns.get(relation, [])
        row_eta_total = sum(row["eta"] for row in rows)
        if not rows or row_eta_total <= 0:
            continue
        for row in rows:
            pattern = row["pattern"]
            if pattern:
                pattern_observed[str(pattern)] += observed * (float(row["eta"]) / row_eta_total)
    return dict(sorted(pattern_observed.items()))


def compare_pattern_totals(
    relation_counts: dict[str, int] | Counter[str],
    allocation: dict[str, Any],
) -> list[dict[str, Any]]:
    pattern_observed = aggregate_observed_by_pattern(relation_counts, allocation)
    pattern_expected = allocation["pattern_expected"]

    pattern_level: list[dict[str, Any]] = []
    for pattern in sorted(set(pattern_expected) | set(pattern_observed)):
        expected = float(pattern_expected.get(pattern, 0.0))
        observed = float(pattern_observed.get(pattern, 0.0))
        pattern_level.append(
            {
                "pattern": pattern,
                "expected_eta": expected,
                "observed_count_apportioned": observed,
                "deficit": max(expected - observed, 0.0),
                "surplus": max(observed - expected, 0.0),
            }
        )
    return pattern_level


def aggregate_observed_by_pattern_integer(
    relation_counts: dict[str, int] | Counter[str],
    allocation: dict[str, Any],
) -> dict[str, int]:
    """Return integer pattern totals used for compact candidate comparisons.

    This uses the same eta-weighted apportioning as
    :func:`aggregate_observed_by_pattern`, but rounds each relation-row
    contribution before summing. It is useful for stable, thesis-facing integer
    pattern totals while the evaluator-compatible floating totals remain
    available in ``pattern_level_expected_observed``.
    """
    observed_counts = Counter({str(relation): int(count) for relation, count in relation_counts.items()})
    relation_patterns = allocation["relation_patterns"]

    pattern_observed: dict[str, int] = defaultdict(int)
    for relation, observed in observed_counts.items():
        rows = relation_patterns.get(relation, [])
        row_eta_total = sum(row["eta"] for row in rows)
        if not rows or row_eta_total <= 0:
            continue
        for row in rows:
            pattern = row["pattern"]
            if pattern:
                contribution = observed * (float(row["eta"]) / row_eta_total)
                pattern_observed[str(pattern)] += round(contribution)
    return dict(sorted(pattern_observed.items()))


def pattern_totals_by_name(pattern_level: list[dict[str, Any]]) -> dict[str, float]:
    return {
        str(row["pattern"]): float(row["observed_count_apportioned"])
        for row in pattern_level
    }
