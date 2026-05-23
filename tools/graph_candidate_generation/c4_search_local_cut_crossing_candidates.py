#!/usr/bin/env python3
"""Search frozen local evidence for candidates crossing tested C4 bridge cuts."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.evaluation.allocation_metrics import load_allocation  # noqa: E402
from src.kg_pipeline.evaluation.candidate_report import sha256_file  # noqa: E402
from src.kg_pipeline.evaluation.graph_io import Triple, load_graph_triples  # noqa: E402
from tools.graph_candidate_generation.c4_audit_replacement_pool_against_bridge_cuts import (  # noqa: E402
    find_simple_bridges_iterative,
)
from tools.graph_candidate_generation.c4_probe_bridge_aware_replace_add import (  # noqa: E402
    build_undirected,
    classify_target,
    load_config,
    relation_delta,
    repo_relative,
    resolve_path,
    target_edges,
)

DEFAULT_CONFIG = Path("experiments/graph_candidates/C4_bridge_aware_replace_add/configs/config.template.json")
DEFAULT_BRIDGE_CUT_AUDIT = Path(
    "experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only/"
    "replacement_pool_bridge_cut_audit.json"
)
DEFAULT_OUTPUT_DIR = Path("experiments/graph_candidates/C4_bridge_aware_replace_add/reports/probe_only")
STAGE11_GRAPH_OUTPUT = Path("src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl")
STAGE12_GRAPH_OUTPUT = Path(
    "src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/graph_output.jsonl"
)
STAGE02_SHARDS = Path("archive/hetzner_version/runs/prod_refine_20260315_180520/stage02_candidates/shards")
FROZEN_CANDIDATE_POOLS = Path("artifacts/frozen_candidate_pools")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--bridge-cut-audit-report", type=Path, default=DEFAULT_BRIDGE_CUT_AUDIT)
    parser.add_argument("--max-target-edges", type=int, default=1000)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Path]:
    return {
        "json": output_dir / "local_cut_crossing_candidate_search.json",
        "markdown": output_dir / "local_cut_crossing_candidate_search.md",
    }


def refuse_overwrite(paths: dict[str, Path], force: bool) -> None:
    existing = [path for path in paths.values() if path.exists()]
    if existing and not force:
        names = ", ".join(str(path) for path in existing)
        raise FileExistsError(f"Refusing to overwrite local search reports without --force: {names}")


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def candidate_sources() -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = [
        {
            "source_id": "stage12_graph_output",
            "source_type": "single_jsonl",
            "paths": [resolve_path(STAGE12_GRAPH_OUTPUT)],
        },
        {
            "source_id": "stage11_graph_output",
            "source_type": "single_jsonl",
            "paths": [resolve_path(STAGE11_GRAPH_OUTPUT)],
        },
    ]
    stage02_dir = resolve_path(STAGE02_SHARDS)
    stage02_paths = sorted(stage02_dir.glob("*.jsonl")) if stage02_dir.is_dir() else []
    sources.append(
        {
            "source_id": "stage02_candidate_shards",
            "source_type": "jsonl_glob",
            "paths": stage02_paths,
        }
    )
    frozen_dir = resolve_path(FROZEN_CANDIDATE_POOLS)
    frozen_paths = sorted(frozen_dir.rglob("*.jsonl")) if frozen_dir.is_dir() else []
    sources.append(
        {
            "source_id": "frozen_candidate_pools",
            "source_type": "jsonl_tree",
            "paths": frozen_paths,
        }
    )
    return sources


def extract_triple(row: Any) -> Triple | None:
    if not isinstance(row, dict):
        return None
    h = row.get("h")
    r = row.get("r")
    t = row.get("t")
    if all(isinstance(value, str) and value for value in (h, r, t)):
        return h, r, t

    triple = row.get("triple")
    if isinstance(triple, dict):
        h = triple.get("h")
        r = triple.get("r")
        t = triple.get("t")
        if all(isinstance(value, str) and value for value in (h, r, t)):
            return h, r, t
    if isinstance(triple, list) and len(triple) == 3 and all(isinstance(value, str) for value in triple):
        return triple[0], triple[1], triple[2]
    return None


def iter_jsonl_triples(path: Path) -> Iterable[tuple[int, Triple | None, dict[str, Any] | None]]:
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                yield line_number, None, None
                continue
            triple = extract_triple(row)
            yield line_number, triple, row if isinstance(row, dict) else None


def prepare_tested_cuts(
    graph_triples: set[Triple],
    entities: set[str],
    relation_counts: Counter[str],
    relation_expected: dict[str, float],
    target_relations: set[str],
    max_target_edges: int,
) -> tuple[list[dict[str, Any]], dict[str, set[int]]]:
    adjacency, pair_counts, _degrees = build_undirected(graph_triples)
    simple_bridges = find_simple_bridges_iterative(adjacency)
    bridges = {pair for pair in simple_bridges if pair_counts[pair] == 1}
    ordered_targets = target_edges(
        sorted(graph_triples),
        relation_counts,
        relation_expected,
        target_relations,
        max_target_edges,
    )

    cut_index: dict[str, set[int]] = defaultdict(set)
    cuts: list[dict[str, Any]] = []
    entity_count = len(entities)
    for target in ordered_targets:
        classified = classify_target(target, pair_counts, bridges, adjacency, entity_count)
        if not classified["connectivity_critical"]:
            continue
        side = classified.pop("_side")
        if side is None:
            continue
        if len(side) > entity_count / 2:
            side = entities - side
        cut_id = len(cuts)
        for entity in side:
            cut_index[entity].add(cut_id)
        cuts.append(
            {
                "cut_id": cut_id,
                "target_edge": {"h": classified["h"], "r": classified["r"], "t": classified["t"]},
                "bridge_pair": classified["bridge_pair"],
                "relation_surplus_before": classified["relation_surplus_before"],
                "smaller_side_size": len(side),
                "larger_side_size": entity_count - len(side),
            }
        )
    return cuts, cut_index


def summarize_sources(sources: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for source in sources:
        paths = source["paths"]
        out[source["source_id"]] = {
            "source_type": source["source_type"],
            "file_count": len(paths),
            "paths_first_10": [repo_relative(path) for path in paths[:10]],
        }
    return out


def row_source_metadata(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        key: row.get(key)
        for key in (
            "candidate_id",
            "source_stage",
            "provenance_type",
            "relation_allocation_status",
            "endpoint_overlap_with_b0",
            "score",
            "path_group_id",
            "path_group_size",
            "source_backend",
            "source_stage",
            "chunk_id",
        )
        if row.get(key) is not None
    }


def scan_sources(
    sources: list[dict[str, Any]],
    cuts: list[dict[str, Any]],
    cut_index: dict[str, set[int]],
    graph_triples: set[Triple],
    entities: set[str],
    relation_counts: Counter[str],
    relation_expected: dict[str, float],
) -> dict[str, Any]:
    source_stats: dict[str, Counter[str]] = defaultdict(Counter)
    source_relation_counts: dict[str, Counter[str]] = defaultdict(Counter)
    aggregate = Counter()
    examples: list[dict[str, Any]] = []
    feasible_examples: list[dict[str, Any]] = []
    cut_counts: dict[int, Counter[str]] = defaultdict(Counter)
    unique_crossing_candidates: set[Triple] = set()
    unique_allocated_crossing_candidates: set[Triple] = set()
    unique_balance_improving_candidates: set[Triple] = set()
    unique_deficit_increase_candidates: set[Triple] = set()

    for source in sources:
        source_id = source["source_id"]
        paths: list[Path] = source["paths"]
        if not paths:
            source_stats[source_id]["missing_or_empty_source_list"] += 1
            continue
        for path in paths:
            if not path.is_file():
                source_stats[source_id]["missing_files"] += 1
                continue
            source_stats[source_id]["files_scanned"] += 1
            source_stats[source_id]["bytes_scanned"] += path.stat().st_size
            for line_number, triple, row in iter_jsonl_triples(path):
                source_stats[source_id]["rows_scanned"] += 1
                if triple is None:
                    source_stats[source_id]["rows_without_parseable_triple"] += 1
                    continue
                h, r, t = triple
                source_stats[source_id]["triples_parsed"] += 1
                source_relation_counts[source_id][r] += 1
                h_inside = h in entities
                t_inside = t in entities
                if h_inside and t_inside:
                    source_stats[source_id]["endpoint_inside_b0_both"] += 1
                elif h_inside or t_inside:
                    source_stats[source_id]["endpoint_inside_b0_one"] += 1
                    continue
                else:
                    source_stats[source_id]["endpoint_inside_b0_none"] += 1
                    continue

                if triple in graph_triples:
                    source_stats[source_id]["already_in_b0"] += 1
                    continue

                crossing_cut_ids = cut_index.get(h, set()) ^ cut_index.get(t, set())
                if not crossing_cut_ids:
                    source_stats[source_id]["both_endpoints_in_b0_but_no_tested_cut_crossing"] += 1
                    continue

                source_stats[source_id]["cut_crossing_candidate_rows"] += 1
                aggregate["cut_crossing_candidate_rows"] += 1
                unique_crossing_candidates.add(triple)
                allocated = r in relation_expected
                if allocated:
                    source_stats[source_id]["allocated_cut_crossing_candidate_rows"] += 1
                    aggregate["allocated_cut_crossing_candidate_rows"] += 1
                    unique_allocated_crossing_candidates.add(triple)
                else:
                    source_stats[source_id]["unallocated_cut_crossing_candidate_rows"] += 1

                for cut_id in sorted(crossing_cut_ids):
                    cut = cuts[cut_id]
                    delta = relation_delta(relation_counts, relation_expected, cut["target_edge"]["r"], r)
                    surplus_reducing = delta["surplus_delta"] < 0
                    deficit_increase = delta["deficit_delta"] > 0
                    if surplus_reducing:
                        aggregate["balance_improving_candidate_cut_pairs"] += 1
                        source_stats[source_id]["balance_improving_candidate_cut_pairs"] += 1
                        unique_balance_improving_candidates.add(triple)
                        if allocated:
                            aggregate["allocated_balance_improving_candidate_cut_pairs"] += 1
                            source_stats[source_id]["allocated_balance_improving_candidate_cut_pairs"] += 1
                        else:
                            aggregate["unallocated_balance_improving_candidate_cut_pairs"] += 1
                            source_stats[source_id]["unallocated_balance_improving_candidate_cut_pairs"] += 1
                    if deficit_increase:
                        aggregate["deficit_increase_candidate_cut_pairs"] += 1
                        source_stats[source_id]["deficit_increase_candidate_cut_pairs"] += 1
                        unique_deficit_increase_candidates.add(triple)

                    cut_counts[cut_id]["cut_crossing_candidate_rows"] += 1
                    if allocated:
                        cut_counts[cut_id]["allocated_cut_crossing_candidate_rows"] += 1
                    if surplus_reducing:
                        cut_counts[cut_id]["balance_improving_candidate_rows"] += 1
                        if allocated:
                            cut_counts[cut_id]["allocated_balance_improving_candidate_rows"] += 1
                    if deficit_increase:
                        cut_counts[cut_id]["deficit_increase_candidate_rows"] += 1

                    example = {
                        "source_id": source_id,
                        "source_path": repo_relative(path),
                        "line_number": line_number,
                        "candidate": {"h": h, "r": r, "t": t},
                        "cut_id": cut_id,
                        "target_edge": cut["target_edge"],
                        "smaller_side_size": cut["smaller_side_size"],
                        "allocated_relation": allocated,
                        "balance_effect": delta,
                        "surplus_reducing": surplus_reducing,
                        "deficit_would_increase": deficit_increase,
                        "source_metadata": row_source_metadata(row),
                    }
                    if len(examples) < 100:
                        examples.append(example)
                    if allocated and surplus_reducing and not deficit_increase and len(feasible_examples) < 100:
                        feasible_examples.append(example)

    per_cut = []
    for cut in cuts:
        counts = cut_counts[cut["cut_id"]]
        per_cut.append(
            {
                **cut,
                "cut_crossing_candidate_rows": counts["cut_crossing_candidate_rows"],
                "allocated_cut_crossing_candidate_rows": counts["allocated_cut_crossing_candidate_rows"],
                "balance_improving_candidate_rows": counts["balance_improving_candidate_rows"],
                "allocated_balance_improving_candidate_rows": counts[
                    "allocated_balance_improving_candidate_rows"
                ],
                "deficit_increase_candidate_rows": counts["deficit_increase_candidate_rows"],
            }
        )
    per_cut.sort(
        key=lambda row: (
            -row["balance_improving_candidate_rows"],
            -row["allocated_cut_crossing_candidate_rows"],
            -row["cut_crossing_candidate_rows"],
            row["cut_id"],
        )
    )

    return {
        "source_stats": {
            source_id: {
                **dict(sorted(stats.items())),
                "top_20_relations": dict(source_relation_counts[source_id].most_common(20)),
            }
            for source_id, stats in sorted(source_stats.items())
        },
        "aggregate_counts": {
            "cut_crossing_candidate_rows": aggregate["cut_crossing_candidate_rows"],
            "allocated_cut_crossing_candidate_rows": aggregate["allocated_cut_crossing_candidate_rows"],
            "balance_improving_candidate_cut_pairs": aggregate["balance_improving_candidate_cut_pairs"],
            "allocated_balance_improving_candidate_cut_pairs": aggregate[
                "allocated_balance_improving_candidate_cut_pairs"
            ],
            "unallocated_balance_improving_candidate_cut_pairs": aggregate[
                "unallocated_balance_improving_candidate_cut_pairs"
            ],
            "deficit_increase_candidate_cut_pairs": aggregate["deficit_increase_candidate_cut_pairs"],
            "unique_cut_crossing_candidates": len(unique_crossing_candidates),
            "unique_allocated_cut_crossing_candidates": len(unique_allocated_crossing_candidates),
            "unique_balance_improving_candidates": len(unique_balance_improving_candidates),
            "unique_deficit_increase_candidates": len(unique_deficit_increase_candidates),
        },
        "top_cuts_by_candidate_count": per_cut[:50],
        "top_candidate_examples": sorted(
            examples,
            key=lambda row: (
                row["balance_effect"]["surplus_delta"],
                row["balance_effect"]["deficit_delta"],
                row["source_id"],
                row["candidate"]["r"],
            ),
        )[:50],
        "top_feasible_looking_candidates": sorted(
            feasible_examples,
            key=lambda row: (
                row["balance_effect"]["surplus_delta"],
                row["balance_effect"]["deficit_delta"],
                row["source_id"],
                row["candidate"]["r"],
            ),
        )[:50],
    }


def run_search(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    config_path = resolve_path(args.config)
    audit_path = resolve_path(args.bridge_cut_audit_report)
    config = load_config(config_path)
    audit_report = load_json_file(audit_path)
    parent_graph = resolve_path(config["parent_graph_path"])
    allocation_path = resolve_path(config["allocation_path"])

    graph_triples = set(load_graph_triples(parent_graph))
    entities = {node for h, _r, t in graph_triples for node in (h, t)}
    relation_counts = Counter(r for _h, r, _t in graph_triples)
    allocation = load_allocation(allocation_path)
    relation_expected = allocation["relation_expected"]
    target_relations = set(config.get("target_relations") or [])
    cuts, cut_index = prepare_tested_cuts(
        graph_triples,
        entities,
        relation_counts,
        relation_expected,
        target_relations,
        args.max_target_edges,
    )
    sources = candidate_sources()
    scan = scan_sources(
        sources,
        cuts,
        cut_index,
        graph_triples,
        entities,
        relation_counts,
        relation_expected,
    )
    finished = time.time()
    return {
        "schema_version": "c4-local-cut-crossing-candidate-search-v1",
        "search_id": "C4_2_local_cut_crossing_candidate_search",
        "status": "read_only_local_evidence_search",
        "inputs": {
            "config": {
                "path": repo_relative(config_path),
                "sha256": sha256_file(config_path),
            },
            "bridge_cut_audit_report": {
                "path": repo_relative(audit_path),
                "sha256": sha256_file(audit_path),
                "summary": audit_report.get("aggregate"),
            },
            "parent_graph": {
                "path": config["parent_graph_path"],
                "sha256": sha256_file(parent_graph),
            },
            "allocation": {
                "path": config["allocation_path"],
                "sha256": sha256_file(allocation_path),
            },
        },
        "limits": {
            "max_target_edges": args.max_target_edges,
        },
        "candidate_sources": summarize_sources(sources),
        "bridge_cut_context": {
            "cuts_tested": len(cuts),
            "target_relations": sorted(target_relations),
            "cut_index_entities": len(cut_index),
            "b0_unique_triples": len(graph_triples),
            "b0_entities": len(entities),
        },
        **scan,
        "interpretation": interpretation(scan["aggregate_counts"]),
        "runtime": {
            "started_on": datetime.fromtimestamp(started, timezone.utc).isoformat(),
            "finished_on": datetime.fromtimestamp(finished, timezone.utc).isoformat(),
            "elapsed_seconds": round(finished - started, 6),
        },
        "notes": [
            "Read-only local evidence search; no graph candidate was generated.",
            "No WDQS query was made.",
            "No LLM call was made.",
            "candidate_registry.v1.json was not updated.",
            "Candidate triples already present in B0 were excluded from cut-crossing candidate counts.",
        ],
    }


def interpretation(aggregate: dict[str, int]) -> dict[str, Any]:
    if aggregate["unique_cut_crossing_candidates"] == 0:
        primary = "no_local_cut_crossing_candidates_found"
    elif aggregate["unique_allocated_cut_crossing_candidates"] == 0:
        primary = "local_cut_crossing_candidates_are_unallocated"
    elif aggregate["unique_balance_improving_candidates"] == 0:
        primary = "local_cut_crossing_candidates_do_not_reduce_surplus"
    elif aggregate["allocated_balance_improving_candidate_cut_pairs"] == 0:
        primary = "only_unallocated_cut_crossing_candidates_reduce_surplus"
    elif aggregate["unique_deficit_increase_candidates"] >= aggregate["unique_balance_improving_candidates"]:
        primary = "balance_improving_candidates_mostly_increase_deficit"
    else:
        primary = "local_feasible_looking_candidates_exist"
    return {
        "primary_result": primary,
        "graph_candidate_generated": False,
        "candidate_registry_updated": False,
    }


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    aggregate = report["aggregate_counts"]
    lines = [
        "# C4.2 Local Cut-Crossing Candidate Search",
        "",
        "Status: read-only local evidence search. No graph candidate was generated.",
        "",
        "## Inputs",
        "",
        f"- Config: `{report['inputs']['config']['path']}`",
        f"- Bridge-cut audit: `{report['inputs']['bridge_cut_audit_report']['path']}`",
        f"- Parent graph: `{report['inputs']['parent_graph']['path']}`",
        f"- Parent graph SHA256: `{report['inputs']['parent_graph']['sha256']}`",
        f"- Allocation: `{report['inputs']['allocation']['path']}`",
        f"- Allocation SHA256: `{report['inputs']['allocation']['sha256']}`",
        "",
        "## Search Result",
        "",
        f"- Cuts tested: `{report['bridge_cut_context']['cuts_tested']}`",
        f"- Cut-crossing candidate rows found: `{aggregate['cut_crossing_candidate_rows']}`",
        f"- Unique cut-crossing candidates: `{aggregate['unique_cut_crossing_candidates']}`",
        f"- Allocated cut-crossing candidate rows: `{aggregate['allocated_cut_crossing_candidate_rows']}`",
        f"- Unique allocated cut-crossing candidates: `{aggregate['unique_allocated_cut_crossing_candidates']}`",
        f"- Surplus-reducing candidate-cut pairs: `{aggregate['balance_improving_candidate_cut_pairs']}`",
        f"- Unique balance-improving candidates: `{aggregate['unique_balance_improving_candidates']}`",
        f"- Allocated surplus-reducing candidate-cut pairs: `{aggregate['allocated_balance_improving_candidate_cut_pairs']}`",
        f"- Unallocated surplus-reducing candidate-cut pairs: `{aggregate['unallocated_balance_improving_candidate_cut_pairs']}`",
        f"- Candidate-cut pairs that would increase deficit: `{aggregate['deficit_increase_candidate_cut_pairs']}`",
        f"- Primary result: `{report['interpretation']['primary_result']}`",
        "",
        "## Source Scan Counts",
        "",
        "| Source | Files | Rows scanned | Parsed triples | Both endpoints in B0 | Already in B0 | Cut-crossing rows | Allocated crossing rows |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for source_id, stats in report["source_stats"].items():
        lines.append(
            f"| `{source_id}` | {stats.get('files_scanned', 0)} | {stats.get('rows_scanned', 0)} | "
            f"{stats.get('triples_parsed', 0)} | {stats.get('endpoint_inside_b0_both', 0)} | "
            f"{stats.get('already_in_b0', 0)} | {stats.get('cut_crossing_candidate_rows', 0)} | "
            f"{stats.get('allocated_cut_crossing_candidate_rows', 0)} |"
        )

    lines.extend(
        [
            "",
            "## Top Feasible-Looking Candidates",
            "",
        ]
    )
    feasible = report["top_feasible_looking_candidates"]
    if feasible:
        lines.append("| Source | Cut | Candidate | Target | Surplus Delta | Deficit Delta |")
        lines.append("| --- | ---: | --- | --- | ---: | ---: |")
        for row in feasible[:20]:
            c = row["candidate"]
            t = row["target_edge"]
            b = row["balance_effect"]
            lines.append(
                f"| `{row['source_id']}` | {row['cut_id']} | `{c['h']} {c['r']} {c['t']}` | "
                f"`{t['h']} {t['r']} {t['t']}` | {b['surplus_delta']} | {b['deficit_delta']} |"
            )
    else:
        lines.append("No feasible-looking candidates were found under the local read-only search criteria.")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This search broadens C4.1 beyond the eligible replacement pool by scanning Stage11/Stage12 graph outputs, "
            "Stage2 candidate shards, and frozen candidate pools. It still uses only local frozen files.",
            "",
            "The search excludes triples already present in B0 and requires both candidate endpoints to be in B0. "
            "A cut-crossing hit means the candidate connects the two sides exposed by removing a tested target bridge edge.",
            "",
            "This output is evidence only. It does not create a graph and does not update the candidate registry.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    paths = output_paths()
    refuse_overwrite(paths, args.force)
    report = run_search(args)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_markdown(paths["markdown"], report)
    aggregate = report["aggregate_counts"]
    print(f"search_json={paths['json']}")
    print(f"search_markdown={paths['markdown']}")
    print(f"cuts_tested={report['bridge_cut_context']['cuts_tested']}")
    print(f"cut_crossing_candidate_rows={aggregate['cut_crossing_candidate_rows']}")
    print(f"unique_cut_crossing_candidates={aggregate['unique_cut_crossing_candidates']}")
    print(f"allocated_cut_crossing_candidate_rows={aggregate['allocated_cut_crossing_candidate_rows']}")
    print(f"balance_improving_candidate_cut_pairs={aggregate['balance_improving_candidate_cut_pairs']}")
    print(f"primary_result={report['interpretation']['primary_result']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
