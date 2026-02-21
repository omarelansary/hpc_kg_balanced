# enrich_pairs_with_targets.py
#
# Goal:
# For each candidate pair (r1, r2) extracted from a pairs JSONL file,
# find all target relations t such that:
#   Dom(t) ∩ Dom(r1) != ∅     AND     Rng(t) ∩ Rng(r2) != ∅
#
# All inputs/outputs are JSONL files (one JSON object per line).
#
# Semantics for "ANY":
# - Treat "ANY" as "unknown / could be anything" → intersection check always PASSES.
# - Missing property in constraints file is treated as unknown (passes).
# - Each match records explicit reason labels so you know which side was ANY.
#
# Restart safety:
# - Checkpoint file stores the last processed line number.
# - Output appends, so partial runs can resume.
#
# Usage example:
# python enrich_pairs_with_targets.py \
#   --pairs_file pairs.jsonl \
#   --targets_file relation_profiles.jsonl \
#   --properties_file properties.jsonl \
#   --out_file pairs_with_compatible_targets.jsonl

import argparse
import json
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

ANY = "ANY"


def to_constraint_set(values: Optional[List[str]]) -> Optional[Set[str]]:
    """
    Returns:
      - None if unknown ("ANY" present, empty, missing)
      - set of QIDs otherwise
    """
    if not values:
        return None
    if ANY in values:
        return None
    return set(values)


def intersects_with_reason(
    a: Optional[Set[str]], b: Optional[Set[str]], a_label: str, b_label: str
) -> Tuple[bool, str]:
    """
    Intersection test with ANY/unknown pass-through.
    Returns (passed, reason).
    Reason is one of:
      "INTERSECT"                    – both known, non-empty intersection
      "ANY_{a_label}"                – a is unknown
      "ANY_{b_label}"                – b is unknown
      "ANY_{a_label}_AND_{b_label}"  – both unknown
      "EMPTY"                        – both known, empty intersection (failed)
    """
    if a is None and b is None:
        return True, f"ANY_{a_label}_AND_{b_label}"
    if a is None:
        return True, f"ANY_{a_label}"
    if b is None:
        return True, f"ANY_{b_label}"
    if a.intersection(b):
        return True, "INTERSECT"
    return False, "EMPTY"


def load_jsonl(filepath: str) -> List[Dict[str, Any]]:
    """Load records from JSONL or JSON array/object files."""
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read().strip()

    if not text:
        return []

    # Try whole-file JSON first (array/object). If that fails, treat as JSONL.
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        records: List[Dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        return records

    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    raise ValueError(f"Unsupported JSON root type in {filepath}: {type(parsed).__name__}")


def load_target_property_ids(targets_file: str) -> List[str]:
    """
    Load target relations where composition_target != 'NO_WAY'.
    """
    records = load_jsonl(targets_file)
    targets = set()
    for d in records:
        comp = (d.get("llm_classification") or {}).get("composition") or {}
        if comp.get("composition_target") != "NO_WAY":
            pid = d.get("property_id")
            if pid:
                targets.add(pid)
    return sorted(targets)


def load_constraints(properties_file: str, pids: List[str]) -> Dict[str, Tuple[Optional[Set[str]], Optional[Set[str]]]]:
    """
    Returns map:
      constraints[pid] = (dom_set_or_None, rng_set_or_None)
    Missing pid => (None, None) i.e., unknown.
    """
    needed = set(pids)
    records = load_jsonl(properties_file)
    out: Dict[str, Tuple[Optional[Set[str]], Optional[Set[str]]]] = {}
    for d in records:
        pid = d.get("property_id")
        if pid and pid in needed:
            dom = to_constraint_set(d.get("valid_subject_type_ids"))
            rng = to_constraint_set(d.get("valid_object_type_ids"))
            out[pid] = (dom, rng)

    # fill missing as unknown
    for pid in pids:
        if pid not in out:
            out[pid] = (None, None)
    return out


def extract_pairs_from_doc(doc: Dict[str, Any]) -> List[Tuple[str, str, int]]:
    """
    Supports:
      - old format: topk_support / top_support lists of {"r2":..., "support":...}
      - new format: support_data dict: {r2: {"total":..., ...}, ...}
    Returns (r1, r2, support_total).
    """
    r1 = doc["r1"]
    seen: Set[str] = set()
    pairs: List[Tuple[str, str, int]] = []

    # New format
    sd = doc.get("support_data")
    if isinstance(sd, dict):
        for r2, stats in sd.items():
            if not r2 or r2 in seen:
                continue
            support = 0
            if isinstance(stats, dict):
                # prefer "total" if present
                support = int(stats.get("total", 0) or 0)
            pairs.append((r1, r2, support))
            seen.add(r2)
        return pairs

    # Old formats
    for entry in doc.get("topk_support", []):
        r2 = entry.get("r2")
        if r2 and r2 not in seen:
            pairs.append((r1, r2, int(entry.get("support", 0) or 0)))
            seen.add(r2)

    for entry in doc.get("top_support", []):
        r2 = entry.get("r2")
        if r2 and r2 not in seen:
            pairs.append((r1, r2, int(entry.get("support", 0) or 0)))
            seen.add(r2)

    return pairs


def get_checkpoint(checkpoint_file: str) -> int:
    """Returns the last processed line number (0-based), or -1 if no checkpoint."""
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, "r") as f:
            data = json.load(f)
            return data.get("last_line", -1)
    return -1


