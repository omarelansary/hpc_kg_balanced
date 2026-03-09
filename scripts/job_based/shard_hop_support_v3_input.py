#!/usr/bin/env python3
"""Shard hop_support_v3 input into disjoint JSONL files by r1.

This helper is intentionally minimal and safe:
- accepts JSONL or JSON-array input
- keeps only the latest row per r1 (input order)
- assigns each r1 deterministically to one shard
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


def _load_json_or_jsonl(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            return [parsed]
    except json.JSONDecodeError:
        pass

    out: List[Dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _dedupe_latest_by_r1(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest_by_r1: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    seen = set()
    for row in rows:
        r1 = row.get("r1")
        if not isinstance(r1, str) or not r1:
            continue
        if r1 not in seen:
            seen.add(r1)
            order.append(r1)
        latest_by_r1[r1] = row
    return [latest_by_r1[r1] for r1 in order]


def _assign_shard(r1: str, num_shards: int) -> int:
    h = hashlib.sha1(r1.encode("utf-8")).hexdigest()
    return int(h[:16], 16) % num_shards


def main() -> None:
    ap = argparse.ArgumentParser(description="Shard hop_support_v3 input JSONL by r1.")
    ap.add_argument("--input", required=True, help="Input JSON/JSONL path.")
    ap.add_argument("--output_dir", required=True, help="Directory for shard JSONL files.")
    ap.add_argument("--num_shards", type=int, required=True, help="Number of shards (>0).")
    ap.add_argument("--prefix", default="hop_support_v3_input", help="Shard filename prefix.")
    args = ap.parse_args()

    if args.num_shards <= 0:
        raise ValueError("num_shards must be > 0")

    in_path = Path(args.input)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _load_json_or_jsonl(in_path)
    rows = _dedupe_latest_by_r1(rows)

    buckets: List[List[Dict[str, Any]]] = [[] for _ in range(args.num_shards)]
    skipped = 0
    for row in rows:
        r1 = row.get("r1")
        if not isinstance(r1, str) or not r1:
            skipped += 1
            continue
        sid = _assign_shard(r1, args.num_shards)
        buckets[sid].append(row)

    width = max(2, len(str(args.num_shards)))
    written = 0
    shard_paths: List[str] = []
    for sid, bucket in enumerate(buckets):
        shard_id = f"{sid:0{width}d}"
        shard_n = f"{args.num_shards:0{width}d}"
        p = out_dir / f"{args.prefix}.s{shard_id}of{shard_n}.jsonl"
        shard_paths.append(str(p))
        with p.open("w", encoding="utf-8") as f:
            for row in bucket:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        written += len(bucket)

    manifest = {
        "input": str(in_path),
        "output_dir": str(out_dir),
        "num_shards": int(args.num_shards),
        "prefix": args.prefix,
        "rows_after_dedupe": len(rows),
        "rows_skipped_missing_r1": int(skipped),
        "rows_written": int(written),
        "shards": [
            {
                "index": i,
                "path": shard_paths[i],
                "rows": len(buckets[i]),
            }
            for i in range(args.num_shards)
        ],
    }
    manifest_path = out_dir / f"{args.prefix}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print("shard_complete")
    print(f"input_rows_after_dedupe: {len(rows)}")
    print(f"rows_written: {written}")
    print(f"rows_skipped_missing_r1: {skipped}")
    print(f"num_shards: {args.num_shards}")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()

