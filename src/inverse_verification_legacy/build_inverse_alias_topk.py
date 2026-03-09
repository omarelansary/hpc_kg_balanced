#!/usr/bin/env python3
"""
Build inverse-mode top-k aliases for wikibase-item properties.

Inputs:
- relation profiles JSON (for pid list, datatype, description, inverse_links)
- property aliases JSON (alias candidates + alias embeddings)
- properties label embeddings JSON (label + label_text_embedding)

Output:
- JSON array with one object per pid.
"""

import argparse
import json
from typing import Any, Dict, List

from tqdm import tqdm

from alias_selector import PropertyAliasSelector


def load_json_array(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON array in {path}")
    return [x for x in payload if isinstance(x, dict)]


def build_label_map(path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for d in load_json_array(path):
        pid = d.get("property_id")
        label = d.get("label")
        if isinstance(pid, str) and pid and isinstance(label, str):
            out[pid] = label
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build inverse-mode alias top-k for wikibase-item properties.")
    parser.add_argument(
        "--relation_profiles_path",
        default="data/raw/wikidata_ontology.relation_profiles_afterLLM_SecondTime.json",
    )
    parser.add_argument(
        "--aliases_json_path",
        default="data/raw/wikidata_ontology.property_aliases.json",
    )
    parser.add_argument(
        "--label_embeddings_json_path",
        default="data/raw/wikidata_ontology.properties_label_embeddings.json",
    )
    parser.add_argument("--output_path", required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--preload_aliases_json", action="store_true")
    parser.add_argument("--label_similarity_weight", type=float, default=0.35)
    parser.add_argument("--limit", type=int, default=0, help="Optional cap for quick testing.")
    args = parser.parse_args()

    if args.k <= 0:
        raise ValueError("--k must be > 0")

    relation_profiles = load_json_array(args.relation_profiles_path)
    label_map = build_label_map(args.label_embeddings_json_path)

    selector = PropertyAliasSelector(
        db=None,
        properties_json_path=args.label_embeddings_json_path,
        aliases_json_path=args.aliases_json_path,
        label_embeddings_json_path=args.label_embeddings_json_path,
        preload_aliases_json=args.preload_aliases_json,
        label_similarity_weight=args.label_similarity_weight,
    )

    rows: List[Dict[str, Any]] = []
    count = 0
    for doc in tqdm(relation_profiles, desc="Selecting aliases", unit="pid"):
        pid = doc.get("property_id")
        metadata = doc.get("metadata") or {}
        datatype = metadata.get("datatype")
        if datatype != "wikibase-item":
            continue
        if not isinstance(pid, str) or not pid:
            continue

        selected = selector.get(pid=pid, k=args.k, mode="inverse", include_debug=False)
        out = {
            "pid": pid,
            "label": label_map.get(pid, selected.get("label", "")),
            "description": metadata.get("description", ""),
            "datatype": datatype,
            "inverse_links": metadata.get("inverse_links") or [],
            "inverse_mode_aliases_labels_topk": selected.get("aliases", []),
        }
        rows.append(out)
        count += 1
        if args.limit > 0 and count >= args.limit:
            break

    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=True, indent=2)
        f.write("\n")

    print(f"Wrote {len(rows)} rows to {args.output_path}")


if __name__ == "__main__":
    main()
