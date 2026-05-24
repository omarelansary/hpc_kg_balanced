#!/usr/bin/env python3
"""Audit whether verified Phase I patterns can synthesize bridge alternatives.

This is a feasibility audit only. It does not write a graph candidate, query WDQS,
call an LLM, or update the candidate registry.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

sys.dont_write_bytecode = True
sys.modules.setdefault("pyarrow", None)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.allocation_metrics import (  # noqa: E402
    compare_relation_counts_to_allocation,
    load_allocation,
)
from src.kg_pipeline.evaluation.candidate_report import sha256_file  # noqa: E402
from src.kg_pipeline.evaluation.graph_io import Triple, load_graph_triples  # noqa: E402
from src.kg_pipeline.evaluation.pattern_balance import compare_pattern_totals  # noqa: E402
from src.kg_pipeline.phase1.pattern_evidence import (  # noqa: E402
    load_composition_verified_compact,
    load_pair_counts,
)
from src.kg_pipeline.phase1.pattern_groups import (  # noqa: E402
    filter_composition_candidates,
    filter_pair_universe,
    select_inverse_candidates,
    select_symmetric_candidates,
)
from tools.graph_candidate_generation.c4_probe_bridge_aware_replace_add import (  # noqa: E402
    relation_delta,
    repo_relative,
    resolve_path,
)
from tools.graph_candidate_generation.c4_search_local_cut_crossing_candidates import (  # noqa: E402
    candidate_sources,
    iter_jsonl_triples,
    prepare_tested_cuts,
    row_source_metadata,
)

B0_GRAPH = Path("src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv")
ALLOCATION = Path("src/Pruning graph/bidirectional_allocation_results5k.json")
HOP_SUPPORT = Path("data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl")
COMPOSITION = Path(
    "data/processed/hop_support_v3/"
    "min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl"
)
C4_LOCAL_SEARCH = Path(
    "experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/"
    "local_cut_crossing_candidate_search.json"
)
C5_H1_H2_REPORT = Path(
    "experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/reports/probe_only/"
    "c5_h1_h2_probe_report.json"
)
C5_MARGINAL_DOC = Path(
    "experiments/graph_candidates/C5_connectivity_support_hypothesis_matrix/marginal_utility_decision.md"
)
OUTPUT_DIR = Path("experiments/graph_candidates/H3_synthetic_pattern_feasibility/reports")
README_PATH = Path("experiments/graph_candidates/H3_synthetic_pattern_feasibility/README.md")
REPORT_JSON = OUTPUT_DIR / "h3_synthetic_pattern_feasibility_report.json"
REPORT_MD = OUTPUT_DIR / "h3_synthetic_pattern_feasibility_summary.md"
EXAMPLES_TSV = OUTPUT_DIR / "h3_synthetic_pattern_examples.tsv"
TARGET_RELATIONS = {"P31", "P279", "P131"}
COMPOSITION_MIN_EXAMINED = 50
COMPOSITION_MIN_SHORTCUTS = 1
WILSON_Z_95 = 1.959963984540054
MAX_EXAMPLES = 200


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-target-edges", type=int, default=200)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def output_paths() -> dict[str, Path]:
    return {"json": REPORT_JSON, "markdown": REPORT_MD, "examples_tsv": EXAMPLES_TSV, "readme": README_PATH}


def refuse_overwrite(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite H3 reports without --force: {names}")


def required_artifacts() -> list[Path]:
    return [B0_GRAPH, ALLOCATION, HOP_SUPPORT, COMPOSITION, C4_LOCAL_SEARCH, C5_H1_H2_REPORT]


def missing_artifacts() -> list[Path]:
    return [path for path in required_artifacts() if not resolve_path(path).is_file()]


def artifact_descriptor(path: Path) -> dict[str, Any]:
    resolved = resolve_path(path)
    return {
        "path": repo_relative(resolved),
        "exists": resolved.is_file(),
        "sha256": sha256_file(resolved) if resolved.is_file() else None,
    }


def build_verified_pattern_rules(allocation_payload: dict[str, Any]) -> dict[str, Any]:
    config = allocation_payload["config"]
    pair_counts = load_pair_counts(resolve_path(HOP_SUPPORT), only_success=True)
    pair_universe = filter_pair_universe(
        pair_counts,
        base_min_total=int(config["base_min_total"]),
        base_max_total=int(config["base_max_total"]),
    )
    symmetric = select_symmetric_candidates(
        pair_universe,
        min_support=int(config["sym_min_support"]),
        min_confidence=float(config["sym_min_conf"]),
    )
    inverse = select_inverse_candidates(
        pair_universe,
        min_support=int(config["inv_min_support"]),
        min_confidence=float(config["inv_min_conf"]),
        sort_by="bidirectional_conf_min",
    )
    composition_input = load_composition_verified_compact(resolve_path(COMPOSITION), only_success=True)
    composition = filter_composition_candidates(
        composition_input,
        min_support=int(config["comp_min_support"]),
        min_examined=COMPOSITION_MIN_EXAMINED,
        min_confidence=float(config["comp_min_conf"]),
        min_shortcuts=COMPOSITION_MIN_SHORTCUTS,
        use_wilson=False,
        wilson_z=WILSON_Z_95,
        sort_by="conf_composition_sample",
    )

    symmetric_rules: dict[str, dict[str, Any]] = {}
    for row in symmetric.to_dict("records"):
        symmetric_rules[row["r1"]] = {
            "pattern_type": "symmetric",
            "relation": row["r1"],
            "support": int(row["total"]),
            "confidence": float(row["conf_loop"]),
            "threshold_status": "preferred",
        }

    inverse_rules: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen_inverse: set[tuple[str, str]] = set()
    for row in inverse.to_dict("records"):
        support = int(min(int(row["total"]), int(row["reverse_total"])))
        for source, derived in ((row["r1"], row["r2"]), (row["r2"], row["r1"])):
            key = (source, derived)
            if key in seen_inverse:
                continue
            seen_inverse.add(key)
            inverse_rules[source].append(
                {
                    "pattern_type": "inverse",
                    "source_relation": source,
                    "derived_relation": derived,
                    "support": support,
                    "confidence": float(row["bidirectional_conf_min"]),
                    "forward_confidence": float(row["conf_loop"]),
                    "reverse_confidence": float(row["reverse_conf_loop"]),
                    "threshold_status": "preferred",
                }
            )

    composition_rules: list[dict[str, Any]] = []
    for row in composition.to_dict("records"):
        composition_rules.append(
            {
                "pattern_type": "composition",
                "r1": row["r1"],
                "r2": row["r2"],
                "r3": row["r3"],
                "base_support": int(row["base_support"]),
                "chain_pairs_examined": int(row["chain_pairs_examined"]),
                "chain_pairs_with_shortcut": int(row["chain_pairs_with_shortcut"]),
                "confidence": float(row["conf_composition_sample"]),
                "threshold_status": "preferred",
                "composition_class": row.get("composition_class"),
            }
        )

    return {
        "thresholds": {
            "preferred": {
                "symmetric": {"min_support": config["sym_min_support"], "min_confidence": config["sym_min_conf"]},
                "inverse": {"min_support": config["inv_min_support"], "min_confidence": config["inv_min_conf"]},
                "composition": {
                    "min_support": config["comp_min_support"],
                    "min_confidence": config["comp_min_conf"],
                    "min_examined": COMPOSITION_MIN_EXAMINED,
                    "min_shortcuts": COMPOSITION_MIN_SHORTCUTS,
                    "use_wilson": False,
                },
            },
            "fallback": "not_generated; this audit uses canonical preferred verified rules only",
        },
        "symmetric": symmetric_rules,
        "inverse_by_source_relation": dict(inverse_rules),
        "composition": composition_rules,
        "counts": {
            "symmetric_rules": len(symmetric_rules),
            "inverse_oriented_rules": sum(len(v) for v in inverse_rules.values()),
            "composition_rules": len(composition_rules),
        },
    }


def relation_interest(rules: dict[str, Any]) -> set[str]:
    relations = set(rules["symmetric"])
    for source, rows in rules["inverse_by_source_relation"].items():
        relations.add(source)
        relations.update(row["derived_relation"] for row in rows)
    for row in rules["composition"]:
        relations.update([row["r1"], row["r2"], row["r3"]])
    return relations


def add_observed_triple(
    triple: Triple,
    source: dict[str, Any],
    observed: set[Triple],
    metadata: dict[Triple, dict[str, Any]],
    out_by_relation: dict[str, dict[str, set[str]]],
    in_by_relation: dict[str, dict[str, set[str]]],
) -> None:
    if triple not in observed:
        observed.add(triple)
        metadata[triple] = source
        h, r, t = triple
        out_by_relation[r][h].add(t)
        in_by_relation[r][t].add(h)


def load_observed_evidence(
    b0_triples: set[Triple],
    entities: set[str],
    relations: set[str],
) -> dict[str, Any]:
    observed: set[Triple] = set()
    metadata: dict[Triple, dict[str, Any]] = {}
    out_by_relation: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    in_by_relation: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    stats: dict[str, Counter[str]] = defaultdict(Counter)

    for triple in b0_triples:
        h, r, t = triple
        if r in relations:
            add_observed_triple(
                triple,
                {"source_id": "b0_parent_graph", "source_path": repo_relative(resolve_path(B0_GRAPH))},
                observed,
                metadata,
                out_by_relation,
                in_by_relation,
            )
            stats["b0_parent_graph"]["triples_loaded"] += 1

    for source in candidate_sources():
        source_id = source["source_id"]
        for path in source["paths"]:
            if not path.is_file():
                stats[source_id]["missing_files"] += 1
                continue
            stats[source_id]["files_scanned"] += 1
            stats[source_id]["bytes_scanned"] += path.stat().st_size
            for line_number, triple, row in iter_jsonl_triples(path):
                stats[source_id]["rows_scanned"] += 1
                if triple is None:
                    stats[source_id]["rows_without_parseable_triple"] += 1
                    continue
                h, r, t = triple
                if r not in relations:
                    continue
                stats[source_id]["triples_with_relation_of_interest"] += 1
                if h not in entities or t not in entities:
                    stats[source_id]["outside_b0_endpoint_scope"] += 1
                    continue
                add_observed_triple(
                    triple,
                    {
                        "source_id": source_id,
                        "source_path": repo_relative(path),
                        "line_number": line_number,
                        "source_metadata": row_source_metadata(row),
                    },
                    observed,
                    metadata,
                    out_by_relation,
                    in_by_relation,
                )
                stats[source_id]["triples_loaded"] += 1

    return {
        "observed": observed,
        "metadata": metadata,
        "out_by_relation": out_by_relation,
        "in_by_relation": in_by_relation,
        "source_stats": {source_id: dict(sorted(counter.items())) for source_id, counter in sorted(stats.items())},
    }


def side_sets(cut_index: dict[str, set[int]], entities: set[str], cut_count: int) -> dict[int, set[str]]:
    out = {cut_id: set() for cut_id in range(cut_count)}
    for entity, cuts in cut_index.items():
        for cut_id in cuts:
            out[cut_id].add(entity)
    for cut_id, side in out.items():
        if len(side) > len(entities) / 2:
            out[cut_id] = entities - side
    return out


def crossing_cut_ids(h: str, t: str, cut_index: dict[str, set[int]]) -> set[int]:
    return cut_index.get(h, set()) ^ cut_index.get(t, set())


def edge_dict(triple: Triple) -> dict[str, str]:
    return {"h": triple[0], "r": triple[1], "t": triple[2]}


def pattern_deficits(pattern_level: list[dict[str, Any]]) -> dict[str, float]:
    return {
        row["pattern"]: float(row["deficit"])
        for row in pattern_level
    }


def relation_patterns(allocation: dict[str, Any], relation: str) -> list[str]:
    return [str(row["pattern"]) for row in allocation["relation_patterns"].get(relation, []) if row.get("pattern")]


def candidate_classification(allocated: bool, threshold_status: str) -> str:
    if threshold_status == "preferred":
        return "synthetic_allocated_preferred" if allocated else "synthetic_unallocated_preferred"
    if threshold_status == "fallback":
        return "synthetic_allocated_fallback" if allocated else "synthetic_unallocated_fallback"
    return "synthetic_low_confidence"


def add_candidate(
    *,
    candidates: dict[tuple[int, Triple, str], dict[str, Any]],
    rejected: Counter[str],
    b0_triples: set[Triple],
    observed: set[Triple],
    observed_metadata: dict[Triple, dict[str, Any]],
    relation_counts: Counter[str],
    allocation: dict[str, Any],
    relation_expected: dict[str, float],
    pattern_deficit_map: dict[str, float],
    cuts: list[dict[str, Any]],
    cut_id: int,
    candidate: Triple,
    pattern_type: str,
    rule: dict[str, Any],
    source_edges: list[Triple],
    cut_index: dict[str, set[int]],
    extra: dict[str, Any] | None = None,
) -> None:
    if candidate in b0_triples:
        rejected["rejected_duplicate"] += 1
        return
    if cut_id not in crossing_cut_ids(candidate[0], candidate[2], cut_index):
        rejected["rejected_not_cut_crossing"] += 1
        return

    target = cuts[cut_id]["target_edge"]
    allocated = candidate[1] in relation_expected
    delta = relation_delta(relation_counts, relation_expected, target["r"], candidate[1] if allocated else None)
    patterns = relation_patterns(allocation, candidate[1])
    underfilled = any(pattern_deficit_map.get(pattern, 0.0) > 0 for pattern in patterns)
    threshold_status = str(rule.get("threshold_status") or "low_confidence")
    key = (cut_id, candidate, pattern_type)
    row = {
        "cut_id": cut_id,
        "target_edge": target,
        "candidate": edge_dict(candidate),
        "edge_role": "synthetic_pattern_derived",
        "pattern_type": pattern_type,
        "classification": candidate_classification(allocated, threshold_status),
        "threshold_status": threshold_status,
        "allocated_relation": allocated,
        "derived_relation_patterns": patterns,
        "derived_relation_belongs_to_underfilled_pattern": underfilled,
        "surplus_reducing": float(delta["surplus_delta"]) < 0,
        "deficit_would_increase": float(delta["deficit_delta"]) > 0,
        "balance_effect": delta,
        "candidate_already_observed_in_local_evidence": candidate in observed,
        "candidate_observed_metadata": observed_metadata.get(candidate),
        "observed_source_edge": True,
        "source_edges": [edge_dict(edge) for edge in source_edges],
        "source_edge_metadata": [observed_metadata.get(edge) for edge in source_edges],
        "rule": rule,
        "smaller_side_size": cuts[cut_id]["smaller_side_size"],
        "larger_side_size": cuts[cut_id]["larger_side_size"],
    }
    if extra:
        row.update(extra)

    existing = candidates.get(key)
    if existing is None:
        candidates[key] = row
        return
    existing_sources = existing.setdefault("alternative_source_edges", [])
    existing_sources.append([edge_dict(edge) for edge in source_edges])


def generate_symmetric_and_inverse(
    *,
    rules: dict[str, Any],
    observed: set[Triple],
    observed_metadata: dict[Triple, dict[str, Any]],
    b0_triples: set[Triple],
    relation_counts: Counter[str],
    allocation: dict[str, Any],
    relation_expected: dict[str, float],
    pattern_deficit_map: dict[str, float],
    cuts: list[dict[str, Any]],
    cut_index: dict[str, set[int]],
    rejected: Counter[str],
) -> dict[tuple[int, Triple, str], dict[str, Any]]:
    candidates: dict[tuple[int, Triple, str], dict[str, Any]] = {}
    source_hits = Counter()

    for h, r, t in sorted(observed):
        if r in rules["symmetric"]:
            cut_ids = crossing_cut_ids(h, t, cut_index)
            if cut_ids:
                source_hits["symmetric"] += 1
            for cut_id in cut_ids:
                add_candidate(
                    candidates=candidates,
                    rejected=rejected,
                    b0_triples=b0_triples,
                    observed=observed,
                    observed_metadata=observed_metadata,
                    relation_counts=relation_counts,
                    allocation=allocation,
                    relation_expected=relation_expected,
                    pattern_deficit_map=pattern_deficit_map,
                    cuts=cuts,
                    cut_id=cut_id,
                    candidate=(t, r, h),
                    pattern_type="symmetric",
                    rule=rules["symmetric"][r],
                    source_edges=[(h, r, t)],
                    cut_index=cut_index,
                    extra={"source_relation": r, "derived_relation": r},
                )

        for rule in rules["inverse_by_source_relation"].get(r, []):
            cut_ids = crossing_cut_ids(h, t, cut_index)
            if cut_ids:
                source_hits["inverse"] += 1
            derived = rule["derived_relation"]
            for cut_id in cut_ids:
                add_candidate(
                    candidates=candidates,
                    rejected=rejected,
                    b0_triples=b0_triples,
                    observed=observed,
                    observed_metadata=observed_metadata,
                    relation_counts=relation_counts,
                    allocation=allocation,
                    relation_expected=relation_expected,
                    pattern_deficit_map=pattern_deficit_map,
                    cuts=cuts,
                    cut_id=cut_id,
                    candidate=(t, derived, h),
                    pattern_type="inverse",
                    rule=rule,
                    source_edges=[(h, r, t)],
                    cut_index=cut_index,
                    extra={"source_relation": r, "derived_relation": derived},
                )

    if source_hits["symmetric"] == 0:
        rejected["rejected_missing_observed_source_edges_symmetric"] += len(rules["symmetric"])
    if source_hits["inverse"] == 0:
        rejected["rejected_missing_observed_source_edges_inverse"] += sum(
            len(rows) for rows in rules["inverse_by_source_relation"].values()
        )
    return candidates


def generate_composition(
    *,
    rules: dict[str, Any],
    observed: set[Triple],
    observed_metadata: dict[Triple, dict[str, Any]],
    out_by_relation: dict[str, dict[str, set[str]]],
    in_by_relation: dict[str, dict[str, set[str]]],
    b0_triples: set[Triple],
    relation_counts: Counter[str],
    allocation: dict[str, Any],
    relation_expected: dict[str, float],
    pattern_deficit_map: dict[str, float],
    cuts: list[dict[str, Any]],
    cut_index: dict[str, set[int]],
    cut_sides: dict[int, set[str]],
    entities: set[str],
    rejected: Counter[str],
) -> dict[tuple[int, Triple, str], dict[str, Any]]:
    candidates: dict[tuple[int, Triple, str], dict[str, Any]] = {}
    rule_hits: Counter[tuple[str, str, str]] = Counter()

    for cut in cuts:
        cut_id = int(cut["cut_id"])
        side = cut_sides[cut_id]
        if not side:
            continue
        for rule in rules["composition"]:
            r1, r2, r3 = rule["r1"], rule["r2"], rule["r3"]
            # Candidate direction from smaller side to larger side.
            for a in side:
                for x in out_by_relation.get(r1, {}).get(a, ()):
                    for b in out_by_relation.get(r2, {}).get(x, ()):
                        if b not in entities or b in side:
                            continue
                        source_edges = [(a, r1, x), (x, r2, b)]
                        rule_hits[(r1, r2, r3)] += 1
                        add_candidate(
                            candidates=candidates,
                            rejected=rejected,
                            b0_triples=b0_triples,
                            observed=observed,
                            observed_metadata=observed_metadata,
                            relation_counts=relation_counts,
                            allocation=allocation,
                            relation_expected=relation_expected,
                            pattern_deficit_map=pattern_deficit_map,
                            cuts=cuts,
                            cut_id=cut_id,
                            candidate=(a, r3, b),
                            pattern_type="composition",
                            rule=rule,
                            source_edges=source_edges,
                            cut_index=cut_index,
                            extra={
                                "source_relations": [r1, r2],
                                "derived_relation": r3,
                                "intermediate_node": x,
                            },
                        )
            # Candidate direction from larger side to smaller side.
            for b in side:
                for x in in_by_relation.get(r2, {}).get(b, ()):
                    for a in in_by_relation.get(r1, {}).get(x, ()):
                        if a not in entities or a in side:
                            continue
                        source_edges = [(a, r1, x), (x, r2, b)]
                        rule_hits[(r1, r2, r3)] += 1
                        add_candidate(
                            candidates=candidates,
                            rejected=rejected,
                            b0_triples=b0_triples,
                            observed=observed,
                            observed_metadata=observed_metadata,
                            relation_counts=relation_counts,
                            allocation=allocation,
                            relation_expected=relation_expected,
                            pattern_deficit_map=pattern_deficit_map,
                            cuts=cuts,
                            cut_id=cut_id,
                            candidate=(a, r3, b),
                            pattern_type="composition",
                            rule=rule,
                            source_edges=source_edges,
                            cut_index=cut_index,
                            extra={
                                "source_relations": [r1, r2],
                                "derived_relation": r3,
                                "intermediate_node": x,
                            },
                        )

    missing = len(rules["composition"]) - len(rule_hits)
    if missing > 0:
        rejected["rejected_missing_observed_source_edges_composition_rules"] += missing
    return candidates


def aggregate_candidates(candidates: Iterable[dict[str, Any]], rejected: Counter[str]) -> dict[str, Any]:
    rows = list(candidates)
    pattern_counts = Counter(row["pattern_type"] for row in rows)
    classification_counts = Counter(row["classification"] for row in rows)
    threshold_counts = Counter(row["threshold_status"] for row in rows)
    allocated = sum(1 for row in rows if row["allocated_relation"])
    unallocated = len(rows) - allocated
    underfilled = sum(1 for row in rows if row["derived_relation_belongs_to_underfilled_pattern"])
    surplus_reducing = sum(1 for row in rows if row["surplus_reducing"])
    deficit_neutral = sum(1 for row in rows if not row["deficit_would_increase"])
    preferred = threshold_counts["preferred"]
    fallback = threshold_counts["fallback"]
    low = threshold_counts["low_confidence"]
    observed_local = sum(1 for row in rows if row["candidate_already_observed_in_local_evidence"])

    if not rows:
        conclusion = "h3_not_promising_no_candidates"
    elif classification_counts["synthetic_allocated_preferred"] > 0:
        conclusion = "h3_promising_allocated_synthetic_candidates"
    elif classification_counts["synthetic_unallocated_preferred"] > 0:
        conclusion = "h3_promising_only_unallocated_synthetic_candidates"
    elif low > 0 and preferred == 0 and fallback == 0:
        conclusion = "h3_low_confidence_only"
    else:
        conclusion = "h3_not_promising_no_candidates"

    return {
        "total_candidates": len(rows),
        "synthetic_candidates_by_pattern_type": dict(sorted(pattern_counts.items())),
        "classification_counts": dict(sorted(classification_counts.items())),
        "allocated_synthetic_candidates": allocated,
        "unallocated_synthetic_candidates": unallocated,
        "underfilled_pattern_synthetic_candidates": underfilled,
        "surplus_reducing_synthetic_candidates": surplus_reducing,
        "deficit_neutral_synthetic_candidates": deficit_neutral,
        "candidate_already_observed_in_local_evidence": observed_local,
        "threshold_counts": {
            "preferred": preferred,
            "fallback": fallback,
            "below_fallback_or_low_confidence": low,
        },
        "rejection_counts": dict(sorted(rejected.items())),
        "feasibility_conclusion": conclusion,
    }


def example_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        0 if row["allocated_relation"] else 1,
        0 if row["surplus_reducing"] else 1,
        1 if row["deficit_would_increase"] else 0,
        row["pattern_type"],
        row["candidate"]["r"],
        row["cut_id"],
        row["candidate"]["h"],
        row["candidate"]["t"],
    )


def write_examples(path: Path, examples: list[dict[str, Any]]) -> None:
    fields = [
        "cut_id",
        "pattern_type",
        "classification",
        "threshold_status",
        "candidate_h",
        "candidate_r",
        "candidate_t",
        "allocated_relation",
        "surplus_reducing",
        "deficit_would_increase",
        "underfilled_pattern",
        "confidence",
        "support",
        "target_h",
        "target_r",
        "target_t",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in examples:
            candidate = row["candidate"]
            target = row["target_edge"]
            rule = row["rule"]
            writer.writerow(
                {
                    "cut_id": row["cut_id"],
                    "pattern_type": row["pattern_type"],
                    "classification": row["classification"],
                    "threshold_status": row["threshold_status"],
                    "candidate_h": candidate["h"],
                    "candidate_r": candidate["r"],
                    "candidate_t": candidate["t"],
                    "allocated_relation": row["allocated_relation"],
                    "surplus_reducing": row["surplus_reducing"],
                    "deficit_would_increase": row["deficit_would_increase"],
                    "underfilled_pattern": row["derived_relation_belongs_to_underfilled_pattern"],
                    "confidence": rule.get("confidence"),
                    "support": rule.get("support", rule.get("base_support")),
                    "target_h": target["h"],
                    "target_r": target["r"],
                    "target_t": target["t"],
                }
            )


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    missing = missing_artifacts()
    if missing:
        finished = time.time()
        return {
            "schema_version": "h3-synthetic-pattern-feasibility-audit-v1",
            "audit_id": "H3_synthetic_pattern_feasibility",
            "status": "missing_artifact",
            "feasibility_conclusion": "h3_blocked_missing_artifacts",
            "missing_artifacts": [repo_relative(resolve_path(path)) for path in missing],
            "runtime": {
                "started_on": datetime.fromtimestamp(started, timezone.utc).isoformat(),
                "finished_on": datetime.fromtimestamp(finished, timezone.utc).isoformat(),
                "elapsed_seconds": round(finished - started, 6),
            },
        }

    allocation_payload = load_json(resolve_path(ALLOCATION))
    allocation = load_allocation(resolve_path(ALLOCATION))
    relation_expected = allocation["relation_expected"]
    b0_triples = set(load_graph_triples(resolve_path(B0_GRAPH)))
    entities = {node for h, _r, t in b0_triples for node in (h, t)}
    relation_counts = Counter(r for _h, r, _t in b0_triples)
    allocation_metrics = compare_relation_counts_to_allocation(relation_counts, allocation)
    baseline_pattern_level = compare_pattern_totals(relation_counts, allocation)
    pattern_deficit_map = pattern_deficits(baseline_pattern_level)

    rules = build_verified_pattern_rules(allocation_payload)
    observed_evidence = load_observed_evidence(b0_triples, entities, relation_interest(rules))

    cuts, cut_index = prepare_tested_cuts(
        b0_triples,
        entities,
        relation_counts,
        relation_expected,
        TARGET_RELATIONS,
        args.max_target_edges,
    )
    cut_sides = side_sets(cut_index, entities, len(cuts))

    rejected: Counter[str] = Counter()
    generated = generate_symmetric_and_inverse(
        rules=rules,
        observed=observed_evidence["observed"],
        observed_metadata=observed_evidence["metadata"],
        b0_triples=b0_triples,
        relation_counts=relation_counts,
        allocation=allocation,
        relation_expected=relation_expected,
        pattern_deficit_map=pattern_deficit_map,
        cuts=cuts,
        cut_index=cut_index,
        rejected=rejected,
    )
    generated.update(
        generate_composition(
            rules=rules,
            observed=observed_evidence["observed"],
            observed_metadata=observed_evidence["metadata"],
            out_by_relation=observed_evidence["out_by_relation"],
            in_by_relation=observed_evidence["in_by_relation"],
            b0_triples=b0_triples,
            relation_counts=relation_counts,
            allocation=allocation,
            relation_expected=relation_expected,
            pattern_deficit_map=pattern_deficit_map,
            cuts=cuts,
            cut_index=cut_index,
            cut_sides=cut_sides,
            entities=entities,
            rejected=rejected,
        )
    )
    candidates = sorted(generated.values(), key=example_sort_key)
    aggregate = aggregate_candidates(candidates, rejected)
    examples = candidates[:MAX_EXAMPLES]
    c4_report = load_json(resolve_path(C4_LOCAL_SEARCH))
    c5_report = load_json(resolve_path(C5_H1_H2_REPORT))
    finished = time.time()

    return {
        "schema_version": "h3-synthetic-pattern-feasibility-audit-v1",
        "audit_id": "H3_synthetic_pattern_feasibility",
        "status": "read_only_feasibility_audit",
        "inputs": {
            "b0_parent_graph": artifact_descriptor(B0_GRAPH),
            "allocation": artifact_descriptor(ALLOCATION),
            "hop_support": artifact_descriptor(HOP_SUPPORT),
            "composition_verified_compact": artifact_descriptor(COMPOSITION),
            "c4_local_cut_crossing_search": artifact_descriptor(C4_LOCAL_SEARCH),
            "c5_h1_h2_probe": artifact_descriptor(C5_H1_H2_REPORT),
            "c5_marginal_decision": {
                "path": repo_relative(resolve_path(C5_MARGINAL_DOC)),
                "exists": resolve_path(C5_MARGINAL_DOC).is_file(),
            },
        },
        "limits": {"max_target_edges": args.max_target_edges, "max_examples": MAX_EXAMPLES},
        "bridge_cut_context": {
            "target_relations": sorted(TARGET_RELATIONS),
            "tested_cuts": len(cuts),
            "b0_unique_triples": len(b0_triples),
            "b0_entities": len(entities),
            "baseline_total_surplus": allocation_metrics["total_surplus"],
            "baseline_total_deficit": allocation_metrics["total_deficit"],
            "baseline_pattern_deficits": pattern_deficit_map,
            "baseline_pattern_level_expected_observed": baseline_pattern_level,
        },
        "verified_pattern_rules": {
            "counts": rules["counts"],
            "thresholds": rules["thresholds"],
        },
        "observed_evidence_scan": {
            "relations_of_interest": len(relation_interest(rules)),
            "observed_triples_loaded": len(observed_evidence["observed"]),
            "source_stats": observed_evidence["source_stats"],
        },
        "aggregate_counts": aggregate,
        "comparison_context": {
            "c4_local_cut_crossing_primary_result": c4_report.get("interpretation", {}).get("primary_result"),
            "c5_h1_h2_h2_summary": c5_report.get("h2_summary"),
            "c5_h2_marginal_decision": "diagnostic_evidence_only",
        },
        "top_examples": examples,
        "notes": [
            "Every proposed triple is labelled synthetic_pattern_derived.",
            "Synthetic pattern-derived triples are not observed Wikidata triples unless separately verified.",
            "This audit uses frozen local evidence only.",
            "No graph candidate was generated.",
            "No WDQS query was made.",
            "No LLM call was made.",
            "candidate_registry.v1.json was not updated.",
        ],
        "runtime": {
            "started_on": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "finished_on": datetime.fromtimestamp(finished, timezone.utc).isoformat(),
            "elapsed_seconds": round(finished - started, 6),
        },
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    agg = report.get("aggregate_counts", {})
    context = report.get("bridge_cut_context", {})
    rules = report.get("verified_pattern_rules", {}).get("counts", {})
    lines = [
        "# H3 Synthetic Pattern Feasibility Audit",
        "",
        "Status: read-only feasibility audit. No graph candidate was generated.",
        "",
        "## Scope",
        "",
        "H3 tests whether verified Phase I structural patterns can synthesize cut-crossing bridge alternatives. "
        "Synthetic pattern-derived triples are not observed Wikidata triples and must remain explicitly labelled.",
        "",
        "## Inputs",
        "",
        f"- B0 graph: `{report['inputs']['b0_parent_graph']['path']}`",
        f"- Allocation: `{report['inputs']['allocation']['path']}`",
        f"- Hop support: `{report['inputs']['hop_support']['path']}`",
        f"- Composition verification: `{report['inputs']['composition_verified_compact']['path']}`",
        "",
        "## Tested Cuts",
        "",
        f"- Target relations: `{', '.join(context.get('target_relations', []))}`",
        f"- Tested bridge cuts: `{context.get('tested_cuts')}`",
        f"- Baseline surplus: `{context.get('baseline_total_surplus')}`",
        f"- Baseline deficit: `{context.get('baseline_total_deficit')}`",
        "",
        "## Verified Pattern Rules",
        "",
        f"- Symmetric rules: `{rules.get('symmetric_rules', 0)}`",
        f"- Inverse oriented rules: `{rules.get('inverse_oriented_rules', 0)}`",
        f"- Composition rules: `{rules.get('composition_rules', 0)}`",
        "",
        "## Candidate Counts",
        "",
        f"- Total synthetic candidates: `{agg.get('total_candidates', 0)}`",
        f"- By pattern type: `{json.dumps(agg.get('synthetic_candidates_by_pattern_type', {}), sort_keys=True)}`",
        f"- Allocated synthetic candidates: `{agg.get('allocated_synthetic_candidates', 0)}`",
        f"- Unallocated synthetic candidates: `{agg.get('unallocated_synthetic_candidates', 0)}`",
        f"- Underfilled-pattern candidates: `{agg.get('underfilled_pattern_synthetic_candidates', 0)}`",
        f"- Surplus-reducing candidates: `{agg.get('surplus_reducing_synthetic_candidates', 0)}`",
        f"- Deficit-neutral candidates: `{agg.get('deficit_neutral_synthetic_candidates', 0)}`",
        f"- Preferred-threshold candidates: `{agg.get('threshold_counts', {}).get('preferred', 0)}`",
        f"- Fallback-threshold candidates: `{agg.get('threshold_counts', {}).get('fallback', 0)}`",
        f"- Below fallback / low-confidence candidates: `{agg.get('threshold_counts', {}).get('below_fallback_or_low_confidence', 0)}`",
        f"- Candidate already observed in local evidence: `{agg.get('candidate_already_observed_in_local_evidence', 0)}`",
        f"- Feasibility conclusion: `{agg.get('feasibility_conclusion')}`",
        "",
        "## Risk Classification",
        "",
        f"`{json.dumps(agg.get('classification_counts', {}), sort_keys=True)}`",
        "",
        "## Interpretation",
        "",
    ]
    conclusion = agg.get("feasibility_conclusion")
    if conclusion == "h3_promising_allocated_synthetic_candidates":
        lines.append(
            "H3 has allocated, preferred-threshold synthetic candidates under frozen evidence. This is worth continuing "
            "as a separate synthetic feasibility branch, but not as an observed-fact graph."
        )
    elif conclusion == "h3_promising_only_unallocated_synthetic_candidates":
        lines.append(
            "H3 finds preferred-threshold synthetic candidates, but only for unallocated relations. This is weaker than "
            "an allocated synthetic branch and remains outside canonical allocation accounting."
        )
    elif conclusion == "h3_low_confidence_only":
        lines.append("H3 finds only low-confidence or fallback candidates and is not ready for graph generation.")
    else:
        lines.append("H3 did not find promising synthetic candidates under the bounded frozen-evidence audit.")

    lines.extend(
        [
            "",
            "## Safe Claims",
            "",
            "- The audit can state whether pattern-derived synthetic candidates were found under frozen evidence.",
            "- Synthetic candidates are explicitly marked `synthetic_pattern_derived`.",
            "- No WDQS query, LLM call, or graph generation was performed.",
            "",
            "## Unsafe Claims",
            "",
            "- Do not claim synthetic triples are factual Wikidata facts.",
            "- Do not claim an H3 graph is valid before graph generation and evaluation.",
            "- Do not claim LLM verification.",
            "- Do not update the candidate registry from this feasibility audit alone.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_readme(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# H3 Synthetic Pattern Feasibility",
                "",
                "This experiment directory stores a read-only feasibility audit for H3 synthetic-pattern-derived support.",
                "",
                "No graph candidate is generated here. Synthetic pattern-derived triples are not observed Wikidata facts "
                "unless separately verified and must remain marked as `synthetic_pattern_derived`.",
                "",
                "Reports:",
                "",
                "- `reports/h3_synthetic_pattern_feasibility_report.json`",
                "- `reports/h3_synthetic_pattern_feasibility_summary.md`",
                "- `reports/h3_synthetic_pattern_examples.tsv`",
                "",
                "Registry updates are not allowed from this audit alone.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    paths = output_paths()
    if args.dry_run:
        print("dry_run=true")
        print(f"max_target_edges={args.max_target_edges}")
        for name, path in paths.items():
            print(f"{name}={path}")
        missing = missing_artifacts()
        print("missing_artifacts=" + json.dumps([repo_relative(resolve_path(path)) for path in missing]))
        print("outputs_written=false")
        return 0

    refuse_overwrite(paths, args.force)
    report = run_audit(args)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    write_readme(README_PATH)
    REPORT_JSON.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(REPORT_MD, report)
    write_examples(EXAMPLES_TSV, report.get("top_examples", []))
    aggregate = report.get("aggregate_counts", {})
    print(f"report_json={REPORT_JSON}")
    print(f"summary_md={REPORT_MD}")
    print(f"examples_tsv={EXAMPLES_TSV}")
    print(f"tested_cuts={report.get('bridge_cut_context', {}).get('tested_cuts', 0)}")
    print(f"total_candidates={aggregate.get('total_candidates', 0)}")
    print(f"by_pattern={json.dumps(aggregate.get('synthetic_candidates_by_pattern_type', {}), sort_keys=True)}")
    print(f"allocated={aggregate.get('allocated_synthetic_candidates', 0)}")
    print(f"unallocated={aggregate.get('unallocated_synthetic_candidates', 0)}")
    print(f"preferred={aggregate.get('threshold_counts', {}).get('preferred', 0)}")
    print(f"fallback={aggregate.get('threshold_counts', {}).get('fallback', 0)}")
    print(f"feasibility_conclusion={aggregate.get('feasibility_conclusion')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
