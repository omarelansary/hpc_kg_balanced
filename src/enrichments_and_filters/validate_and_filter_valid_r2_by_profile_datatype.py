#!/usr/bin/env python3
"""Check whether valid_r2 relations in hop_support exist in relation profiles
and whether each relation has metadata.datatype == wikibase-item.

Supports JSONL or JSON array/object input for relation profiles.
Supports JSONL input for hop_support.
"""

from __future__ import annotations

import argparse
import json
import copy
from collections import Counter
from typing import Any, Dict, Iterable, List, Set


def load_json_or_jsonl(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()

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
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, dict):
            out.append(obj)
    return out


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                out.append(obj)
    return out


def normalize_datatype(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip().lower()
    if not v:
        return None
    return v


def build_profile_index(records: Iterable[Dict[str, Any]]) -> Dict[str, str | None]:
    idx: Dict[str, str | None] = {}
    for rec in records:
        pid = rec.get("property_id")
        if not isinstance(pid, str) or not pid:
            continue
        datatype = normalize_datatype((rec.get("metadata") or {}).get("datatype"))
        idx[pid] = datatype
    return idx


def extract_valid_r2(doc: Dict[str, Any]) -> Set[str]:
    vals = doc.get("valid_r2")
    if isinstance(vals, list):
        return {x for x in vals if isinstance(x, str) and x}

    by_r2 = doc.get("support_by_r2")
    if isinstance(by_r2, dict):
        return {k for k in by_r2.keys() if isinstance(k, str) and k}

    sd = doc.get("support_data")
    if isinstance(sd, dict):
        return {k for k in sd.keys() if isinstance(k, str) and k}

    out: Set[str] = set()
    for key in ("top_support", "topk_support"):
        arr = doc.get(key)
        if not isinstance(arr, list):
            continue
        for row in arr:
            if not isinstance(row, dict):
                continue
            pid = row.get("r2")
            if isinstance(pid, str) and pid:
                out.add(pid)
    return out


def filter_r2_entries(rec: Dict[str, Any], allowed_r2: Set[str]) -> Dict[str, Any]:
    """
    Return a copy of rec with r2-bearing fields filtered to allowed_r2.
    This keeps output parseable and internally consistent for downstream tools.
    """
    out = copy.deepcopy(rec)

    if isinstance(out.get("valid_r2"), list):
        out["valid_r2"] = sorted([x for x in out["valid_r2"] if isinstance(x, str) and x in allowed_r2])
        out["valid_r2_count"] = len(out["valid_r2"])

    if isinstance(out.get("support_by_r2"), dict):
        out["support_by_r2"] = {k: v for k, v in out["support_by_r2"].items() if isinstance(k, str) and k in allowed_r2}

    if isinstance(out.get("support_data"), dict):
        out["support_data"] = {k: v for k, v in out["support_data"].items() if isinstance(k, str) and k in allowed_r2}
    

    for key in ("top_support", "topk_support"):
        if isinstance(out.get(key), list):
            kept: List[Dict[str, Any]] = []
            for row in out[key]:
                if not isinstance(row, dict):
                    continue
                pid = row.get("r2")
                if isinstance(pid, str) and pid in allowed_r2:
                    kept.append(row)
            out[key] = kept

    if isinstance(out.get("failed_r2"), list):
        out["failed_r2"] = sorted([x for x in out["failed_r2"] if isinstance(x, str) and x in allowed_r2])

    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate hop_support valid_r2 against relation profiles datatype")
    ap.add_argument("--hop_support", required=True, help="Path to hop_support JSONL")
    ap.add_argument("--relation_profiles", required=True, help="Path to relation profiles (JSON/JSONL)")
    ap.add_argument("--out_details", required=True, help="Output JSONL with per-r1 details")
    ap.add_argument("--out_summary", required=True, help="Output JSON summary")
    ap.add_argument("--write_filtered", action="store_true", help="Write filtered hop_support JSONL keeping only wikibase-item r2")
    ap.add_argument("--out_filtered", default="hop_support.filtered_wikibase_item.jsonl", help="Output JSONL path for filtered records")
    args = ap.parse_args()

    hop_records = load_jsonl(args.hop_support)
    profile_records = load_json_or_jsonl(args.relation_profiles)
    profile_idx = build_profile_index(profile_records)
    allowed_wikibase_item_r2: Set[str] = {pid for pid, dt in profile_idx.items() if dt == "wikibase-item"}

    hop_latest: Dict[str, Dict[str, Any]] = {}
    hop_order: List[str] = []
    seen_r1: Set[str] = set()
    for rec in hop_records:
        r1 = rec.get("r1")
        if not isinstance(r1, str) or not r1:
            continue
        if r1 not in seen_r1:
            seen_r1.add(r1)
            hop_order.append(r1)
        hop_latest[r1] = rec

    global_counts = Counter()
    datatype_counter = Counter()

    unique_valid_r2: Set[str] = set()
    unique_in_profile: Set[str] = set()
    unique_missing_profile: Set[str] = set()
    unique_wikibase_item: Set[str] = set()
    unique_non_wikibase_item: Set[str] = set()
    unique_unknown_datatype: Set[str] = set()
    unique_not_wikibase_time_quantity: Set[str] = set()

    r1_with_missing_profile: Set[str] = set()
    filtered_stats = Counter()

    filtered_out = open(args.out_filtered, "w", encoding="utf-8") if args.write_filtered else None
    with open(args.out_details, "w", encoding="utf-8") as out:
        for r1 in hop_order:
            rec = hop_latest[r1]
            final_status = rec.get("status")
            is_success = isinstance(final_status, str) and final_status == "SUCCESS"

            if is_success:
                valid_r2 = sorted(extract_valid_r2(rec))
            else:
                valid_r2 = []

            in_profile: List[str] = []
            missing_profile: List[str] = []
            wikibase_item: List[str] = []
            not_wikibase_item: List[Dict[str, str | None]] = []
            unknown_datatype: List[str] = []

            for r2 in valid_r2:
                unique_valid_r2.add(r2)

                if r2 not in profile_idx:
                    missing_profile.append(r2)
                    unique_missing_profile.add(r2)
                    continue

                in_profile.append(r2)
                unique_in_profile.add(r2)

                dt = profile_idx[r2]
                if dt is None:
                    unknown_datatype.append(r2)
                    unique_unknown_datatype.add(r2)
                    datatype_counter["UNKNOWN"] += 1
                elif dt == "wikibase-item":
                    wikibase_item.append(r2)
                    unique_wikibase_item.add(r2)
                    datatype_counter["wikibase-item"] += 1
                else:
                    not_wikibase_item.append({"r2": r2, "datatype": dt})
                    unique_non_wikibase_item.add(r2)
                    datatype_counter[dt] += 1
                    if dt not in {"wikibase-item", "time", "quantity"}:
                        unique_not_wikibase_time_quantity.add(r2)

            row = {
                "r1": r1,
                "input_status": rec.get("input_status"),
                "status": rec.get("status"),
                "mode": rec.get("mode"),
                "valid_r2_total": len(valid_r2),
                "in_relation_profile_count": len(in_profile),
                "missing_in_relation_profile_count": len(missing_profile),
                "wikibase_item_count": len(wikibase_item),
                "non_wikibase_item_count": len(not_wikibase_item),
                "unknown_datatype_count": len(unknown_datatype),
                "missing_in_relation_profile": missing_profile,
                "non_wikibase_item": not_wikibase_item,
                "unknown_datatype": unknown_datatype,
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            
            if filtered_out is not None:
                if is_success:
                    filtered_rec = filter_r2_entries(rec, allowed_wikibase_item_r2)
                    filtered_valid_r2 = sorted(extract_valid_r2(filtered_rec))
                    removed = max(0, len(valid_r2) - len(filtered_valid_r2))

                    filtered_stats["rows_written"] += 1
                    filtered_stats["valid_r2_before_total"] += len(valid_r2)
                    filtered_stats["valid_r2_after_total"] += len(filtered_valid_r2)
                    filtered_stats["valid_r2_removed_total"] += removed
                    if removed > 0:
                        filtered_stats["rows_with_removals"] += 1

                    filtered_out.write(json.dumps(filtered_rec, ensure_ascii=False) + "\n")
                else:
                    # keep ERROR/NOT_FOUND/etc rows unchanged in filtered output
                    filtered_stats["rows_written"] += 1
                    filtered_stats["rows_non_success_written"] += 1
                    filtered_out.write(json.dumps(rec, ensure_ascii=False) + "\n")


            global_counts["r1_rows"] += 1
            global_counts["valid_r2_total"] += len(valid_r2)
            global_counts["in_profile_total"] += len(in_profile)
            global_counts["missing_in_profile_total"] += len(missing_profile)
            global_counts["wikibase_item_total"] += len(wikibase_item)
            global_counts["non_wikibase_item_total"] += len(not_wikibase_item)
            global_counts["unknown_datatype_total"] += len(unknown_datatype)
            if missing_profile:
                global_counts["r1_with_missing_profile"] += 1
                r1_with_missing_profile.add(r1)
            if not_wikibase_item:
                global_counts["r1_with_non_wikibase_item"] += 1
    if filtered_out is not None:
        filtered_out.close()

    summary = {
        "inputs": {
            "hop_support": args.hop_support,
            "relation_profiles": args.relation_profiles,
        },
        "row_counts": {
            "hop_support_rows_raw": len(hop_records),
            "hop_support_rows_unique_r1": len(hop_order),
            "relation_profile_rows": len(profile_records),
            "relation_profile_unique_property_id": len(profile_idx),
        },
        "pair_level_totals": dict(global_counts),
        "unique_r2_totals": {
            "unique_valid_r2": len(unique_valid_r2),
            "unique_in_profile": len(unique_in_profile),
            "unique_missing_in_profile": len(unique_missing_profile),
            "unique_wikibase_item": len(unique_wikibase_item),
            "unique_non_wikibase_item": len(unique_non_wikibase_item),
            "unique_unknown_datatype": len(unique_unknown_datatype),
            "unique_not_wikibase_time_quantity": len(unique_not_wikibase_time_quantity),
        },
        "requested_lists": {
            "r1_with_r2_missing_in_relation_profile": sorted(r1_with_missing_profile),
            "r2_missing_in_relation_profile": sorted(unique_missing_profile),
            "r2_non_wikibase_item": sorted(unique_non_wikibase_item),
            "r2_not_wikibase_time_quantity": sorted(unique_not_wikibase_time_quantity),
        },
        "datatype_distribution_in_profile_r2": dict(datatype_counter),
        "outputs": {
            "details": args.out_details,
            "summary": args.out_summary,
            "filtered": args.out_filtered if args.write_filtered else None,
        },
    }
    if args.write_filtered:
        summary["filtered_mode"] = {
            "enabled": True,
            "allowed_wikibase_item_r2": len(allowed_wikibase_item_r2),
            "rows_written": filtered_stats["rows_written"],
            "rows_with_removals": filtered_stats["rows_with_removals"],
            "valid_r2_before_total": filtered_stats["valid_r2_before_total"],
            "valid_r2_after_total": filtered_stats["valid_r2_after_total"],
            "valid_r2_removed_total": filtered_stats["valid_r2_removed_total"],
        }
    else:
        summary["filtered_mode"] = {"enabled": False}

    with open(args.out_summary, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("check_complete")
    print(f"unique_r1_checked: {len(hop_order)}")
    print(f"valid_r2_total_pair_level: {global_counts['valid_r2_total']}")
    print(f"valid_r2_total_unique: {len(unique_valid_r2)}")
    print(f"missing_in_profile_total_pair_level: {global_counts['missing_in_profile_total']}")
    print(f"missing_in_profile_total_unique: {len(unique_missing_profile)}")
    print(f"non_wikibase_item_total_pair_level: {global_counts['non_wikibase_item_total']}")
    print(f"non_wikibase_item_total_unique: {len(unique_non_wikibase_item)}")
    print(f"not_wikibase_time_quantity_total_unique: {len(unique_not_wikibase_time_quantity)}")
    print(f"r1_with_missing_profile_unique: {len(r1_with_missing_profile)}")
    if args.write_filtered:
        print(f"filtered_rows_written: {filtered_stats['rows_written']}")
        print(f"filtered_valid_r2_removed_total: {filtered_stats['valid_r2_removed_total']}")
        print(f"filtered_output: {args.out_filtered}")
    print(f"details: {args.out_details}")
    print(f"summary: {args.out_summary}")


if __name__ == "__main__":
    main()
    # python src/enrichments_and_filters/check_valid_r2_profile_datatype.py --hop_support data/processed/hop_support.jsonl --relation_profiles data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json --out_details data/processed/hop_support_valid_r2_profile_check.jsonl --out_summary data/processed/hop_support_valid_r2_profile_check_summary.json
    # or with manual r2 filtering:
    # python src/enrichments_and_filters/validate_and_filter_valid_r2_by_profile_datatype.py --hop_support data/processed/hop_support.jsonl --relation_profiles data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json --out_details data/processed/hop_support_valid_r2_profile_check.jsonl --out_summary data/processed/hop_support_valid_r2_profile_check_summary.json --write_filtered --out_filtered data/processed/hop_support.wikibase_item_only.jsonl