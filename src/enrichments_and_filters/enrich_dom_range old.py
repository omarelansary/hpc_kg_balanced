# enrich_pairs_with_targets.py
#
# Goal:
# For each candidate pair (r1, r2) in an existing pairs collection (INTERSECT or ANY_*),
# find all target relations t (615) such that:
#   Dom(t) ∩ Dom(r1) != ∅     AND     Rng(t) ∩ Rng(r2) != ∅
#
# Semantics for "ANY":
# - Treat "ANY" as "unknown / could be anything" → intersection check always PASSES.
# - Missing constraints doc in `properties` is treated as unknown (passes).
#
# Restart safety:
# - Uses a checkpoint in meta collection storing the last processed _id from the pairs collection.
# - Output writes are idempotent via unique (r1,r2) index + upsert.
#
# Usage example:
# python enrich_pairs_with_targets.py --mongo_uri "mongodb://localhost:27017/" --db wikidata_ontology \
#   --pairs_col relations_range_domain_intersection --targets_col relation_profiles_afterLLM_SecondTime \
#   --properties_col properties --out_col pairs_with_compatible_targets

import argparse
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from bson import ObjectId
from pymongo import MongoClient, UpdateOne, ASCENDING
from pymongo.errors import BulkWriteError

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


def intersects_unknown_pass(a: Optional[Set[str]], b: Optional[Set[str]]) -> bool:
    """
    Intersection test with ANY/unknown pass-through:
      - If either side unknown -> PASS (True)
      - Else -> PASS iff intersection non-empty
    """
    if a is None or b is None:
        return True
    return len(a.intersection(b)) > 0


def ensure_indexes(out_col):
    out_col.create_index([("r1", ASCENDING), ("r2", ASCENDING)], unique=True)
    out_col.create_index([("target_count", ASCENDING)])
    out_col.create_index([("updated_at", ASCENDING)])


def get_checkpoint(meta_col, checkpoint_id: str) -> Optional[Any]:
    doc = meta_col.find_one({"_id": checkpoint_id}, {"last_pairs_id": 1})
    return doc.get("last_pairs_id") if doc else None


def set_checkpoint(meta_col, checkpoint_id: str, last_pairs_id: Any, extra: Optional[Dict[str, Any]] = None) -> None:
    payload: Dict[str, Any] = {"last_pairs_id": last_pairs_id, "updated_at": time.time()}
    if extra:
        payload.update(extra)
    meta_col.update_one({"_id": checkpoint_id}, {"$set": payload}, upsert=True)


def normalize_checkpoint_id(value: Any) -> Optional[Any]:
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    if isinstance(value, str):
        value = value.strip()
        if len(value) == 24:
            try:
                return ObjectId(value)
            except Exception:
                return None
    return value


def load_target_property_ids(targets_col) -> List[str]:
    """
    Load the 615 target relations from relation_profiles_afterLLM_SecondTime:
      {'llm_classification.composition.composition_target': {$ne:'NO_WAY'}}
    """
    cursor = targets_col.find(
        {"llm_classification.composition.composition_target": {"$ne": "NO_WAY"}},
        {"_id": 0, "property_id": 1},
    )
    targets = sorted({d["property_id"] for d in cursor if d.get("property_id")})
    return targets


def load_constraints(props_col, pids: List[str]) -> Dict[str, Tuple[Optional[Set[str]], Optional[Set[str]]]]:
    """
    Returns map:
      constraints[pid] = (dom_set_or_None, rng_set_or_None)
    Missing pid in properties => (None,None) i.e., unknown.
    """
    if not pids:
        return {}

    cursor = props_col.find(
        {"property_id": {"$in": pids}},
        {"_id": 0, "property_id": 1, "valid_subject_type_ids": 1, "valid_object_type_ids": 1},
    )
    out: Dict[str, Tuple[Optional[Set[str]], Optional[Set[str]]]] = {}
    for d in cursor:
        pid = d["property_id"]
        dom = to_constraint_set(d.get("valid_subject_type_ids"))
        rng = to_constraint_set(d.get("valid_object_type_ids"))
        out[pid] = (dom, rng)

    # fill missing as unknown
    for pid in pids:
        if pid not in out:
            out[pid] = (None, None)
    return out


