#!/usr/bin/env python3
"""
Filter hop_discovery docs to only those whose r1 has non-SUCCESS status
in a prior hop_support JSONL output. Accepts hop_discovery as JSON array
or JSONL, and always writes JSONL.

Example:
  python src/filter_failed_hop_support.py \
    --hop_support data/processed/hop_support.jsonl \
    --hop_discovery data/raw/wikidata_ontology.hop_discovery_run2.json \
    --out data/processed/hop_discovery_failed_only.jsonl
"""

from __future__ import annotations

import argparse
import json
from typing import Set


def load_failed_r1s(hop_support_path: str) -> Set[str]:
    failed: Set[str] = set()
    with open(hop_support_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("status") != "SUCCESS":
                r1 = obj.get("r1")
                if r1:
                    failed.add(r1)
    return failed


def filter_hop_discovery(hop_discovery_path: str, out_path: str, failed: Set[str]) -> int:
    kept = 0
    with open(hop_discovery_path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if not text:
        return 0
    if text[0] == "[":
        docs = json.loads(text)
    else:
        docs = [json.loads(line) for line in text.splitlines() if line.strip()]
    with open(out_path, "w", encoding="utf-8") as w:
        for obj in docs:
            if obj.get("r1") in failed:
                w.write(json.dumps(obj, ensure_ascii=False) + "\n")
                kept += 1
    return kept


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Filter hop_discovery JSONL to only r1s that failed in hop_support JSONL",
    )
    ap.add_argument("--hop_support", required=True, help="Path to hop_support.jsonl")
    ap.add_argument("--hop_discovery", required=True, help="Path to hop_discovery JSON or JSONL")
    ap.add_argument("--out", required=True, help="Output JSONL path for filtered hop_discovery")
    args = ap.parse_args()

    failed = load_failed_r1s(args.hop_support)
    kept = filter_hop_discovery(args.hop_discovery, args.out, failed)
    print(f"failed r1s: {len(failed)}")
    print(f"kept docs: {kept}")
    print(f"output: {args.out}")


if __name__ == "__main__":
    main()
