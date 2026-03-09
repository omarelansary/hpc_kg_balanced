#!/usr/bin/env python3
"""Merge sharded hop_support_v3 outputs.

Modes:
- append: concatenate all JSONL records
- fail_on_duplicate_r1: error if same r1 appears twice
- dedupe_latest_by_r1: keep latest row per r1 by merged file order
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any, Dict, List


def _iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            yield line, json.loads(line)


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge shard JSONL files for hop_support_v3.")
    ap.add_argument("--shard_glob", required=True, help="Glob for shard JSONL files.")
    ap.add_argument("--output_path", required=True, help="Merged output JSONL path.")
    ap.add_argument(
        "--mode",
        choices=["append", "fail_on_duplicate_r1", "dedupe_latest_by_r1"],
        default="append",
        help="Merge behavior. Use append for triplets output.",
    )
    args = ap.parse_args()

    shard_files = sorted(glob.glob(args.shard_glob))
    if not shard_files:
        raise ValueError(f"No shard files matched: {args.shard_glob}")

    out_path = Path(args.output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "append":
        written = 0
        with out_path.open("w", encoding="utf-8") as w:
            for p in shard_files:
                for line, _obj in _iter_jsonl(Path(p)):
                    w.write(line + "\n")
                    written += 1
        print("merge_complete")
        print(f"mode: {args.mode}")
        print(f"shard_files: {len(shard_files)}")
        print(f"rows_written: {written}")
        print(f"output: {out_path}")
        return

    seen = set()
    latest: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    rows_in = 0
    dupes = 0

    for p in shard_files:
        for _line, obj in _iter_jsonl(Path(p)):
            rows_in += 1
            r1 = obj.get("r1")
            if not isinstance(r1, str) or not r1:
                continue

            if args.mode == "fail_on_duplicate_r1":
                if r1 in seen:
                    raise ValueError(f"Duplicate r1 found across shards: {r1}")
                seen.add(r1)
                latest[r1] = obj
                order.append(r1)
            else:
                if r1 not in seen:
                    seen.add(r1)
                    order.append(r1)
                else:
                    dupes += 1
                latest[r1] = obj

    with out_path.open("w", encoding="utf-8") as w:
        for r1 in order:
            w.write(json.dumps(latest[r1], ensure_ascii=False) + "\n")

    print("merge_complete")
    print(f"mode: {args.mode}")
    print(f"shard_files: {len(shard_files)}")
    print(f"rows_in: {rows_in}")
    print(f"rows_out: {len(order)}")
    print(f"duplicate_r1_seen: {dupes}")
    print(f"output: {out_path}")


if __name__ == "__main__":
    main()