def main():
    parser = argparse.ArgumentParser(description="Enrich (r1,r2) pairs with compatible composition targets (ANY passes).")
    parser.add_argument("--mongo_uri", default=os.getenv("MONGO_URI", "mongodb://localhost:27017/"))
    parser.add_argument("--db", default="wikidata_ontology")

    parser.add_argument("--pairs_col", required=True, help="Collection containing (r1,r2) pairs + compatibility labels.")
    parser.add_argument("--targets_col", default="relation_profiles_afterLLM_SecondTime",
                        help="Collection containing LLM output with composition_target != NO_WAY.")
    parser.add_argument("--properties_col", default="properties")

    parser.add_argument("--out_col", default="pairs_with_compatible_targets")
    parser.add_argument("--meta_col", default="_meta")
    parser.add_argument("--checkpoint_id", default="pairs_targets_checkpoint")

    parser.add_argument("--batch_size", type=int, default=500)
    parser.add_argument("--checkpoint_every_batches", type=int, default=5)

    parser.add_argument("--store_targets", action="store_true",
                        help="Store the list of matching targets in addition to target_count.")
    parser.add_argument("--targets_cap", type=int, default=0,
                        help="If store_targets, optionally cap stored targets to first K (0 = store all).")

    parser.add_argument("--pair_compatibilities", nargs="+",
                        default=["INTERSECT", "ANY_RANGE", "ANY_DOMAIN", "ANY_BOTH"],
                        help="Which compatibility labels to process from pairs collection.")

    args = parser.parse_args()

    client = MongoClient(args.mongo_uri)
    db = client[args.db]

    pairs_col = db[args.pairs_col]
    targets_col = db[args.targets_col]
    props_col = db[args.properties_col]
    out_col = db[args.out_col]
    meta_col = db[args.meta_col]

    ensure_indexes(out_col)

    # 1) Load targets (615)
    targets = load_target_property_ids(targets_col)
    print(f"Loaded {len(targets)} target relations from {args.db}.{args.targets_col}.")
    if not targets:
        print("[WARN] No targets found; nothing to process.")
        return

    # 2) Determine query over pairs, resume-safe by _id
    base_query: Dict[str, Any] = {"compatibility": {"$in": args.pair_compatibilities}}

    last_pairs_id = get_checkpoint(meta_col, args.checkpoint_id)
    normalized_last_id = normalize_checkpoint_id(last_pairs_id)
    if last_pairs_id is not None and normalized_last_id is None:
        print(f"[WARN] Ignoring invalid checkpoint _id: {last_pairs_id}")
    if normalized_last_id is not None:
        base_query["_id"] = {"$gt": normalized_last_id}
        print(f"Resuming after pairs _id > {normalized_last_id}")

    # 3) Load the universe of needed pids for constraints:
    #    - all targets
    #    - all r1 / r2 from pairs collection (global distinct; OK for ~1.7k scale)
    print("Loading distinct r1/r2 from pairs collection...")
    r1_ids = pairs_col.distinct("r1", {"compatibility": {"$in": args.pair_compatibilities}})
    r2_ids = pairs_col.distinct("r2", {"compatibility": {"$in": args.pair_compatibilities}})
    needed_pids = sorted(set(targets).union(r1_ids).union(r2_ids))

    print(f"Loading constraints for {len(needed_pids)} relations from {args.db}.{args.properties_col}...")
    constraints = load_constraints(props_col, needed_pids)

    # Pre-materialize target constraints list for fast loop
    target_constraints: List[Tuple[str, Optional[Set[str]], Optional[Set[str]]]] = []
    for t in targets:
        dom_t, rng_t = constraints[t]
        target_constraints.append((t, dom_t, rng_t))

    # 4) Iterate pairs and compute matching targets
    cursor = pairs_col.find(base_query, {"r1": 1, "r2": 1, "compatibility": 1}).sort("_id", ASCENDING)

    ops: List[UpdateOne] = []
    processed = 0
    batches = 0
    t0 = time.time()
    last_seen_id = last_pairs_id

    for doc in cursor:
        last_seen_id = doc["_id"]
        r1 = doc["r1"]
        r2 = doc["r2"]
        compat = doc.get("compatibility")

        dom_r1, _rng_r1_unused = constraints.get(r1, (None, None))
        _dom_r2_unused, rng_r2 = constraints.get(r2, (None, None))

        matching: List[str] = []
        match_count = 0

        for t, dom_t, rng_t in target_constraints:
            # Your strict per-target check:
            # 1) Dom(t) ∩ Dom(r1)  (ANY passes)
            # 2) Rng(t) ∩ Rng(r2)  (ANY passes)
            if intersects_unknown_pass(dom_t, dom_r1) and intersects_unknown_pass(rng_t, rng_r2):
                match_count += 1
                if args.store_targets:
                    matching.append(t)

        if args.store_targets and args.targets_cap and len(matching) > args.targets_cap:
            matching = matching[: args.targets_cap]

        out_doc: Dict[str, Any] = {
            "r1": r1,
            "r2": r2,
            "pairs_compatibility": compat,
            "target_count": match_count,
            "targets_truncated": bool(args.store_targets and args.targets_cap and match_count > len(matching)),
            "updated_at": time.time(),
        }
        if args.store_targets:
            out_doc["targets"] = matching

        ops.append(UpdateOne({"r1": r1, "r2": r2}, {"$set": out_doc}, upsert=True))

        processed += 1

        if len(ops) >= args.batch_size:
            try:
                out_col.bulk_write(ops, ordered=False)
            except BulkWriteError as bwe:
                print(f"[WARN] BulkWriteError: {bwe.details.get('writeErrors', [])[:1]}")
            ops.clear()

            batches += 1
            if batches % args.checkpoint_every_batches == 0:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0.0
                set_checkpoint(
                    meta_col,
                    args.checkpoint_id,
                    last_seen_id,
                    extra={
                        "processed": processed,
                        "rate_pairs_per_sec": rate,
                        "pairs_col": args.pairs_col,
                        "out_col": args.out_col,
                        "targets_count": len(targets),
                        "compatibilities": args.pair_compatibilities,
                        "store_targets": args.store_targets,
                        "targets_cap": args.targets_cap,
                    },
                )
                print(f"Processed={processed} | rate={rate:.2f} pairs/s | last_id={last_seen_id}")

    # final flush
    if ops:
        try:
            out_col.bulk_write(ops, ordered=False)
        except BulkWriteError as bwe:
            print(f"[WARN] BulkWriteError (final): {bwe.details.get('writeErrors', [])[:1]}")
        ops.clear()

    if last_seen_id is not None:
        elapsed = time.time() - t0
        rate = processed / elapsed if elapsed > 0 else 0.0
        set_checkpoint(meta_col, args.checkpoint_id, last_seen_id, extra={"done": True, "processed": processed, "rate": rate})

    print(f"Done. Processed={processed}. Output={args.db}.{args.out_col}")


if __name__ == "__main__":
    main()