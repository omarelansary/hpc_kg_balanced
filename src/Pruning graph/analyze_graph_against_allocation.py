#!/usr/bin/env python3
"""
Compare an observed graph against a relation allocation target.

The script accepts:
- an allocation JSON/JSONL file with relation + eta_integer rows
- a graph file in CSV or JSONL with at least h/r/t or h/relation/t fields

It writes:
- summary.json
- relation_fulfillment.csv
- relation_fulfillment.jsonl
- missing_relations.csv
- extra_graph_relations.csv
- histogram_bins.csv
- expected_vs_observed_histogram.html
- top_relation_gaps.html
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

try:
    import plotly.graph_objects as go
except Exception:  # pragma: no cover - plotting is optional at runtime
    go = None


@dataclass(frozen=True)
class RelationAllocation:
    relation: str
    eta_integer: int
    eta_total: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def read_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} line {line_no}: {exc}") from exc


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name) for name in fieldnames})


def write_fallback_grouped_bar_html(
    path: Path,
    *,
    title: str,
    labels: Sequence[str],
    series: Sequence[Dict[str, Any]],
    table_rows: Sequence[Dict[str, Any]],
    table_columns: Sequence[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chart_height = 360
    left = 60
    right = 20
    top = 50
    bottom = 140
    chart_width = max(900, 38 * max(1, len(labels)) + left + right)
    plot_width = chart_width - left - right
    plot_height = chart_height - top - bottom
    max_value = max([1.0, *[float(value) for item in series for value in item["values"]]])
    group_width = plot_width / max(1, len(labels))
    bar_width = max(3.0, group_width / max(2.0, len(series) + 0.6))

    svg_parts: List[str] = [
        f'<svg width="{chart_width}" height="{chart_height}" viewBox="0 0 {chart_width} {chart_height}" '
        'xmlns="http://www.w3.org/2000/svg" role="img">'
    ]
    svg_parts.append(
        f'<text x="{chart_width / 2:.1f}" y="26" text-anchor="middle" '
        'font-size="18" font-family="sans-serif" font-weight="600">'
        f'{html.escape(title)}</text>'
    )
    svg_parts.append(
        f'<line x1="{left}" y1="{top + plot_height}" x2="{chart_width - right}" y2="{top + plot_height}" '
        'stroke="#444" stroke-width="1"/>'
    )
    svg_parts.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#444" stroke-width="1"/>'
    )

    for tick in range(6):
        tick_value = max_value * tick / 5.0
        y = top + plot_height - (tick_value / max_value) * plot_height
        svg_parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{chart_width - right}" y2="{y:.1f}" '
            'stroke="#ddd" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" font-size="10" '
            f'font-family="sans-serif">{tick_value:.0f}</text>'
        )

    for idx, label in enumerate(labels):
        group_x = left + idx * group_width
        for series_idx, item in enumerate(series):
            value = float(item["values"][idx])
            bar_height = 0.0 if max_value <= 0 else (value / max_value) * plot_height
            x = group_x + series_idx * bar_width
            y = top + plot_height - bar_height
            svg_parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width - 1:.1f}" height="{bar_height:.1f}" '
                f'fill="{item["color"]}"><title>{html.escape(item["name"])}: {value:.0f}</title></rect>'
            )
        label_x = group_x + (len(series) * bar_width) / 2.0
        label_y = top + plot_height + 12
        svg_parts.append(
            f'<g transform="translate({label_x:.1f},{label_y:.1f}) rotate(55)">'
            f'<text text-anchor="start" font-size="10" font-family="sans-serif">{html.escape(label)}</text>'
            '</g>'
        )

    legend_x = left
    legend_y = chart_height - 18
    for item in series:
        svg_parts.append(
            f'<rect x="{legend_x}" y="{legend_y - 10}" width="12" height="12" fill="{item["color"]}"/>'
        )
        svg_parts.append(
            f'<text x="{legend_x + 18}" y="{legend_y}" font-size="11" font-family="sans-serif">'
            f'{html.escape(item["name"])}</text>'
        )
        legend_x += 18 + max(60, 7 * len(item["name"]))

    svg_parts.append("</svg>")

    table_html = [
        '<table border="1" cellspacing="0" cellpadding="4" style="border-collapse: collapse; font-family: sans-serif; font-size: 12px;">',
        "<thead><tr>",
    ]
    for column in table_columns:
        table_html.append(f"<th>{html.escape(column)}</th>")
    table_html.append("</tr></thead><tbody>")
    for row in table_rows:
        table_html.append("<tr>")
        for column in table_columns:
            table_html.append(f"<td>{html.escape(str(row.get(column, '')))}</td>")
        table_html.append("</tr>")
    table_html.append("</tbody></table>")

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
</head>
<body style="margin: 24px; font-family: sans-serif;">
  <h1 style="font-size: 20px;">{html.escape(title)}</h1>
  <p style="max-width: 900px;">Fallback chart output generated without Plotly. The grouped bars above show the same data that is available in the table below.</p>
  {''.join(svg_parts)}
  <h2 style="font-size: 16px; margin-top: 28px;">Underlying data</h2>
  {''.join(table_html)}
</body>
</html>
"""
    path.write_text(page, encoding="utf-8")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def unique_preserving_order(values: Iterable[Any]) -> List[Any]:
    out: List[Any] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def normalize_patterns(value: Any) -> List[str]:
    if value is None:
        return ["(unlabeled)"]
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return unique_preserving_order(items) or ["(unlabeled)"]
    text = str(value).strip()
    return [text] if text else ["(unlabeled)"]


