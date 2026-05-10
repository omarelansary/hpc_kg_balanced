#!/usr/bin/env python3
"""Export relation-pattern membership matrix (0/1) from allocation JSON.

Input JSON is expected to contain a top-level `pattern_groups` object, e.g.:
{
  "pattern_groups": {
    "symmetric": ["P31", ...],
    "anti_symmetric": [...],
    "inverse": [...],
    "composition": [...]
  }
}

Output CSV schema:
relation,symmetric,anti_symmetric,inverse,composition
P31,1,0,0,1
...
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple


DEFAULT_COLUMN_ORDER = ["symmetric", "anti_symmetric", "inverse", "composition"]
IGNORE_GROUP_KEYS = {"universe", "relations_universe"}


def _is_pid(value: str) -> bool:
    return isinstance(value, str) and len(value) >= 2 and value[0] == "P" and value[1:].isdigit()


def _relation_sort_key(pid: str) -> Tuple[int, int | str]:
    if _is_pid(pid):
        return (0, int(pid[1:]))
    return (1, pid)


def _load_pattern_groups(input_json: Path) -> Dict[str, Set[str]]:
    with input_json.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    groups_raw = payload.get("pattern_groups")
    if not isinstance(groups_raw, dict):
        raise RuntimeError("Input JSON must contain an object field: pattern_groups")

    groups: Dict[str, Set[str]] = {}
    for group_name, rels in groups_raw.items():
        name = str(group_name).strip()
        if not name or name in IGNORE_GROUP_KEYS:
            continue
        if not isinstance(rels, list):
            continue
        groups[name] = {str(r).strip() for r in rels if isinstance(r, str) and str(r).strip()}

    if not groups:
        raise RuntimeError("No usable pattern groups found in pattern_groups.")
    return groups


def _ordered_columns(groups: Dict[str, Set[str]], explicit: List[str] | None) -> List[str]:
    if explicit:
        cols = [c for c in explicit if c in groups and c not in IGNORE_GROUP_KEYS]
        if not cols:
            raise RuntimeError("None of the requested --columns are present in pattern_groups.")
        return cols

    cols: List[str] = [c for c in DEFAULT_COLUMN_ORDER if c in groups]
    remaining = sorted([c for c in groups.keys() if c not in cols])
    cols.extend(remaining)
    return cols


def _rows(relations: Iterable[str], columns: List[str], groups: Dict[str, Set[str]]) -> List[Dict[str, int | str]]:
    out: List[Dict[str, int | str]] = []
    for relation in sorted(set(relations), key=_relation_sort_key):
        row: Dict[str, int | str] = {"relation": relation}
        for col in columns:
            row[col] = 1 if relation in groups.get(col, set()) else 0
        out.append(row)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Export relation x pattern-group 0/1 membership CSV.")
    ap.add_argument("--input_json", required=True, help="Path to allocation JSON containing pattern_groups.")
    ap.add_argument("--output_csv", required=True, help="Output CSV path.")
    ap.add_argument(
        "--columns",
        default="",
        help="Optional comma-separated column order, e.g. symmetric,anti_symmetric,inverse,composition",
    )
    args = ap.parse_args()

    input_json = Path(args.input_json)
    if not input_json.exists():
        raise FileNotFoundError(f"Input JSON not found: {input_json}")

    groups = _load_pattern_groups(input_json)
    requested_cols = [c.strip() for c in str(args.columns).split(",") if c.strip()] if args.columns else None
    columns = _ordered_columns(groups, requested_cols)

    relations = set().union(*(groups[c] for c in columns))
    rows = _rows(relations, columns, groups)

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["relation"] + columns)
        writer.writeheader()
        writer.writerows(rows)

    print(
        f"[ok] wrote {len(rows)} rows x {len(columns)} pattern columns to {output_csv.resolve()}"
    )


if __name__ == "__main__":
    main()
