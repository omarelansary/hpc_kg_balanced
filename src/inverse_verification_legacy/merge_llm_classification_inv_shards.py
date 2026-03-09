#!/usr/bin/env python3
"""
Merge sharded llm_classification_inv outputs into one final JSON file
in the same order as the original input JSONL.
"""

import argparse
import glob
import json
from typing import Any, Dict, Iterable, List


def iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                doc = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{idx}: {exc}") from exc
            if not isinstance(doc, dict):
                raise ValueError(f"Expected object at {path}:{idx}")
            yield doc


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge sharded inverse classification outputs.")
    parser.add_argument("--input_path", required=True, help="Original input JSONL for ordering.")
    parser.add_argument(
        "--shard_glob",
        required=True,
        help="Glob for shard output files, e.g. data/processed/hop_support.inv_llm.shard*.jsonl",
    )
    parser.add_argument("--output_path", required=True, help="Final merged JSON (array).")
    parser.add_argument(
        "--strict_complete",
        action="store_true",
        help="Fail if any r1 from input is missing in shard outputs.",
    )
    args = parser.parse_args()

    shard_files = sorted(glob.glob(args.shard_glob))
    if not shard_files:
        raise ValueError(f"No shard files matched: {args.shard_glob}")

    by_r1: Dict[str, Dict[str, Any]] = {}
    for p in shard_files:
        for row in iter_jsonl(p):
            r1 = row.get("r1")
            if not isinstance(r1, str) or not r1:
                continue
            if r1 in by_r1:
                raise ValueError(f"Duplicate r1 across shard outputs: {r1}")
            by_r1[r1] = row

    merged: List[Dict[str, Any]] = []
    missing: List[str] = []
    for src in iter_jsonl(args.input_path):
        r1 = src.get("r1")
        if not isinstance(r1, str) or not r1:
            continue
        row = by_r1.get(r1)
        if row is None:
            missing.append(r1)
            continue
        merged.append(row)

    if args.strict_complete and missing:
        raise ValueError(f"Missing {len(missing)} r1 rows in shard outputs")

    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=True, indent=2)
        f.write("\n")

    print(
        json.dumps(
            {
                "shard_files": len(shard_files),
                "merged_rows": len(merged),
                "missing_rows": len(missing),
                "output_path": args.output_path,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
