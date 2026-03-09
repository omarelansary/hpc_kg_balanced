#!/usr/bin/env python3
"""
Audit relation counts in a constructed KG against an allocation file.

Inputs
------
1) triples JSONL or JSON (list/object), e.g.:
    {"h": "Q1001408", "r": "P31", "t": "Q1065118", "source": "original"}

2) allocation JSON or JSONL, containing per-relation cards like:
   {
     "pattern": "inverse",
     "relation": "P1582",
     "eta_integer": 61,
     ...
   }

Outputs
-------
- relation_audit_report.json
- relation_audit_summary.csv

Main checks
-----------
- actual relation counts in graph
- expected counts from allocation (eta_integer)
- inherited pattern from allocation
- anomalies:
    * present in graph but missing from allocation
    * present in graph but eta_integer missing
    * present in graph but eta_integer == 0
    * expected > 0 but actual == 0
    * actual != expected
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def load_json_or_jsonl(path: Path) -> List[dict]:
    """
    Load records from either:
    - JSONL: one JSON object per line
    - JSON: list of objects, dict containing a list, or single object
    """
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    # Try JSON first
    try:
        obj = json.loads(text)
        return normalize_json_records(obj)
    except json.JSONDecodeError:
        pass

    # Fall back to JSONL
    records: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSONL in {path} at line {line_no}: {e}"
                ) from e
            if not isinstance(obj, dict):
                raise ValueError(
                    f"Expected JSON object at line {line_no} in {path}, got {type(obj).__name__}"
                )
            records.append(obj)
    return records


def normalize_json_records(obj: Any) -> List[dict]:
    """
    Normalize common JSON allocation layouts into a list of dict records.
    """
    if isinstance(obj, list):
        for i, x in enumerate(obj):
            if not isinstance(x, dict):
                raise ValueError(f"Expected list of objects, item {i} is {type(x).__name__}")
        return obj

    if isinstance(obj, dict):
        # Case 1: single card object
        if "relation" in obj:
            return [obj]

        # Case 2: dict with obvious list field
        candidate_keys = [
            "records",
            "items",
            "results",
            "allocations",
            "relations",
            "cards",
            "data",
        ]
        for key in candidate_keys:
            value = obj.get(key)
            if isinstance(value, list) and all(isinstance(x, dict) for x in value):
                return value

        # Case 3: dict of relation -> card
        if all(isinstance(v, dict) for v in obj.values()):
            return list(obj.values())

    raise ValueError(
        "Could not normalize JSON structure into a list of relation records."
    )


def count_relations_in_triples(triples_path: Path) -> Counter:
    counts: Counter = Counter()
    records = load_json_or_jsonl(triples_path)
    for idx, obj in enumerate(records, start=1):
        if not isinstance(obj, dict):
            raise ValueError(
                f"Expected JSON object in triples file at item {idx}, got {type(obj).__name__}"
            )

        relation = obj.get("r")
        if relation is None:
            raise ValueError(
                f"Missing 'r' field in triples file at item {idx}: {obj}"
            )

        counts[str(relation)] += 1

    return counts


def to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return int(round(value))
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            try:
                return int(round(float(value)))
            except ValueError:
                return None
    return None


def to_float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return float(value)
        except ValueError:
            return None
    return None


def build_allocation_index(records: Iterable[dict], *, eta_aggregation: str = "sum") -> Dict[str, dict]:
    if eta_aggregation not in {"sum", "max"}:
        raise ValueError(f"Unsupported eta_aggregation={eta_aggregation!r}. Use 'sum' or 'max'.")

    index: Dict[str, dict] = {}

    for rec in records:
        relation = rec.get("relation")
        if relation is None:
            continue
        relation = str(relation)
        pattern = str(rec.get("pattern") or "UNKNOWN")
        eta_i = to_int_or_none(rec.get("eta_integer"))

        agg = index.get(relation)
        if agg is None:
            agg = {
                "relation": relation,
                "pattern": pattern,
                "patterns": [],
                "eta_integer": 0,
                "eta_integer_by_pattern": {},
                "eta_integer_values": [],
                "eta_expected": 0.0,
                "eta_total": 0.0,
                "forward_score": None,
                "backward_score": None,
                "p_forward": None,
                "p_backward": None,
                "p_avg": None,
                "relation_dom_rng_class": None,
                "relation_dom_rng_classes": [],
                "allocation_row_count": 0,
                "allocation_entries": [],
            }
            index[relation] = agg

        agg["allocation_row_count"] += 1
        if pattern not in agg["patterns"]:
            agg["patterns"].append(pattern)

        eta_for_value = int(eta_i) if eta_i is not None else 0
        agg["eta_integer_values"].append(eta_for_value)

        if eta_aggregation == "sum":
            agg["eta_integer"] += eta_for_value
            agg["eta_integer_by_pattern"][pattern] = agg["eta_integer_by_pattern"].get(pattern, 0) + eta_for_value
        else:
            agg["eta_integer"] = max(int(agg["eta_integer"]), eta_for_value)
            prev_by_pattern = agg["eta_integer_by_pattern"].get(pattern)
            if prev_by_pattern is None:
                agg["eta_integer_by_pattern"][pattern] = eta_for_value
            else:
                agg["eta_integer_by_pattern"][pattern] = max(int(prev_by_pattern), eta_for_value)

        eta_expected = to_float_or_none(rec.get("eta_expected"))
        if eta_expected is not None:
            agg["eta_expected"] += eta_expected

        eta_total = to_float_or_none(rec.get("eta_total"))
        if eta_total is not None:
            agg["eta_total"] += eta_total

        dom_rng = rec.get("relation_dom_rng_class")
        if dom_rng is not None:
            dom_rng = str(dom_rng)
            if dom_rng not in agg["relation_dom_rng_classes"]:
                agg["relation_dom_rng_classes"].append(dom_rng)

        for score_key in ("forward_score", "backward_score", "p_forward", "p_backward", "p_avg"):
            val = to_float_or_none(rec.get(score_key))
            if val is None:
                continue
            prev = agg.get(score_key)
            if prev is None or float(val) > float(prev):
                agg[score_key] = val

        agg["allocation_entries"].append(
            {
                "pattern": pattern,
                "eta_integer": eta_for_value,
                "eta_expected": eta_expected,
                "eta_total": eta_total,
                "forward_score": to_float_or_none(rec.get("forward_score")),
                "backward_score": to_float_or_none(rec.get("backward_score")),
                "p_forward": to_float_or_none(rec.get("p_forward")),
                "p_backward": to_float_or_none(rec.get("p_backward")),
                "p_avg": to_float_or_none(rec.get("p_avg")),
                "relation_dom_rng_class": dom_rng,
            }
        )

    for relation, agg in index.items():
        patterns = sorted(agg["patterns"])
        agg["patterns"] = patterns
        agg["pattern"] = "|".join(patterns)
        agg["eta_integer_by_pattern"] = {
            k: agg["eta_integer_by_pattern"][k] for k in sorted(agg["eta_integer_by_pattern"]) 
        }
        classes = sorted(agg["relation_dom_rng_classes"])
        agg["relation_dom_rng_classes"] = classes
        agg["relation_dom_rng_class"] = "|".join(classes) if classes else None
        agg["allocation_entries"] = sorted(
            agg["allocation_entries"],
            key=lambda x: (str(x.get("pattern") or ""), int(x.get("eta_integer") or 0)),
        )

    return index


def classify_row(
    relation: str,
    actual_count: int,
    alloc: Optional[dict],
) -> dict:
    row: Dict[str, Any] = {
        "relation": relation,
        "actual_count": actual_count,
        "in_allocation": alloc is not None,
        "pattern": None,
        "eta_integer": None,
        "eta_expected": None,
        "eta_total": None,
        "forward_score": None,
        "backward_score": None,
        "p_forward": None,
        "p_backward": None,
        "p_avg": None,
        "relation_dom_rng_class": None,
        "patterns": None,
        "allocation_row_count": 0,
        "eta_integer_by_pattern": None,
        "eta_integer_values": None,
        "allocation_entries": None,
        "difference_actual_minus_expected": None,
        "actual_over_expected_ratio": None,
        "category": None,
        "flags": [],
        "status": "ok",
    }

    if alloc is None:
        row["category"] = "graph_only_missing_allocation"
        row["flags"].append("present_in_graph_but_missing_from_allocation")
        row["status"] = "error"
        return row

    row["pattern"] = alloc.get("pattern")
    row["eta_integer"] = to_int_or_none(alloc.get("eta_integer"))
    row["eta_expected"] = alloc.get("eta_expected")
    row["eta_total"] = alloc.get("eta_total")
    row["forward_score"] = alloc.get("forward_score")
    row["backward_score"] = alloc.get("backward_score")
    row["p_forward"] = alloc.get("p_forward")
    row["p_backward"] = alloc.get("p_backward")
    row["p_avg"] = alloc.get("p_avg")
    row["relation_dom_rng_class"] = alloc.get("relation_dom_rng_class")
    row["patterns"] = alloc.get("patterns")
    row["allocation_row_count"] = int(alloc.get("allocation_row_count", 0))
    row["eta_integer_by_pattern"] = alloc.get("eta_integer_by_pattern")
    row["eta_integer_values"] = alloc.get("eta_integer_values")
    row["allocation_entries"] = alloc.get("allocation_entries")

    eta_integer = row["eta_integer"]

    if eta_integer is None:
        row["category"] = "overlap_eta_missing"
        row["flags"].append("eta_integer_missing")
        row["status"] = "error"
        return row

    if eta_integer == 0:
        if actual_count > 0:
            row["category"] = "overlap_eta_zero_actual_present"
            row["flags"].append("actual_present_but_eta_integer_zero")
            row["status"] = "error"
        else:
            row["category"] = "overlap_eta_zero_actual_absent"
            row["flags"].append("eta_integer_zero")
            row["status"] = "warning"
        row["difference_actual_minus_expected"] = actual_count - eta_integer
        row["actual_over_expected_ratio"] = None
        return row

    # eta_integer > 0
    row["difference_actual_minus_expected"] = actual_count - eta_integer
    row["actual_over_expected_ratio"] = actual_count / eta_integer

    if actual_count == 0:
        row["category"] = "allocation_only_absent_in_graph"
        row["flags"].append("expected_positive_but_absent_in_graph")
        row["status"] = "error"
    elif actual_count != eta_integer:
        row["category"] = "overlap_mismatch"
        row["flags"].append("actual_expected_mismatch")
        row["status"] = "warning"
    else:
        row["category"] = "overlap_exact_match"

    return row


def build_full_report(
    relation_counts: Counter,
    allocation_index: Dict[str, dict],
    include_expected_but_absent: bool = True,
) -> List[dict]:
    relations = set(relation_counts.keys())

    if include_expected_but_absent:
        relations |= set(allocation_index.keys())

    rows: List[dict] = []
    for relation in sorted(relations):
        actual_count = relation_counts.get(relation, 0)
        alloc = allocation_index.get(relation)
        rows.append(classify_row(relation, actual_count, alloc))

    return rows


def build_summary(rows: List[dict], triples_total: int) -> dict:
    status_counts = Counter(row["status"] for row in rows)
    category_counts = Counter(str(row.get("category") or "unknown") for row in rows)

    flag_counts = Counter()
    for row in rows:
        for flag in row["flags"]:
            flag_counts[flag] += 1

    expected_positive = [
        row for row in rows
        if isinstance(row.get("eta_integer"), int) and row["eta_integer"] > 0
    ]

    matched_exactly = [
        row for row in expected_positive
        if row["actual_count"] == row["eta_integer"]
    ]

    summary = {
        "triples_total": triples_total,
        "unique_relations_in_graph": sum(1 for row in rows if row["actual_count"] > 0),
        "unique_relations_in_allocation": sum(1 for row in rows if row["in_allocation"]),
        "rows_total": len(rows),
        "status_counts": dict(status_counts),
        "category_counts": dict(category_counts),
        "flag_counts": dict(flag_counts),
        "expected_positive_relations": len(expected_positive),
        "exact_matches_among_expected_positive": len(matched_exactly),
        "exact_match_rate_among_expected_positive": (
            len(matched_exactly) / len(expected_positive) if expected_positive else None
        ),
    }
    return summary


def _sorted_rows_desc(rows: List[dict]) -> List[dict]:
    def key(row: dict) -> tuple:
        diff = row.get("difference_actual_minus_expected")
        diff_abs = abs(diff) if isinstance(diff, (int, float)) else -1
        return (
            int(row.get("actual_count", 0)),
            diff_abs,
            str(row.get("relation", "")),
        )

    return sorted(rows, key=key, reverse=True)


def build_grouped_rows_view(rows: List[dict], *, graph_only: bool) -> dict:
    base_rows = [row for row in rows if int(row.get("actual_count", 0)) > 0] if graph_only else list(rows)

    status_order = ["error", "warning", "ok"]
    status_groups: Dict[str, List[dict]] = {status: [] for status in status_order}
    for row in base_rows:
        status = str(row.get("status", "ok"))
        if status not in status_groups:
            status_groups[status] = []
        status_groups[status].append(row)

    branches: List[dict] = []
    for status in status_order + sorted(set(status_groups.keys()) - set(status_order)):
        group_rows = status_groups.get(status, [])
        if not group_rows:
            continue

        group_rows_sorted = _sorted_rows_desc(group_rows)
        flag_counter: Counter = Counter()
        for row in group_rows:
            for flag in row.get("flags", []):
                flag_counter[str(flag)] += 1

        by_flag_rows: Dict[str, List[dict]] = {}
        for row in group_rows:
            row_flags = row.get("flags", [])
            if not row_flags:
                by_flag_rows.setdefault("no_flag", []).append(row)
                continue
            for flag in row_flags:
                by_flag_rows.setdefault(str(flag), []).append(row)

        flag_groups: List[dict] = []
        for flag_name, flag_rows in sorted(by_flag_rows.items(), key=lambda kv: (len(kv[1]), kv[0]), reverse=True):
            flag_rows_sorted = _sorted_rows_desc(flag_rows)
            flag_groups.append(
                {
                    "flag": flag_name,
                    "summary": {
                        "rows": len(flag_rows_sorted),
                        "unique_relations": len({str(r.get("relation", "")) for r in flag_rows_sorted}),
                        "actual_count_total": sum(int(r.get("actual_count", 0)) for r in flag_rows_sorted),
                    },
                    "rows": flag_rows_sorted,
                }
            )

        branches.append(
            {
                "branch": status,
                "summary": {
                    "rows": len(group_rows_sorted),
                    "unique_relations": len({str(r.get("relation", "")) for r in group_rows_sorted}),
                    "actual_count_total": sum(int(r.get("actual_count", 0)) for r in group_rows_sorted),
                    "top_flags": [{"flag": flag, "count": count} for flag, count in flag_counter.most_common(10)],
                    "category_counts": dict(Counter(str(r.get("category") or "unknown") for r in group_rows_sorted)),
                },
                "rows": group_rows_sorted,
                "flag_groups": flag_groups,
            }
        )

    by_category_rows: Dict[str, List[dict]] = {}
    for row in base_rows:
        category = str(row.get("category") or "unknown")
        by_category_rows.setdefault(category, []).append(row)

    category_groups: List[dict] = []
    for category_name, category_rows in sorted(
        by_category_rows.items(), key=lambda kv: (len(kv[1]), kv[0]), reverse=True
    ):
        category_rows_sorted = _sorted_rows_desc(category_rows)
        category_groups.append(
            {
                "category": category_name,
                "summary": {
                    "rows": len(category_rows_sorted),
                    "unique_relations": len({str(r.get("relation", "")) for r in category_rows_sorted}),
                    "actual_count_total": sum(int(r.get("actual_count", 0)) for r in category_rows_sorted),
                    "status_counts": dict(Counter(str(r.get("status") or "ok") for r in category_rows_sorted)),
                },
                "rows": category_rows_sorted,
            }
        )

    return {
        "mode": "grouped_errors_graph_only" if graph_only else "grouped_errors",
        "summary": {
            "rows_considered": len(base_rows),
            "unique_relations_considered": len({str(r.get("relation", "")) for r in base_rows}),
            "actual_count_total": sum(int(r.get("actual_count", 0)) for r in base_rows),
            "status_counts": {b["branch"]: int(b["summary"]["rows"]) for b in branches},
            "category_counts": dict(Counter(str(r.get("category") or "unknown") for r in base_rows)),
        },
        "branches": branches,
        "category_groups": category_groups,
    }


def write_csv(rows: List[dict], out_csv: Path) -> None:
    fieldnames = [
        "relation",
        "pattern",
        "patterns",
        "category",
        "allocation_row_count",
        "actual_count",
        "in_allocation",
        "eta_integer",
        "eta_integer_by_pattern",
        "eta_integer_values",
        "eta_expected",
        "eta_total",
        "difference_actual_minus_expected",
        "actual_over_expected_ratio",
        "forward_score",
        "backward_score",
        "p_forward",
        "p_backward",
        "p_avg",
        "relation_dom_rng_class",
        "status",
        "flags",
    ]

    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row_out = dict(row)
            row_out["flags"] = "|".join(row_out["flags"])
            row_out["patterns"] = json.dumps(row_out.get("patterns"), ensure_ascii=False)
            row_out["eta_integer_by_pattern"] = json.dumps(row_out.get("eta_integer_by_pattern"), ensure_ascii=False)
            row_out["eta_integer_values"] = json.dumps(row_out.get("eta_integer_values"), ensure_ascii=False)
            writer.writerow({k: row_out.get(k) for k in fieldnames})


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit actual relation counts against allocation expectations."
    )
    parser.add_argument(
        "--triples_jsonl",
        required=True,
        type=Path,
        help="Path to triples JSONL file.",
    )
    parser.add_argument(
        "--allocation",
        required=True,
        type=Path,
        help="Path to allocation JSON or JSONL file.",
    )
    parser.add_argument(
        "--out_dir",
        required=True,
        type=Path,
        help="Directory where report files will be written.",
    )
    parser.add_argument(
        "--exclude_expected_but_absent",
        action="store_true",
        help="Do not include relations that are only in the allocation and absent from the graph.",
    )
    parser.add_argument(
        "--eta_aggregation",
        choices=["sum", "max"],
        default="sum",
        help="How to aggregate duplicate relation rows from allocation when computing eta_integer.",
    )
    parser.add_argument(
        "--rows_mode",
        choices=["flat", "grouped_errors", "grouped_errors_graph_only"],
        default="flat",
        help=(
            "Row view in JSON report: flat keeps current rows list; grouped_errors groups by status/flags; "
            "grouped_errors_graph_only does the same but only for relations with actual_count > 0."
        ),
    )

    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    relation_counts = count_relations_in_triples(args.triples_jsonl)
    allocation_records = load_json_or_jsonl(args.allocation)
    allocation_index = build_allocation_index(allocation_records, eta_aggregation=str(args.eta_aggregation))

    rows = build_full_report(
        relation_counts=relation_counts,
        allocation_index=allocation_index,
        include_expected_but_absent=not args.exclude_expected_but_absent,
    )

    summary = build_summary(rows, triples_total=sum(relation_counts.values()))

    out_json = args.out_dir / "relation_audit_report.json"
    out_csv = args.out_dir / "relation_audit_summary.csv"

    report = {
        "inputs": {
            "triples_jsonl": str(args.triples_jsonl),
            "allocation": str(args.allocation),
            "eta_aggregation": str(args.eta_aggregation),
            "rows_mode": str(args.rows_mode),
        },
        "summary": summary,
        "rows": rows,
    }

    if args.rows_mode == "grouped_errors":
        report["rows_grouped"] = build_grouped_rows_view(rows, graph_only=False)
    elif args.rows_mode == "grouped_errors_graph_only":
        report["rows_grouped"] = build_grouped_rows_view(rows, graph_only=True)

    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    write_csv(rows, out_csv)

    print(f"Wrote JSON report: {out_json}")
    print(f"Wrote CSV summary: {out_csv}")


if __name__ == "__main__":
    main()
    # /data/horse/ws/omel305g-omel305g-new/hpc_kg_balanced/.venv/bin/python src/statistics/audit_relation_counts.py --triples_jsonl data/connectedgraph/trial9/all_trial9_unique_triplets.triplets.json --allocation data/connectedgraph/bidirectional_allocation_results_allsupp50_conf97_compconf90.json --out_dir data/connectedgraph/trial9/relation_audit_before_repair --eta_aggregation sum --rows_mode grouped_errors_graph_only