def set_checkpoint(checkpoint_file: str, last_line: int, extra: Optional[Dict[str, Any]] = None) -> None:
    payload: Dict[str, Any] = {"last_line": last_line, "updated_at": time.time()}
    if extra:
        payload.update(extra)
    with open(checkpoint_file, "w") as f:
        json.dump(payload, f)


def main():
    parser = argparse.ArgumentParser(description="Enrich (r1,r2) pairs with compatible composition targets (ANY passes). File-based version.")
    parser.add_argument("--pairs_file", required=True, help="JSONL file with r1 docs containing nested r2 support arrays.")
    parser.add_argument("--targets_file", required=True, help="JSONL file with LLM relation profiles (composition_target != NO_WAY).")
    parser.add_argument("--properties_file", required=True, help="JSONL file with property constraints (valid_subject/object_type_ids).")

    parser.add_argument("--out_file", default="pairs_with_compatible_targets.jsonl", help="Output JSONL file.")
    parser.add_argument("--checkpoint_file", default=".enrich_checkpoint.json", help="Checkpoint file for resume.")

    parser.add_argument("--min_support", type=int, default=0,
                        help="Skip (r1,r2) pairs with support below this threshold.")

    parser.add_argument("--store_targets", action="store_true",
                        help="Store the list of matching targets in addition to target_count.")
    parser.add_argument("--targets_cap", type=int, default=0,
                        help="If store_targets, optionally cap stored targets to first K (0 = store all).")

    parser.add_argument("--modes", nargs="+",
                        default=["discover_topk", "values_chunked"],
                        help="Which pair-discovery modes to process.")

    parser.add_argument("--input_statuses", nargs="+",
                        default=["SUCCESS", "ERROR", "NOT_FOUND"],
                        help="Which input_status values to include. Default: all. "
                             "Use '--input_statuses SUCCESS' to only process docs where r1 constraints were found.")

    parser.add_argument("--checkpoint_every", type=int, default=500,
                        help="Write checkpoint every N input docs.")

    args = parser.parse_args()

    # 1) Load targets
    print(f"Loading targets from {args.targets_file}...")
    targets = load_target_property_ids(args.targets_file)
    print(f"Loaded {len(targets)} target relations.")
    if not targets:
        print("[WARN] No targets found; nothing to process.")
        return

    # 2) Load pairs and scan for all r1/r2 pids needed for constraints
    print(f"Loading pairs from {args.pairs_file}...")
    pairs_data = load_jsonl(args.pairs_file)
    print(f"Loaded {len(pairs_data)} docs from pairs file.")

    all_r1: Set[str] = set()
    all_r2: Set[str] = set()
    for doc in pairs_data:
        if doc.get("status") != "SUCCESS":
            continue
        if doc.get("mode") not in args.modes:
            continue
        if doc.get("input_status", "UNKNOWN") not in args.input_statuses:
            continue
        all_r1.add(doc["r1"])

        sd = doc.get("support_data")
        if isinstance(sd, dict):
            for r2 in sd.keys():
                all_r2.add(r2)
        else:
            for entry in doc.get("topk_support", []):
                if entry.get("r2"):
                    all_r2.add(entry["r2"])
            for entry in doc.get("top_support", []):
                if entry.get("r2"):
                    all_r2.add(entry["r2"])

    needed_pids = sorted(set(targets).union(all_r1).union(all_r2))

    # 3) Load constraints
    print(f"Loading constraints for {len(needed_pids)} relations from {args.properties_file}...")
    constraints = load_constraints(args.properties_file, needed_pids)

    # Pre-materialize target constraints list for fast loop
    target_constraints: List[Tuple[str, Optional[Set[str]], Optional[Set[str]]]] = []
    for t in targets:
        dom_t, rng_t = constraints[t]
        target_constraints.append((t, dom_t, rng_t))

    # 4) Resume support
    resume_after = get_checkpoint(args.checkpoint_file)
    if resume_after >= 0:
        print(f"Resuming after line {resume_after}")

    # Open output in append mode (safe for resume)
    out_f = open(args.out_file, "a", encoding="utf-8")

    processed_docs = 0
    processed_pairs = 0
    t0 = time.time()

    try:
        for line_idx, doc in enumerate(pairs_data):
            # Skip already-processed lines on resume
            if line_idx <= resume_after:
                continue

            # Filter
            if doc.get("status") != "SUCCESS":
                continue
            if doc.get("mode") not in args.modes:
                continue
            if doc.get("input_status", "UNKNOWN") not in args.input_statuses:
                continue

            source_mode = doc.get("mode")
            input_status = doc.get("input_status", "UNKNOWN")
            pairs_in_doc = extract_pairs_from_doc(doc)

            for r1, r2, support in pairs_in_doc:
                if support < args.min_support:
                    continue

                dom_r1, _rng_r1_unused = constraints.get(r1, (None, None))
                _dom_r2_unused, rng_r2 = constraints.get(r2, (None, None))

                matching: List[Dict[str, str]] = []
                match_count = 0

                for t, dom_t, rng_t in target_constraints:
                    dom_pass, dom_reason = intersects_with_reason(dom_t, dom_r1, "DOM_T", "DOM_R1")
                    rng_pass, rng_reason = intersects_with_reason(rng_t, rng_r2, "RNG_T", "RNG_R2")
                    if dom_pass and rng_pass:
                        match_count += 1
                        if args.store_targets:
                            matching.append({
                                "t": t,
                                "dom_reason": dom_reason,
                                "rng_reason": rng_reason,
                            })

                if args.store_targets and args.targets_cap and len(matching) > args.targets_cap:
                    matching = matching[: args.targets_cap]

                out_doc: Dict[str, Any] = {
                    "r1": r1,
                    "r2": r2,
                    "support": support,
                    "source_mode": source_mode,
                    "input_status": input_status,
                    "target_count": match_count,
                    "targets_truncated": bool(args.store_targets and args.targets_cap and match_count > len(matching)),
                }
                if args.store_targets:
                    out_doc["targets"] = matching

                out_f.write(json.dumps(out_doc) + "\n")
                processed_pairs += 1

            processed_docs += 1

            # Checkpoint
            if processed_docs % args.checkpoint_every == 0:
                out_f.flush()
                elapsed = time.time() - t0
                rate = processed_pairs / elapsed if elapsed > 0 else 0.0
                set_checkpoint(args.checkpoint_file, line_idx, extra={
                    "processed_docs": processed_docs,
                    "processed_pairs": processed_pairs,
                    "rate_pairs_per_sec": rate,
                })
                print(f"Docs={processed_docs} | Pairs={processed_pairs} | rate={rate:.2f} pairs/s | line={line_idx}")

    finally:
        out_f.flush()
        out_f.close()

    # Final checkpoint
    elapsed = time.time() - t0
    rate = processed_pairs / elapsed if elapsed > 0 else 0.0
    set_checkpoint(args.checkpoint_file, len(pairs_data) - 1, extra={
        "done": True,
        "processed_docs": processed_docs,
        "processed_pairs": processed_pairs,
        "rate": rate,
    })

    print(f"Done. Docs={processed_docs}, Pairs={processed_pairs}. Output={args.out_file}")


if __name__ == "__main__":
    main()
    # we may also remove --store_targets to not store the full list of targets 
    # python src/enrichments_and_filters/enrich_pairs_with_targets_dom_rng_based.py --pairs_file data/processed/hop_support_v2_w_failed_statuses.wikibase_item_only_w_target_enrichment.jsonl --targets_file data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json --properties_file data/raw/wikidata_ontology.properties.json --out_file data/processed/pairs_with_compatible_targets_dom_rng_v1.jsonl --checkpoint_file data/processed/enrich_pairs_dom_rng.checkpoint_v1.json --min_support 0 --modes values_chunked_v2 discover_topk_v2 --input_statuses SUCCESS ERROR NOT_FOUND --checkpoint_every 1 --store_targets
