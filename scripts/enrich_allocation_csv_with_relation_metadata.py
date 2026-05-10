#!/usr/bin/env python3
"""Enrich an allocation CSV with relation labels and descriptions.

The input CSV is expected to contain a `relation` column with Wikidata property
IDs such as `P31`. The script appends:
  - `label` from `wikidata_ontology.properties.json`
  - `description` from `relation_profiles_afterLLM_SecondTime.json`

Usage:
  python scripts/enrich_allocation_csv_with_relation_metadata.py \
      --input_csv 'src/Pruning graph/bidirectional_allocation_results5k.csv' \
      --properties_json 'data/raw/wikidata_ontology.properties.json' \
      --profiles_json 'data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json' \
      --output_csv 'src/Pruning graph/bidirectional_allocation_results5k.enriched.csv'
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load_properties_label_map(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    label_map: dict[str, str] = {}
    for row in data:
        property_id = str(row.get("property_id", "")).strip()
        if not property_id:
            continue
        label_map[property_id] = str(row.get("label", "")).strip()
    return label_map


def load_profiles_description_map(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    description_map: dict[str, str] = {}
    for row in data:
        property_id = str(row.get("property_id", "")).strip()
        if not property_id:
            continue
        metadata = row.get("metadata") or {}
        description_map[property_id] = str(metadata.get("description", "")).strip()
    return description_map


def enrich_csv(
    input_csv: Path,
    output_csv: Path,
    label_map: dict[str, str],
    description_map: dict[str, str],
) -> tuple[int, int, int]:
    with input_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "relation" not in reader.fieldnames:
            raise ValueError(f"Input CSV must contain a 'relation' column: {input_csv}")

        fieldnames = list(reader.fieldnames)
        for new_col in ["label", "description"]:
            if new_col not in fieldnames:
                fieldnames.append(new_col)

        rows = list(reader)

    missing_labels = 0
    missing_descriptions = 0
    for row in rows:
        relation = str(row.get("relation", "")).strip()
        label = label_map.get(relation, "")
        description = description_map.get(relation, "")
        row["label"] = label
        row["description"] = description
        if not label:
            missing_labels += 1
        if not description:
            missing_descriptions += 1

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows), missing_labels, missing_descriptions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input_csv", type=Path, required=True)
    parser.add_argument("--properties_json", type=Path, required=True)
    parser.add_argument("--profiles_json", type=Path, required=True)
    parser.add_argument("--output_csv", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    label_map = load_properties_label_map(args.properties_json)
    description_map = load_profiles_description_map(args.profiles_json)
    row_count, missing_labels, missing_descriptions = enrich_csv(
        args.input_csv,
        args.output_csv,
        label_map,
        description_map,
    )
    print(f"Wrote {row_count} rows to {args.output_csv}")
    print(f"Missing labels: {missing_labels}")
    print(f"Missing descriptions: {missing_descriptions}")


if __name__ == "__main__":
    main()