def compact_number(value: float) -> Any:
    rounded = round(float(value), 6)
    if abs(rounded - round(rounded)) < 1e-9:
        return int(round(rounded))
    return rounded


def apportion_integer_total(total: int, weights: Dict[str, float]) -> Dict[str, int]:
    positive = {key: float(weight) for key, weight in weights.items() if float(weight) > 0.0}
    if total <= 0 or not positive:
        return {key: 0 for key in weights}

    weight_sum = sum(positive.values())
    exact = {key: (total * weight / weight_sum) for key, weight in positive.items()}
    base = {key: int(math.floor(value)) for key, value in exact.items()}
    remainder_units = total - sum(base.values())
    order = sorted(
        positive,
        key=lambda key: (-(exact[key] - base[key]), key),
    )
    for key in order[:remainder_units]:
        base[key] += 1
    for key in weights:
        base.setdefault(key, 0)
    return base


def iter_allocation_records(path: Path) -> Iterator[Dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        yield from read_jsonl(path)
        return

    if suffix != ".json":
        raise ValueError(
            f"Unsupported allocation format for {path}. Expected .json or .jsonl."
        )

    obj = read_json(path)
    if isinstance(obj, dict) and isinstance(obj.get("allocations"), list):
        for idx, rec in enumerate(obj["allocations"]):
            if not isinstance(rec, dict):
                raise ValueError(
                    f"Invalid allocations[{idx}] in {path}: expected object, got {type(rec).__name__}"
                )
            yield rec
        return

    if isinstance(obj, list):
        for idx, rec in enumerate(obj):
            if not isinstance(rec, dict):
                raise ValueError(
                    f"Invalid allocation record {idx} in {path}: expected object, got {type(rec).__name__}"
                )
            yield rec
        return

    raise ValueError(
        f"Unsupported allocation JSON structure in {path}. "
        "Expected a top-level list or an object with an allocations list."
    )


def load_allocations(path: Path) -> List[RelationAllocation]:
    merged_records: Dict[str, Dict[str, Any]] = {}
    metadata_values: Dict[str, Dict[str, List[Any]]] = defaultdict(lambda: defaultdict(list))

    for rec in iter_allocation_records(path):
        eta_integer = int(rec.get("eta_integer", 0) or 0)
        if eta_integer <= 0:
            continue
        relation = str(rec["relation"])

        if relation not in merged_records:
            merged_records[relation] = {
                "relation": relation,
                "eta_integer": 0,
                "eta_total": 0.0 if rec.get("eta_total") is not None else None,
            }
        merged = merged_records[relation]
        merged["eta_integer"] += eta_integer

        if rec.get("eta_total") is not None:
            if merged["eta_total"] is None:
                merged["eta_total"] = 0.0
            merged["eta_total"] += safe_float(rec.get("eta_total"), 0.0)

        for key, value in rec.items():
            if key in {"relation", "eta_integer", "eta_total"}:
                continue
            metadata_values[relation][key].append(value)

    allocations: List[RelationAllocation] = []
    for relation, merged in merged_records.items():
        metadata: Dict[str, Any] = {}
        for key, values in metadata_values[relation].items():
            uniq_values = unique_preserving_order(values)
            metadata[key] = uniq_values[0] if len(uniq_values) == 1 else uniq_values
        allocations.append(
            RelationAllocation(
                relation=relation,
                eta_integer=int(merged["eta_integer"]),
                eta_total=merged.get("eta_total"),
                metadata=metadata,
            )
        )
    allocations.sort(key=lambda row: row.relation)
    return allocations


def normalize_graph_record(rec: Dict[str, Any]) -> Dict[str, str]:
    h = rec.get("h") or rec.get("head")
    r = rec.get("r") or rec.get("relation") or rec.get("rel")
    t = rec.get("t") or rec.get("tail")
    if not h or not r or not t:
        raise ValueError(f"Graph row missing h/r/t fields: {rec}")
    return {"h": str(h), "r": str(r), "t": str(t)}


def iter_graph_triples(path: Path) -> Iterator[Dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with open(path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for rec in reader:
                yield normalize_graph_record(rec)
        return

    if suffix == ".jsonl":
        for rec in read_jsonl(path):
            yield normalize_graph_record(rec)
        return

    raise ValueError(f"Unsupported graph format for {path}. Expected .csv or .jsonl.")


def histogram_bin_rows(
    expected_values: Sequence[int],
    observed_values: Sequence[int],
    bin_count: int,
) -> List[Dict[str, int]]:
    max_value = max([0, *expected_values, *observed_values])
    step = max(1, int(math.ceil((max_value + 1) / max(1, bin_count))))
    total_bins = max(1, int(math.ceil((max_value + 1) / step)))

    expected_hist = Counter()
    observed_hist = Counter()
    for value in expected_values:
        expected_hist[min(total_bins - 1, value // step)] += 1
    for value in observed_values:
        observed_hist[min(total_bins - 1, value // step)] += 1

    rows: List[Dict[str, int]] = []
    for idx in range(total_bins):
        start = idx * step
        end = start + step - 1
        exp_count = int(expected_hist.get(idx, 0))
        obs_count = int(observed_hist.get(idx, 0))
        rows.append(
            {
                "bin_index": idx,
                "bin_start": start,
                "bin_end": end,
                "expected_relation_count": exp_count,
                "observed_relation_count": obs_count,
                "expected_minus_observed": exp_count - obs_count,
            }
        )
    return rows


def write_histogram_html(
    path: Path,
    histogram_rows: Sequence[Dict[str, int]],
    title: str,
) -> None:
    labels = [f"{row['bin_start']}-{row['bin_end']}" for row in histogram_rows]
    expected = [row["expected_relation_count"] for row in histogram_rows]
    observed = [row["observed_relation_count"] for row in histogram_rows]
    diff = [row["expected_minus_observed"] for row in histogram_rows]

    if go is None:
        write_fallback_grouped_bar_html(
            path,
            title=title,
            labels=labels,
            series=[
                {"name": "Expected eta", "values": expected, "color": "#1f77b4"},
                {"name": "Observed graph count", "values": observed, "color": "#ff7f0e"},
            ],
            table_rows=[
                {
                    "bin": label,
                    "expected_relation_count": exp,
                    "observed_relation_count": obs,
                    "expected_minus_observed": delta,
                }
                for label, exp, obs, delta in zip(labels, expected, observed, diff)
            ],
            table_columns=[
                "bin",
                "expected_relation_count",
                "observed_relation_count",
                "expected_minus_observed",
            ],
        )
        return

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Expected eta", x=labels, y=expected))
    fig.add_trace(go.Bar(name="Observed graph count", x=labels, y=observed))
    fig.add_trace(
        go.Scatter(
            name="Expected minus observed",
            x=labels,
            y=diff,
            mode="lines+markers",
            yaxis="y2",
        )
    )
    fig.update_layout(
        title=title,
        barmode="group",
        xaxis_title="Relation count bin",
        yaxis_title="Number of relations",
        yaxis2=dict(
            title="Histogram difference",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        legend=dict(orientation="h"),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(path), include_plotlyjs=True)


def write_gap_chart_html(
    path: Path,
    relation_rows: Sequence[Dict[str, Any]],
    top_n: int,
    title: str,
) -> None:
    top_rows = sorted(
        relation_rows,
        key=lambda row: (-int(row["deficit"]), -int(row["eta_integer"]), row["relation"]),
    )[:top_n]
    labels = [row["relation"] for row in top_rows]
    expected = [int(row["eta_integer"]) for row in top_rows]
    observed = [int(row["observed_count"]) for row in top_rows]
    deficit = [int(row["deficit"]) for row in top_rows]

    if go is None:
        write_fallback_grouped_bar_html(
            path,
            title=title,
            labels=labels,
            series=[
                {"name": "Expected eta", "values": expected, "color": "#1f77b4"},
                {"name": "Observed graph count", "values": observed, "color": "#ff7f0e"},
            ],
            table_rows=[
                {
                    "relation": row["relation"],
                    "eta_integer": row["eta_integer"],
                    "observed_count": row["observed_count"],
                    "deficit": row["deficit"],
                    "pattern": row["pattern"],
                }
                for row in top_rows
            ],
            table_columns=[
                "relation",
                "eta_integer",
                "observed_count",
                "deficit",
                "pattern",
            ],
        )
        return

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Expected eta", x=labels, y=expected))
    fig.add_trace(go.Bar(name="Observed graph count", x=labels, y=observed))
    fig.add_trace(
        go.Scatter(
            name="Deficit",
            x=labels,
            y=deficit,
            mode="lines+markers",
            yaxis="y2",
        )
    )
    fig.update_layout(
        title=title,
        barmode="group",
        xaxis_title="Relation",
        yaxis_title="Triple count",
        yaxis2=dict(
            title="Deficit",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        legend=dict(orientation="h"),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(path), include_plotlyjs=True)


def build_relation_rows(
    allocations: Sequence[RelationAllocation],
    observed_counts: Counter[str],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for allocation in allocations:
        observed = int(observed_counts.get(allocation.relation, 0))
        eta = int(allocation.eta_integer)
        deficit = max(0, eta - observed)
        surplus = max(0, observed - eta)
        patterns = allocation.metadata.get("pattern")
        if isinstance(patterns, list):
            pattern_text = "|".join(str(v) for v in patterns)
        elif patterns is None:
            pattern_text = ""
        else:
            pattern_text = str(patterns)
        rows.append(
            {
                "relation": allocation.relation,
                "eta_integer": eta,
                "observed_count": observed,
                "deficit": deficit,
                "surplus": surplus,
                "fulfilled": observed >= eta,
                "exactly_fulfilled": observed == eta,
                "overfilled": observed > eta,
                "observed_ratio": round(observed / eta, 6) if eta > 0 else None,
                "eta_total": allocation.eta_total,
                "pattern": pattern_text,
            }
        )
    return rows


def build_pattern_rows(
    allocation_path: Path,
    observed_counts: Counter[str],
) -> List[Dict[str, Any]]:
    relation_pattern_expected: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    pattern_expected_totals: Dict[str, float] = defaultdict(float)
    pattern_relation_members: Dict[str, set[str]] = defaultdict(set)

    for rec in iter_allocation_records(allocation_path):
        eta_integer = int(rec.get("eta_integer", 0) or 0)
        if eta_integer <= 0:
            continue
        relation = str(rec["relation"])
        patterns = normalize_patterns(rec.get("pattern"))
        share = float(eta_integer) / float(len(patterns))
        for pattern in patterns:
            relation_pattern_expected[relation][pattern] += share
            pattern_expected_totals[pattern] += share
            pattern_relation_members[pattern].add(relation)

    pattern_observed_totals: Counter[str] = Counter()
    for relation, pattern_weights in relation_pattern_expected.items():
        observed = int(observed_counts.get(relation, 0))
        apportioned = apportion_integer_total(observed, pattern_weights)
        for pattern, count in apportioned.items():
            pattern_observed_totals[pattern] += int(count)

    all_patterns = sorted(set(pattern_expected_totals) | set(pattern_observed_totals))
    rows: List[Dict[str, Any]] = []
    for pattern in all_patterns:
        expected = float(pattern_expected_totals.get(pattern, 0.0))
        observed = int(pattern_observed_totals.get(pattern, 0))
        deficit = max(0.0, expected - float(observed))
        surplus = max(0.0, float(observed) - expected)
        rows.append(
            {
                "pattern": pattern,
                "expected_eta": compact_number(expected),
                "observed_count": observed,
                "deficit": compact_number(deficit),
                "surplus": compact_number(surplus),
                "relation_count": len(pattern_relation_members.get(pattern, set())),
            }
        )
    rows.sort(key=lambda row: str(row["pattern"]))
    return rows


def build_unique_triple_pattern_summaries(
    allocations: Sequence[RelationAllocation],
    unique_triples: Iterable[tuple[str, str, str]],
) -> Dict[str, Any]:
    relation_patterns: Dict[str, List[str]] = {
        allocation.relation: normalize_patterns(allocation.metadata.get("pattern"))
        for allocation in allocations
    }

    membership_counts: Counter[str] = Counter()
    combination_counts: Counter[str] = Counter()
    combination_patterns: Dict[str, List[str]] = {}

    for _, relation, _ in unique_triples:
        patterns = relation_patterns.get(relation, ["(unlabeled)"])
        normalized_patterns = unique_preserving_order(patterns) or ["(unlabeled)"]
        for pattern in normalized_patterns:
            membership_counts[pattern] += 1
        combination_key = "|".join(normalized_patterns)
        combination_counts[combination_key] += 1
        combination_patterns.setdefault(combination_key, list(normalized_patterns))

    membership_rows = [
        {
            "pattern": pattern,
            "unique_triple_count": int(membership_counts[pattern]),
        }
        for pattern in sorted(membership_counts)
    ]
    combination_rows = [
        {
            "pattern_combination": combo_key,
            "patterns": list(combination_patterns[combo_key]),
            "unique_triple_count": int(combination_counts[combo_key]),
        }
        for combo_key in sorted(combination_counts)
    ]

    return {
        "pattern_membership_unique_triple_counts": {
            row["pattern"]: row["unique_triple_count"] for row in membership_rows
        },
        "pattern_membership_unique_triple_rows": membership_rows,
        "pattern_membership_unique_triple_counting_method": (
            "Each unique graph triple is counted once for every pattern associated "
            "with its relation. A triple whose relation belongs to multiple patterns "
            "therefore contributes to multiple pattern buckets."
        ),
        "pattern_combination_unique_triple_counts": {
            row["pattern_combination"]: row["unique_triple_count"] for row in combination_rows
        },
        "pattern_combination_unique_triple_rows": combination_rows,
        "pattern_combination_unique_triple_counting_method": (
            "Each unique graph triple is counted exactly once in the bucket for the "
            "full pattern combination associated with its relation."
        ),
    }


def summarize_relation_rows(
    relation_rows: Sequence[Dict[str, Any]],
    pattern_rows: Sequence[Dict[str, Any]],
    extra_graph_relations: Sequence[Dict[str, Any]],
    graph_triple_count: int,
    graph_unique_triple_count: int,
    graph_unique_relations: int,
    graph_path: Path,
    allocation_path: Path,
    unique_triple_pattern_summary: Dict[str, Any],
) -> Dict[str, Any]:
    fulfilled = [row for row in relation_rows if row["fulfilled"]]
    exact = [row for row in relation_rows if row["exactly_fulfilled"]]
    overfilled = [row for row in relation_rows if row["overfilled"]]
    partial = [row for row in relation_rows if row["observed_count"] > 0 and row["observed_count"] < row["eta_integer"]]
    zero = [row for row in relation_rows if row["observed_count"] == 0]
    total_eta = sum(int(row["eta_integer"]) for row in relation_rows)
    total_observed_allocated = sum(int(row["observed_count"]) for row in relation_rows)
    total_deficit = sum(int(row["deficit"]) for row in relation_rows)
    total_surplus = sum(int(row["surplus"]) for row in relation_rows)
    weighted_fulfillment_ratio = (
        round(total_observed_allocated / total_eta, 6) if total_eta > 0 else None
    )

    top_missing = sorted(
        (
            {
                "relation": row["relation"],
                "eta_integer": row["eta_integer"],
                "observed_count": row["observed_count"],
                "deficit": row["deficit"],
                "pattern": row["pattern"],
            }
            for row in relation_rows
            if int(row["deficit"]) > 0
        ),
        key=lambda row: (-int(row["deficit"]), -int(row["eta_integer"]), row["relation"]),
    )[:25]

    per_relation_expected_vs_observed = [
        {
            "relation": row["relation"],
            "eta_integer": int(row["eta_integer"]),
            "observed_count": int(row["observed_count"]),
            "deficit": int(row["deficit"]),
            "surplus": int(row["surplus"]),
            "fulfilled": bool(row["fulfilled"]),
            "pattern": row["pattern"],
        }
        for row in sorted(relation_rows, key=lambda item: item["relation"])
    ]

    return {
        "graph_path": str(graph_path),
        "allocation_path": str(allocation_path),
        "allocation_rows_merged_by_relation": True,
        "observed_graph_triples_counted_once_per_row": True,
        "graph_triple_count": graph_triple_count,
        "graph_unique_triple_count": graph_unique_triple_count,
        "graph_unique_relations": graph_unique_relations,
        "allocated_relation_count": len(relation_rows),
        "fully_fulfilled_relations": len(fulfilled),
        "exactly_fulfilled_relations": len(exact),
        "overfilled_relations": len(overfilled),
        "partially_fulfilled_relations": len(partial),
        "zero_relations": len(zero),
        "total_expected_eta": total_eta,
        "total_observed_allocated_triples": total_observed_allocated,
        "total_deficit": total_deficit,
        "total_surplus": total_surplus,
        "weighted_fulfillment_ratio": weighted_fulfillment_ratio,
        "extra_graph_relation_count": len(extra_graph_relations),
        "top_missing_relations": top_missing,
        "pattern_expected_vs_observed": list(pattern_rows),
        "pattern_observed_count_is_apportioned": True,
        "pattern_observed_apportionment_method": (
            "Observed relation counts are redistributed back to raw allocation patterns "
            "in proportion to each relation-pattern eta contribution using largest-remainder integer rounding."
        ),
        "per_relation_expected_vs_observed": per_relation_expected_vs_observed,
        **unique_triple_pattern_summary,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare an observed graph against an allocation target.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--graph_path", required=True, help="Path to graph CSV or JSONL.")
    parser.add_argument("--allocation_path", required=True, help="Path to allocation JSON or JSONL.")
    parser.add_argument("--out_dir", required=True, help="Directory for summary tables and plots.")
    parser.add_argument("--hist_bins", type=int, default=25, help="Number of bins for eta/count histograms.")
    parser.add_argument("--top_gap_relations", type=int, default=30, help="How many largest-deficit relations to chart.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    graph_path = Path(args.graph_path)
    allocation_path = Path(args.allocation_path)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    allocations = load_allocations(allocation_path)
    observed_counts: Counter[str] = Counter()
    graph_triple_count = 0
    unique_triples: set[tuple[str, str, str]] = set()
    for rec in iter_graph_triples(graph_path):
        graph_triple_count += 1
        observed_counts[rec["r"]] += 1
        unique_triples.add((rec["h"], rec["r"], rec["t"]))

    relation_rows = build_relation_rows(allocations, observed_counts)
    pattern_rows = build_pattern_rows(allocation_path, observed_counts)
    unique_triple_pattern_summary = build_unique_triple_pattern_summaries(allocations, unique_triples)
    allocated_relations = {row["relation"] for row in relation_rows}
    extra_graph_relations = sorted(
        (
            {
                "relation": relation,
                "observed_count": int(count),
            }
            for relation, count in observed_counts.items()
            if relation not in allocated_relations
        ),
        key=lambda row: (-int(row["observed_count"]), row["relation"]),
    )

    summary = summarize_relation_rows(
        relation_rows,
        pattern_rows,
        extra_graph_relations,
        graph_triple_count=graph_triple_count,
        graph_unique_triple_count=len(unique_triples),
        graph_unique_relations=len(observed_counts),
        graph_path=graph_path,
        allocation_path=allocation_path,
        unique_triple_pattern_summary=unique_triple_pattern_summary,
    )

    histogram_rows = histogram_bin_rows(
        expected_values=[int(row["eta_integer"]) for row in relation_rows],
        observed_values=[int(row["observed_count"]) for row in relation_rows],
        bin_count=args.hist_bins,
    )

    relation_rows_sorted = sorted(
        relation_rows,
        key=lambda row: (-int(row["deficit"]), row["relation"]),
    )
    missing_relations = [row for row in relation_rows_sorted if int(row["deficit"]) > 0]

    write_json(out_dir / "summary.json", summary)
    write_jsonl(out_dir / "relation_fulfillment.jsonl", relation_rows_sorted)
    write_csv(
        out_dir / "relation_fulfillment.csv",
        relation_rows_sorted,
        fieldnames=[
            "relation",
            "eta_integer",
            "observed_count",
            "deficit",
            "surplus",
            "fulfilled",
            "exactly_fulfilled",
            "overfilled",
            "observed_ratio",
            "eta_total",
            "pattern",
        ],
    )
    write_csv(
        out_dir / "missing_relations.csv",
        missing_relations,
        fieldnames=[
            "relation",
            "eta_integer",
            "observed_count",
            "deficit",
            "observed_ratio",
            "pattern",
        ],
    )
    write_csv(
        out_dir / "extra_graph_relations.csv",
        extra_graph_relations,
        fieldnames=["relation", "observed_count"],
    )
    write_csv(
        out_dir / "histogram_bins.csv",
        histogram_rows,
        fieldnames=[
            "bin_index",
            "bin_start",
            "bin_end",
            "expected_relation_count",
            "observed_relation_count",
            "expected_minus_observed",
        ],
    )

    write_histogram_html(
        out_dir / "expected_vs_observed_histogram.html",
        histogram_rows,
        title="Expected eta distribution vs observed graph relation counts",
    )
    write_gap_chart_html(
        out_dir / "top_relation_gaps.html",
        relation_rows_sorted,
        top_n=args.top_gap_relations,
        title=f"Top {args.top_gap_relations} relation deficits",
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
