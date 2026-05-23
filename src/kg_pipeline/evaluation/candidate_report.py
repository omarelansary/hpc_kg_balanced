"""Combined graph candidate evaluation reports."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .allocation_metrics import compare_relation_counts_to_allocation, load_allocation
from .connectivity_metrics import summarize_connectivity
from .graph_io import load_graph_triples, summarize_graph_triples
from .pattern_balance import aggregate_observed_by_pattern_integer, compare_pattern_totals


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evaluate_candidate(
    graph_path: str | Path,
    allocation_path: str | Path,
    candidate_id: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Evaluate a graph candidate against an allocation file without writing outputs."""
    graph = Path(graph_path)
    allocation_file = Path(allocation_path)
    triples = load_graph_triples(graph)
    graph_summary = summarize_graph_triples(triples)
    connectivity_summary = summarize_connectivity(triples)
    graph_metrics = {
        **graph_summary,
        "weak_component_count": connectivity_summary["weak_component_count"],
        "largest_weak_component_size": connectivity_summary["largest_weak_component_size"],
        "largest_weak_component_ratio": connectivity_summary["largest_weak_component_ratio"],
    }

    allocation = load_allocation(allocation_file)
    allocation_metrics = compare_relation_counts_to_allocation(
        graph_metrics["relation_counts"],
        allocation,
    )
    pattern_level = compare_pattern_totals(graph_metrics["relation_counts"], allocation)
    pattern_integer_totals = aggregate_observed_by_pattern_integer(
        graph_metrics["relation_counts"],
        allocation,
    )
    allocation_metrics["pattern_level_expected_observed"] = pattern_level

    return {
        "candidate": {"candidate_id": candidate_id, "label": label},
        "graph_path": str(graph),
        "allocation_path": str(allocation_file),
        "graph_sha256": sha256_file(graph),
        "allocation_sha256": sha256_file(allocation_file),
        "graph_metrics": graph_metrics,
        "connectivity_metrics": connectivity_summary,
        "allocation_extraction": {
            "raw_keys": allocation["raw_keys"],
            "config": allocation["config"],
            "eta_per_group": allocation["eta_per_group"],
            "pattern_groups_relation_counts": allocation["pattern_groups_relation_counts"],
            "positive_allocation_rows": allocation["positive_allocation_rows"],
            "extraction_notes": allocation["extraction_notes"],
        },
        "allocation_metrics": allocation_metrics,
        "pattern_balance_summary": {
            "pattern_level_expected_observed": pattern_level,
            "pattern_observed_integer_totals": pattern_integer_totals,
            "observed_definition": allocation["extraction_notes"]["pattern_observed_definition"],
            "integer_total_note": (
                "Integer pattern totals round each eta-weighted relation-row contribution before summing."
            ),
        },
        "evaluation_notes": [
            "Allocation metrics are computed from unique triples.",
            "Raw graph rows and duplicate_triple_count are reported for duplicate-safety auditing.",
            "The input graph and allocation files are read only and are never modified.",
            "Pattern observed counts are apportioned by per-relation eta weights to avoid double-counting multi-pattern relations.",
        ],
    }
