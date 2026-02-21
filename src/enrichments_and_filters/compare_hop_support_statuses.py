#!/usr/bin/env python3
"""Compare hop_support base vs failed-rerun outputs by r1.

Left join semantics:
- Left side: rerun file (every r1 in rerun is emitted)
- Right side: base/original file (matched on r1)

Outputs:
1) Joined JSONL with status and similarity comparison per r1
2) Summary JSON with transition and similarity statistics
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


VOLATILE_FIELDS = {"updated_at", "elapsed_sec", "query_time_sec"}


@dataclass
class LoadedRecords:
    latest_by_r1: Dict[str, Dict[str, Any]]
    order: List[str]
    total_lines: int
    valid_records: int
    duplicate_r1_overwrites: int


def load_jsonl_latest(path: str) -> LoadedRecords:
    latest: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    seen = set()
    total = 0
    valid = 0
    overwrites = 0

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            total += 1
            obj = json.loads(line)
            r1 = obj.get("r1")
            if not isinstance(r1, str) or not r1:
                continue
            valid += 1
            if r1 not in seen:
                seen.add(r1)
                order.append(r1)
            else:
                overwrites += 1
            latest[r1] = obj

    return LoadedRecords(
        latest_by_r1=latest,
        order=order,
        total_lines=total,
        valid_records=valid,
        duplicate_r1_overwrites=overwrites,
    )


def status_of(rec: Dict[str, Any] | None) -> str:
    if not rec:
        return "MISSING"
    s = rec.get("status")
    return s if isinstance(s, str) and s else "UNKNOWN"


def normalize_record(rec: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if rec is None:
        return None
    return {k: v for k, v in rec.items() if k not in VOLATILE_FIELDS}


def error_str(rec: Dict[str, Any] | None) -> str | None:
    if rec is None:
        return None
    err = rec.get("error")
    if isinstance(err, str):
        return err
    return None


def extract_support_map(rec: Dict[str, Any] | None) -> Dict[str, float] | None:
    if not rec:
        return None

    # v1 values_chunked
    if isinstance(rec.get("support_by_r2"), dict):
        out: Dict[str, float] = {}
        for pid, val in rec["support_by_r2"].items():
            try:
                out[str(pid)] = float(val)
            except Exception:
                continue
        return out

    # v2 support map: {pid: {loop, nonloop, total}}
    if isinstance(rec.get("support_data"), dict):
        out: Dict[str, float] = {}
        for pid, payload in rec["support_data"].items():
            if isinstance(payload, dict):
                val = payload.get("total", payload.get("support", 0))
            else:
                val = payload
            try:
                out[str(pid)] = float(val)
            except Exception:
                continue
        return out

    # discover outputs
    for key in ("top_support", "topk_support"):
        arr = rec.get(key)
        if isinstance(arr, list):
            out: Dict[str, float] = {}
            for row in arr:
                if not isinstance(row, dict):
                    continue
                pid = row.get("r2")
                if not isinstance(pid, str) or not pid:
                    continue
                try:
                    out[pid] = float(row.get("support", 0))
                except Exception:
                    continue
            return out

    return None


def compare_support(base_map: Dict[str, float] | None, rerun_map: Dict[str, float] | None) -> Dict[str, Any]:
    if base_map is None or rerun_map is None:
        return {
            "comparable": False,
            "reason": "missing_support_map",
        }

    base_keys = set(base_map.keys())
    rerun_keys = set(rerun_map.keys())
    shared = base_keys.intersection(rerun_keys)
    union = base_keys.union(rerun_keys)

    max_abs_delta = 0.0
    sum_abs_delta = 0.0
    for pid in shared:
        d = abs(base_map[pid] - rerun_map[pid])
        sum_abs_delta += d
        if d > max_abs_delta:
            max_abs_delta = d

    mean_abs_delta = (sum_abs_delta / len(shared)) if shared else None
    exact = base_map == rerun_map
    same_keys = base_keys == rerun_keys

    return {
        "comparable": True,
        "base_keys": len(base_keys),
        "rerun_keys": len(rerun_keys),
        "shared_keys": len(shared),
        "union_keys": len(union),
        "same_keys": same_keys,
        "exact_match": exact,
        "max_abs_delta_shared": max_abs_delta,
        "mean_abs_delta_shared": mean_abs_delta,
        "jaccard_keys": (len(shared) / len(union)) if union else 1.0,
        "near_match_delta_le_1": bool(shared) and max_abs_delta <= 1.0,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare hop_support rerun statuses against original by r1")
    ap.add_argument("--base", required=True, help="Original hop_support JSONL")
    ap.add_argument("--rerun", required=True, help="Rerun hop_support JSONL (left side)")
    ap.add_argument("--out_joined", required=True, help="Output JSONL for joined comparison")
    ap.add_argument("--out_summary", required=True, help="Output JSON for summary statistics")
    ap.add_argument("--out_patched_base",default=None,help="If set: write a patched copy of base where ERROR->SUCCESS rows are replaced by rerun records")

    args = ap.parse_args()

    base = load_jsonl_latest(args.base)
    rerun = load_jsonl_latest(args.rerun)

    transitions: Counter[Tuple[str, str]] = Counter()
    base_status_counts: Counter[str] = Counter()
    rerun_status_counts: Counter[str] = Counter()

    improved = 0
    regressed = 0
    unchanged = 0
    matched = 0
    missing_in_base = 0

    identical_except_volatile = 0

    error_both_present = 0
    error_same = 0
    error_changed = 0
    error_resolved = 0
    error_new = 0

    support_comparable = 0
    support_exact = 0
    support_same_keys = 0
    support_near = 0
    
    patched_f = open(args.out_patched_base, "w", encoding="utf-8") if args.out_patched_base else None
    try:

        with open(args.out_joined, "w", encoding="utf-8") as out:
            for r1 in rerun.order:
                rerun_rec = rerun.latest_by_r1[r1]
                base_rec = base.latest_by_r1.get(r1)

                old_status = status_of(base_rec)
                new_status = status_of(rerun_rec)

                transitions[(old_status, new_status)] += 1
                base_status_counts[old_status] += 1
                rerun_status_counts[new_status] += 1

                if base_rec is None:
                    missing_in_base += 1
                else:
                    matched += 1

                if old_status == new_status:
                    unchanged += 1
                elif old_status != "SUCCESS" and new_status == "SUCCESS":
                    improved += 1
                elif old_status == "SUCCESS" and new_status != "SUCCESS":
                    regressed += 1

                norm_base = normalize_record(base_rec)
                norm_rerun = normalize_record(rerun_rec)
                same_nonvolatile = (norm_base == norm_rerun)
                if same_nonvolatile:
                    identical_except_volatile += 1

                old_error = error_str(base_rec)
                new_error = error_str(rerun_rec)
                old_has_error = bool(old_error)
                new_has_error = bool(new_error)

                if old_has_error and new_has_error:
                    error_both_present += 1
                    if old_error == new_error:
                        error_same += 1
                    else:
                        error_changed += 1
                elif old_has_error and not new_has_error:
                    error_resolved += 1
                elif not old_has_error and new_has_error:
                    error_new += 1

                support_cmp = compare_support(extract_support_map(base_rec), extract_support_map(rerun_rec))
                if support_cmp.get("comparable"):
                    support_comparable += 1
                    if support_cmp.get("exact_match"):
                        support_exact += 1
                    if support_cmp.get("same_keys"):
                        support_same_keys += 1
                    if support_cmp.get("near_match_delta_le_1"):
                        support_near += 1

                joined = {
                    "r1": r1,
                    "original_status": old_status,
                    "rerun_status": new_status,
                    "status_changed": old_status != new_status,
                    "original_mode": (base_rec or {}).get("mode"),
                    "rerun_mode": rerun_rec.get("mode"),
                    "original_error": old_error,
                    "rerun_error": new_error,
                    "error_changed": old_error != new_error,
                    "same_except_volatile_fields": same_nonvolatile,
                    "support_comparison": support_cmp,
                }
                out.write(json.dumps(joined, ensure_ascii=False) + "\n")

        # Write patched base: iterate base, replace where rerun fixed ERROR->SUCCESS for same r1
        if patched_f:
            for r1 in base.order:
                base_rec = base.latest_by_r1[r1]
                rerun_rec = rerun.latest_by_r1.get(r1)

                if rerun_rec is not None and status_of(base_rec) != "SUCCESS" and status_of(rerun_rec) == "SUCCESS":
                    patched_f.write(json.dumps(rerun_rec, ensure_ascii=False) + "\n")
                else:
                    patched_f.write(json.dumps(base_rec, ensure_ascii=False) + "\n")

    finally:
        if patched_f:
            patched_f.close()

    summary = {
        "inputs": {
            "base": args.base,
            "rerun": args.rerun,
        },
        "loader_stats": {
            "base": {
                "total_lines": base.total_lines,
                "valid_records": base.valid_records,
                "unique_r1": len(base.latest_by_r1),
                "duplicate_r1_overwrites": base.duplicate_r1_overwrites,
            },
            "rerun": {
                "total_lines": rerun.total_lines,
                "valid_records": rerun.valid_records,
                "unique_r1": len(rerun.latest_by_r1),
                "duplicate_r1_overwrites": rerun.duplicate_r1_overwrites,
            },
        },
        "left_join_stats": {
            "total_rerun_r1": len(rerun.latest_by_r1),
            "matched_in_base": matched,
            "missing_in_base": missing_in_base,
        },
        "status_comparison": {
            "improved_to_success": improved,
            "regressed_from_success": regressed,
            "unchanged_status": unchanged,
            "changed_status": len(rerun.latest_by_r1) - unchanged,
        },
        "record_similarity": {
            "identical_except_volatile_fields": identical_except_volatile,
            "different_nonvolatile_fields": len(rerun.latest_by_r1) - identical_except_volatile,
            "ignored_fields": sorted(VOLATILE_FIELDS),
        },
        "error_comparison": {
            "both_have_error": error_both_present,
            "same_error_message": error_same,
            "changed_error_message": error_changed,
            "error_resolved": error_resolved,
            "new_error_introduced": error_new,
        },
        "support_similarity": {
            "comparable_rows": support_comparable,
            "exact_match_rows": support_exact,
            "same_keyset_rows": support_same_keys,
            "near_match_rows_delta_le_1": support_near,
        },
        "status_counts_on_joined_set": {
            "original": dict(base_status_counts),
            "rerun": dict(rerun_status_counts),
        },
        "transitions": {
            f"{old}=>{new}": count for (old, new), count in sorted(transitions.items())
        },
        "outputs": {
            "joined": args.out_joined,
            "summary": args.out_summary,
            "patched_base": args.out_patched_base,
        },
    }

    with open(args.out_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("Comparison complete")
    print(f"rerun unique r1: {len(rerun.latest_by_r1)}")
    print(f"matched in base: {matched}")
    print(f"missing in base: {missing_in_base}")
    print(f"improved_to_success: {improved}")
    print(f"regressed_from_success: {regressed}")
    print(f"same_error_message: {error_same}")
    print(f"changed_error_message: {error_changed}")
    print(f"identical_except_volatile_fields: {identical_except_volatile}")
    print(f"joined output: {args.out_joined}")
    print(f"summary output: {args.out_summary}")


if __name__ == "__main__":
    main()
    # python src/enrichments_and_filters/compare_hop_support_statuses.py --base data/processed/hop_support.jsonl --rerun data/archived/hop_support_failed_rerun.jsonl --out_joined data/processed/hop_support_rerun_joined.jsonl --out_summary data/processed/hop_support_rerun_joined_summary.json

