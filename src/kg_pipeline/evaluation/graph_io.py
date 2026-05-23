"""Graph loading and duplicate-safe graph summary helpers."""

from __future__ import annotations

import csv
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

Triple = tuple[str, str, str]


def normalize_triple(h: Any, r: Any, t: Any) -> Triple:
    """Return a normalized ``(h, r, t)`` triple tuple."""
    if h is None or r is None or t is None:
        raise ValueError("Triple fields h, r, and t must be non-null")
    return str(h), str(r), str(t)


def load_graph_triples(path: str | Path) -> list[Triple]:
    """Load graph triples from CSV or JSONL files with h/r/t fields."""
    graph_path = Path(path)
    suffix = graph_path.suffix.lower()
    if suffix == ".csv":
        return load_csv_graph_triples(graph_path)
    if suffix == ".jsonl":
        return load_jsonl_graph_triples(graph_path)
    raise ValueError(f"Unsupported graph extension {graph_path.suffix!r}; use .csv or .jsonl")


def load_csv_graph_triples(path: Path) -> list[Triple]:
    triples: list[Triple] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"h", "r", "t"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV graph missing required columns: {sorted(missing)}")
        for row in reader:
            triples.append(normalize_triple(row["h"], row["r"], row["t"]))
    return triples


def load_jsonl_graph_triples(path: Path) -> list[Triple]:
    triples: list[Triple] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            try:
                triples.append(normalize_triple(obj["h"], obj["r"], obj["t"]))
            except KeyError as exc:
                raise ValueError(f"JSONL graph line {line_no} missing key {exc}") from exc
    return triples


def unique_triples(triples: Iterable[Triple]) -> set[Triple]:
    return set(triples)


def count_entities(triples: Iterable[Triple]) -> int:
    entities: set[str] = set()
    for h, _r, t in triples:
        entities.add(h)
        entities.add(t)
    return len(entities)


def count_relations(triples: Iterable[Triple]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for _h, r, _t in triples:
        counts[r] += 1
    return counts


def relation_count_distribution(relation_counts: Counter[str] | dict[str, int]) -> dict[str, Any]:
    values = sorted(int(value) for value in relation_counts.values())
    if not values:
        return {
            "min": 0,
            "max": 0,
            "mean": 0.0,
            "median": 0.0,
            "histogram": {},
        }
    histogram: dict[str, int] = {}
    for value in values:
        if value < 10:
            bucket = "1-9"
        elif value < 50:
            bucket = "10-49"
        elif value < 100:
            bucket = "50-99"
        elif value < 250:
            bucket = "100-249"
        elif value < 500:
            bucket = "250-499"
        elif value < 1000:
            bucket = "500-999"
        else:
            bucket = "1000+"
        histogram[bucket] = histogram.get(bucket, 0) + 1
    return {
        "min": values[0],
        "max": values[-1],
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "histogram": histogram,
    }


def summarize_graph_triples(triples: Sequence[Triple]) -> dict[str, Any]:
    """Summarize raw and unique triples without computing connectivity."""
    raw_relation_counts = count_relations(triples)
    unique = unique_triples(triples)
    unique_relation_counts = count_relations(unique)
    unique_entity_count = count_entities(unique)
    duplicate_triple_count = len(triples) - len(unique)

    return {
        "raw_total_rows": len(triples),
        "total_triples": len(unique),
        "unique_triples": len(unique),
        "duplicate_triple_count": duplicate_triple_count,
        "unique_entities": unique_entity_count,
        "unique_relations": len(unique_relation_counts),
        "raw_relation_counts": dict(sorted(raw_relation_counts.items())),
        "unique_relation_counts": dict(sorted(unique_relation_counts.items())),
        "relation_counts": dict(sorted(unique_relation_counts.items())),
        "raw_relation_count_distribution": relation_count_distribution(raw_relation_counts),
        "unique_relation_count_distribution": relation_count_distribution(unique_relation_counts),
        "relation_count_distribution": relation_count_distribution(unique_relation_counts),
        "evaluation_notes": [
            "Allocation metrics are computed from unique triples.",
            "relation_counts is an alias for unique_relation_counts.",
            "Entity counts are computed from unique triples.",
        ],
    }

