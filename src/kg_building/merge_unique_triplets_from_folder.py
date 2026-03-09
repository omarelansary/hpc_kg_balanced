#!/usr/bin/env python3
"""Merge triplet files from a folder and write unique triplets as JSON.

Supported input formats:
- JSONL: one object per line with fields h/r/t by default
- JSON: a list of triplet objects, or a dict containing `triples`/`triples_out`

Deduplication key:
- (head, relation, tail)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Tuple

Triple = Tuple[str, str, str]


def _parse_triplet_records(
    rows: Iterable[object],
    *,
    field_head: str,
    field_rel: str,
    field_tail: str,
) -> List[Triple]:
    triples: List[Triple] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        h = row.get(field_head)
        r = row.get(field_rel)
        t = row.get(field_tail)
        if h is None or r is None or t is None:
            continue
        triples.append((str(h), str(r), str(t)))
    return triples


def _load_jsonl(
    path: Path,
    *,
    field_head: str,
    field_rel: str,
    field_tail: str,
) -> List[Triple]:
    triples: List[Triple] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} at line {line_no}: {exc}") from exc
            triples.extend(
                _parse_triplet_records(
                    [obj],
                    field_head=field_head,
                    field_rel=field_rel,
                    field_tail=field_tail,
                )
            )
    return triples


def _load_json(
    path: Path,
    *,
    field_head: str,
    field_rel: str,
    field_tail: str,
) -> List[Triple]:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)

    if isinstance(obj, list):
        return _parse_triplet_records(
            obj,
            field_head=field_head,
            field_rel=field_rel,
            field_tail=field_tail,
        )

    if isinstance(obj, dict):
        for key in ("triples", "triples_out"):
            rows = obj.get(key)
            if isinstance(rows, list):
                return _parse_triplet_records(
                    rows,
                    field_head=field_head,
                    field_rel=field_rel,
                    field_tail=field_tail,
                )
        return _parse_triplet_records(
            [obj],
            field_head=field_head,
            field_rel=field_rel,
            field_tail=field_tail,
        )

    return []


def _load_triplets_from_file(
    path: Path,
    *,
    field_head: str,
    field_rel: str,
    field_tail: str,
) -> List[Triple]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return _load_jsonl(
            path,
            field_head=field_head,
            field_rel=field_rel,
            field_tail=field_tail,
        )
    if suffix == ".json":
        return _load_json(
            path,
            field_head=field_head,
            field_rel=field_rel,
            field_tail=field_tail,
        )
    raise ValueError(f"Unsupported file type: {path}")


def _normalize_allocation_records(obj: object) -> List[dict]:
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]

    if isinstance(obj, dict):
        for key in ("allocations", "records", "items", "results", "data"):
            rows = obj.get(key)
            if isinstance(rows, list):
                return [x for x in rows if isinstance(x, dict)]

        if "relation" in obj:
            return [obj]

    return []


def _load_allocation_relations(allocation_path: Path) -> set[str]:
    suffix = allocation_path.suffix.lower()
    relations: set[str] = set()

    if suffix == ".jsonl":
        with allocation_path.open("r", encoding="utf-8") as f:
            for line_no, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSONL in allocation file {allocation_path} at line {line_no}: {exc}"
                    ) from exc
                if not isinstance(obj, dict):
                    continue
                relation = obj.get("relation")
                if relation is not None:
                    relations.add(str(relation))
        return relations

    if suffix == ".json":
        with allocation_path.open("r", encoding="utf-8") as f:
            obj = json.load(f)
        for row in _normalize_allocation_records(obj):
            relation = row.get("relation")
            if relation is not None:
                relations.add(str(relation))
        return relations

    raise ValueError(f"Unsupported allocation file type: {allocation_path} (expected .json or .jsonl)")


def _discover_files(input_dir: Path, patterns: Sequence[str], recursive: bool) -> List[Path]:
    files: List[Path] = []
    for pattern in patterns:
        matches = input_dir.rglob(pattern) if recursive else input_dir.glob(pattern)
        files.extend(sorted(p for p in matches if p.is_file()))

    deduped: List[Path] = []
    seen = set()
    for path in files:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _dedupe_triples(triples: Iterable[Triple]) -> List[Triple]:
    out: List[Triple] = []
    seen = set()
    for triple in triples:
        if triple in seen:
            continue
        seen.add(triple)
        out.append(triple)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge triplet files from a folder into one unique JSON file.")
    ap.add_argument("--input_dir", required=True, help="Folder containing triplet files.")
    ap.add_argument(
        "--patterns",
        nargs="+",
        default=["*.jsonl", "*.json"],
        help="Input file glob patterns to scan inside input_dir (NOT allocation pattern groups). Defaults to *.jsonl *.json",
    )
    ap.add_argument("--recursive", action="store_true", help="Scan subfolders recursively.")
    ap.add_argument("--output_json", required=True, help="Path for merged unique triplets JSON array.")
    ap.add_argument("--output_stats_json", default="", help="Optional stats JSON output path.")
    ap.add_argument(
        "--allocation",
        default="",
        help="Optional allocation JSON/JSONL file. If provided, triples whose relation is not present in allocation are removed.",
    )
    ap.add_argument("--field_head", default="h")
    ap.add_argument("--field_rel", default="r")
    ap.add_argument("--field_tail", default="t")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError(f"Input directory not found or not a directory: {input_dir}")

    # --patterns are file-name globs for discovering input files (e.g., *.jsonl, *.json),
    # not semantic 'pattern' fields from the allocation file.
    files = _discover_files(input_dir, args.patterns, args.recursive)
    if not files:
        raise ValueError(
            f"No files matched in {input_dir} for patterns: {', '.join(args.patterns)}"
        )

    all_triples: List[Triple] = []
    file_summaries: List[Dict[str, object]] = []
    for path in files:
        triples = _load_triplets_from_file(
            path,
            field_head=args.field_head,
            field_rel=args.field_rel,
            field_tail=args.field_tail,
        )
        file_summaries.append(
            {
                "path": str(path.resolve()),
                "triples_found": len(triples),
            }
        )
        all_triples.extend(triples)

    triples_before_allocation_filter = len(all_triples)
    filtered_out_by_allocation = 0
    allocation_relations_count = 0
    allocation_relation_hits: Dict[str, int] = {}

    if args.allocation:
        allocation_path = Path(args.allocation)
        if not allocation_path.exists() or not allocation_path.is_file():
            raise ValueError(f"Allocation file not found: {allocation_path}")

        allowed_relations = _load_allocation_relations(allocation_path)
        allocation_relations_count = len(allowed_relations)
        if not allowed_relations:
            raise ValueError(
                f"No relations found in allocation file: {allocation_path}. Expected records with a 'relation' field."
            )

        relation_counter = Counter(r for _, r, _ in all_triples)
        allocation_relation_hits = {
            rel: count for rel, count in relation_counter.items() if rel in allowed_relations
        }

        filtered_triples: List[Triple] = []
        for h, r, t in all_triples:
            if r in allowed_relations:
                filtered_triples.append((h, r, t))
            else:
                filtered_out_by_allocation += 1
        all_triples = filtered_triples

    unique_triples = _dedupe_triples(all_triples)

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {args.field_head: h, args.field_rel: r, args.field_tail: t}
        for h, r, t in unique_triples
    ]
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    stats = {
        "input_dir": str(input_dir.resolve()),
        "patterns": list(args.patterns),
        "recursive": bool(args.recursive),
        "files_scanned": len(files),
        "allocation_filter_applied": bool(args.allocation),
        "allocation_path": str(Path(args.allocation).resolve()) if args.allocation else "",
        "allocation_relations_count": allocation_relations_count,
        "triples_before_dedupe": len(all_triples),
        "triples_before_allocation_filter": triples_before_allocation_filter,
        "triples_after_allocation_filter": len(all_triples),
        "triples_removed_by_allocation_filter": filtered_out_by_allocation,
        "triples_after_dedupe": len(unique_triples),
        "allocation_relation_hits": allocation_relation_hits,
        "files": file_summaries,
        "output_json": str(output_path.resolve()),
    }

    if args.output_stats_json:
        stats_path = Path(args.output_stats_json)
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        with stats_path.open("w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

    print("merge_complete")
    print(f"files_scanned: {len(files)}")
    if args.allocation:
        print(f"allocation_relations_count: {allocation_relations_count}")
        print(f"triples_before_allocation_filter: {triples_before_allocation_filter}")
        print(f"triples_after_allocation_filter: {len(all_triples)}")
        print(f"triples_removed_by_allocation_filter: {filtered_out_by_allocation}")
    print(f"triples_before_dedupe: {len(all_triples)}")
    print(f"triples_after_dedupe: {len(unique_triples)}")
    print(f"output_json: {output_path}")


if __name__ == "__main__":
    main()
