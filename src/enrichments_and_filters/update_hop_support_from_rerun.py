#!/usr/bin/env python3
"""Update base hop_support JSONL from rerun JSONL, skipping ERROR=>ERROR transitions.

Rules:
- Match records by r1.
- For each r1 in rerun:
  - If base status is ERROR and rerun status is ERROR, keep base record unchanged.
  - Otherwise replace/add with rerun record.
- Writes output as JSONL in deterministic base-first order.
"""

from __future__ import annotations

import argparse
import json
import shutil
from typing import Any, Dict, List, Tuple


def load_jsonl_latest(path: str) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    latest: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    seen = set()

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            obj = json.loads(line)
            r1 = obj.get("r1")
            if not isinstance(r1, str) or not r1:
                continue
            if r1 not in seen:
                seen.add(r1)
                order.append(r1)
            latest[r1] = obj

    return latest, order


def status_of(rec: Dict[str, Any] | None) -> str:
    if not rec:
        return "MISSING"
    s = rec.get("status")
    return s if isinstance(s, str) and s else "UNKNOWN"


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge rerun hop_support into base, excluding ERROR=>ERROR")
    ap.add_argument("--base", required=True, help="Base hop_support JSONL to update")
    ap.add_argument("--rerun", required=True, help="Rerun hop_support JSONL")
    ap.add_argument("--out", required=True, help="Output merged JSONL")
    ap.add_argument("--backup_base", action="store_true", help="Create <base>.bak before merge")
    args = ap.parse_args()

    if args.backup_base:
        backup_path = args.base + ".bak"
        shutil.copyfile(args.base, backup_path)
        print(f"backup_created: {backup_path}")

    base, base_order = load_jsonl_latest(args.base)
    rerun, rerun_order = load_jsonl_latest(args.rerun)

    replaced = 0
    added = 0
    skipped_error_to_error = 0

    for r1 in rerun_order:
        old = base.get(r1)
        new = rerun[r1]

        old_status = status_of(old)
        new_status = status_of(new)

        if old_status == "ERROR" and new_status == "ERROR":
            skipped_error_to_error += 1
            continue

        if r1 in base:
            replaced += 1
        else:
            added += 1
            base_order.append(r1)
        base[r1] = new

    with open(args.out, "w", encoding="utf-8") as w:
        for r1 in base_order:
            rec = base.get(r1)
            if rec is not None:
                w.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("merge_complete")
    print(f"base_unique_r1: {len(base_order)}")
    print(f"rerun_unique_r1: {len(rerun)}")
    print(f"replaced: {replaced}")
    print(f"added: {added}")
    print(f"skipped_ERROR_to_ERROR: {skipped_error_to_error}")
    print(f"output: {args.out}")


if __name__ == "__main__":
    main()
    # python scripts/update_hop_support_from_rerun.py --base data/processed/hop_support.jsonl --rerun data/archived/hop_support_failed_rerun.jsonl --out data/processed/hop_support_merged.jsonl --backup_base

