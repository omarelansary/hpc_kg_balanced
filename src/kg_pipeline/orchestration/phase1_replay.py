"""Run-scoped Phase I replay/export helpers for the pipeline runner."""

from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

# The cluster environment can expose an optional pyarrow build that is not
# compatible with the installed NumPy. Pandas treats pyarrow as optional.
sys.modules.setdefault("pyarrow", None)

from src.kg_pipeline.phase1.allocation_export import (
    allocation_results_to_rows,
    build_allocation_payload,
    normalize_allocation_rows,
    positive_eta_relations,
    run_phase3_allocation,
)
from src.kg_pipeline.phase1.genericity_matrix import (
    build_square_adjacency_matrix,
    build_weight_matrix,
    extract_relation_submatrix,
    matrix_to_nested_json_dict,
)
from src.kg_pipeline.phase1.pattern_evidence import (
    load_composition_verified_compact,
    load_pair_counts,
)
from src.kg_pipeline.phase1.pattern_groups import (
    build_pattern_groups,
    filter_composition_candidates,
    filter_pair_universe,
    pattern_group_counts,
    select_anti_symmetric_candidates,
    select_inverse_candidates,
    select_symmetric_candidates,
    unique_preserve,
)


HOP_SUPPORT_PATH = Path("data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl")
COMPOSITION_PATH = Path(
    "data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl"
)
CANONICAL_ALLOCATION_PATH = Path("src/Pruning graph/bidirectional_allocation_results5k.json")
CANONICAL_GENERICITY_MATRIX_PATH = Path(
    "archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json"
)

EXPECTED_GROUP_COUNTS = {
    "symmetric": 18,
    "anti_symmetric": 66,
    "inverse": 44,
    "composition": 26,
}
COMPOSITION_MIN_EXAMINED = 50
COMPOSITION_MIN_SHORTCUTS = 1
WILSON_Z_95 = 1.959963984540054

PHASE1_REPLAY_DIRNAME = "phase1_replay"
ALLOCATION_OUT_NAME = "allocation.replayed.json"
MATRIX_OUT_NAME = "genericity_support_matrix.replayed.json"
REPORT_OUT_NAME = "phase1_replay_report.json"
SUMMARY_OUT_NAME = "phase1_replay_summary.md"


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ensure_required_inputs(repo_root: Path) -> None:
    missing = [
        path
        for path in [
            HOP_SUPPORT_PATH,
            COMPOSITION_PATH,
            CANONICAL_ALLOCATION_PATH,
            CANONICAL_GENERICITY_MATRIX_PATH,
        ]
        if not (repo_root / path).is_file()
    ]
    if missing:
        joined = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"missing required Phase I replay input(s): {joined}")


def _relation_class_map(canonical_allocation: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in canonical_allocation.get("allocations", []):
        relation = row.get("relation")
        relation_class = row.get("relation_dom_rng_class")
        if isinstance(relation, str) and isinstance(relation_class, str):
            out[relation] = relation_class
    return out




def _order_matrix_like_canonical(
    matrix: dict[str, dict[str, float]],
    canonical_matrix: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    ordered: dict[str, dict[str, float]] = {}
    for relation, canonical_row in canonical_matrix.items():
        if relation not in matrix:
            continue
        row = matrix[relation]
        ordered_row = {target: row[target] for target in canonical_row if target in row}
        for target, value in row.items():
            if target not in ordered_row:
                ordered_row[target] = value
        ordered[relation] = ordered_row
    for relation, row in matrix.items():
        if relation not in ordered:
            ordered[relation] = row
    return ordered


def _compute_replay_payloads(repo_root: Path) -> dict[str, Any]:
    ensure_required_inputs(repo_root)

    canonical_allocation = load_json(repo_root / CANONICAL_ALLOCATION_PATH)
    canonical_matrix = load_json(repo_root / CANONICAL_GENERICITY_MATRIX_PATH)
    config = canonical_allocation["config"]

    pair_counts = load_pair_counts(repo_root / HOP_SUPPORT_PATH, only_success=True)
    pair_universe = filter_pair_universe(
        pair_counts,
        base_min_total=int(config["base_min_total"]),
        base_max_total=int(config["base_max_total"]),
    )

    symmetric = select_symmetric_candidates(
        pair_universe,
        min_support=int(config["sym_min_support"]),
        min_confidence=float(config["sym_min_conf"]),
    )
    anti_symmetric = select_anti_symmetric_candidates(
        pair_universe,
        min_support=int(config["anti_min_support"]),
        min_confidence=float(config["anti_min_conf"]),
    )
    inverse = select_inverse_candidates(
        pair_universe,
        min_support=int(config["inv_min_support"]),
        min_confidence=float(config["inv_min_conf"]),
        sort_by="bidirectional_conf_min",
    )

    composition_input = load_composition_verified_compact(repo_root / COMPOSITION_PATH, only_success=True)
    composition = filter_composition_candidates(
        composition_input,
        min_support=int(config["comp_min_support"]),
        min_examined=COMPOSITION_MIN_EXAMINED,
        min_confidence=float(config["comp_min_conf"]),
        min_shortcuts=COMPOSITION_MIN_SHORTCUTS,
        use_wilson=False,
        wilson_z=WILSON_Z_95,
        sort_by="conf_composition_sample",
    )

    pattern_groups, overlap = build_pattern_groups(symmetric, anti_symmetric, inverse, composition)
    if overlap:
        raise ValueError(f"unexpected symmetric/anti-symmetric overlap: {overlap}")

    all_group_relations = unique_preserve(
        pattern_groups["symmetric"]
        + pattern_groups["anti_symmetric"]
        + pattern_groups["inverse"]
        + pattern_groups["composition"]
    )
    relations_universe, adjacency = build_square_adjacency_matrix(
        pair_universe,
        min_support=int(config["matrix_min_support"]),
        extra_relations=all_group_relations,
    )

    weight_matrix, alloc_results = run_phase3_allocation(
        pattern_groups=pattern_groups,
        eta_per_group={name: int(value) for name, value in canonical_allocation["eta_per_group"].items()},
        relations_universe=relations_universe,
        adjacency=adjacency,
        matrix_mode=str(config["matrix_mode"]),
        temperature=float(config["temperature"]),
        epsilon=float(config["epsilon"]),
        integerize=bool(config["integerize"]),
    )
    allocation_rows = allocation_results_to_rows(
        alloc_results,
        relations_universe,
        weight_matrix,
        relation_dom_rng_class=_relation_class_map(canonical_allocation),
    )
    allocation_payload = build_allocation_payload(
        config=config,
        eta_per_group={name: int(value) for name, value in canonical_allocation["eta_per_group"].items()},
        pattern_groups=pattern_groups,
        relations_universe=relations_universe,
        allocation_rows=allocation_rows,
    )

    positive_relations = positive_eta_relations(allocation_rows)
    genericity_relations, genericity_adjacency = extract_relation_submatrix(
        adjacency,
        relations_universe,
        positive_relations,
    )
    genericity_matrix = build_weight_matrix(genericity_adjacency, matrix_mode="adjacency_support")
    genericity_export = matrix_to_nested_json_dict(genericity_relations, genericity_matrix)
    ordered_genericity_export = _order_matrix_like_canonical(genericity_export, canonical_matrix)

    return {
        "allocation": allocation_payload,
        "genericity_matrix": ordered_genericity_export,
        "canonical_allocation": canonical_allocation,
        "canonical_matrix": canonical_matrix,
        "pattern_group_counts": pattern_group_counts(pattern_groups),
        "normalized_allocation_rows_match": normalize_allocation_rows(allocation_rows)
        == normalize_allocation_rows(canonical_allocation["allocations"]),
    }


def run_phase1_replay(repo_root: str | Path, run_dir: str | Path) -> dict[str, Any]:
    """Materialize Phase I replay exports under the pipeline run directory."""
    repo_root = Path(repo_root).resolve()
    run_dir = Path(run_dir)
    replay_dir = run_dir / PHASE1_REPLAY_DIRNAME
    allocation_out = replay_dir / ALLOCATION_OUT_NAME
    matrix_out = replay_dir / MATRIX_OUT_NAME
    report_out = replay_dir / REPORT_OUT_NAME
    summary_out = replay_dir / SUMMARY_OUT_NAME

    payloads = _compute_replay_payloads(repo_root)
    write_json(allocation_out, payloads["allocation"])
    write_json(matrix_out, payloads["genericity_matrix"])

    canonical_allocation_path = repo_root / CANONICAL_ALLOCATION_PATH
    canonical_matrix_path = repo_root / CANONICAL_GENERICITY_MATRIX_PATH
    allocation_hash = sha256_file(allocation_out)
    canonical_allocation_hash = sha256_file(canonical_allocation_path)
    matrix_hash = sha256_file(matrix_out)
    canonical_matrix_hash = sha256_file(canonical_matrix_path)

    allocation_matches_exactly = payloads["allocation"] == payloads["canonical_allocation"]
    matrix_relation_set_matches = set(payloads["genericity_matrix"]) == set(payloads["canonical_matrix"])
    matrix_content_matches = payloads["genericity_matrix"] == payloads["canonical_matrix"]
    pattern_counts_match = payloads["pattern_group_counts"] == EXPECTED_GROUP_COUNTS

    overall_status = "passed"
    mismatches: list[str] = []
    if not allocation_matches_exactly:
        mismatches.append("allocation_exact_json")
    if not payloads["normalized_allocation_rows_match"]:
        mismatches.append("allocation_normalized_rows")
    if not matrix_relation_set_matches:
        mismatches.append("genericity_matrix_relation_set")
    if not matrix_content_matches:
        mismatches.append("genericity_matrix_content")
    if not pattern_counts_match:
        mismatches.append("pattern_group_counts")
    if mismatches:
        overall_status = "failed"

    report = {
        "schema_version": "phase1-run-scoped-replay-report-v1",
        "created_by": "src/kg_pipeline/orchestration/phase1_replay.py",
        "mode": "replay-frozen",
        "status": overall_status,
        "inputs": {
            "hop_support": str(HOP_SUPPORT_PATH),
            "composition": str(COMPOSITION_PATH),
            "canonical_allocation": str(CANONICAL_ALLOCATION_PATH),
            "canonical_genericity_matrix": str(CANONICAL_GENERICITY_MATRIX_PATH),
        },
        "outputs": {
            "allocation": str(allocation_out),
            "genericity_support_matrix": str(matrix_out),
            "report": str(report_out),
            "summary": str(summary_out),
        },
        "allocation": {
            "replayed_sha256": allocation_hash,
            "canonical_sha256": canonical_allocation_hash,
            "matches_exactly": allocation_matches_exactly,
            "normalized_rows_match": payloads["normalized_allocation_rows_match"],
        },
        "genericity_support_matrix": {
            "replayed_sha256": matrix_hash,
            "canonical_sha256": canonical_matrix_hash,
            "relation_set_matches": matrix_relation_set_matches,
            "content_matches": matrix_content_matches,
        },
        "pattern_group_counts": payloads["pattern_group_counts"],
        "expected_pattern_group_counts": EXPECTED_GROUP_COUNTS,
        "pattern_group_counts_match": pattern_counts_match,
        "mismatches": mismatches,
        "notes": [
            "Canonical allocation and genericity matrix files were read for comparison only.",
            "Replay outputs were written only under the pipeline run directory.",
            "No WDQS, LLM, SLURM, or graph construction path is used by this replay."
        ],
    }
    write_json(report_out, report)
    summary_out.write_text(_summary_markdown(report), encoding="utf-8")
    return report


def load_phase1_replay_report(run_dir: str | Path) -> dict[str, Any]:
    report_path = Path(run_dir) / PHASE1_REPLAY_DIRNAME / REPORT_OUT_NAME
    if not report_path.is_file():
        raise FileNotFoundError(f"Phase I replay report not found: {report_path}")
    return load_json(report_path)


def _summary_markdown(report: dict[str, Any]) -> str:
    counts = report["pattern_group_counts"]
    allocation = report["allocation"]
    matrix = report["genericity_support_matrix"]
    mismatches = report.get("mismatches") or []
    mismatch_text = "none" if not mismatches else ", ".join(str(item) for item in mismatches)
    return f"""# Phase I Run-Scoped Replay Summary

Status: `{report['status']}`

## Pattern Groups

| Pattern | Count |
| --- | ---: |
| symmetric | {counts.get('symmetric')} |
| anti_symmetric | {counts.get('anti_symmetric')} |
| inverse | {counts.get('inverse')} |
| composition | {counts.get('composition')} |

## Allocation Export

- Replayed hash: `{allocation['replayed_sha256']}`
- Canonical hash: `{allocation['canonical_sha256']}`
- Exact JSON match: `{str(allocation['matches_exactly']).lower()}`
- Normalized rows match: `{str(allocation['normalized_rows_match']).lower()}`

## Genericity Support Matrix Export

- Replayed hash: `{matrix['replayed_sha256']}`
- Canonical hash: `{matrix['canonical_sha256']}`
- Relation set match: `{str(matrix['relation_set_matches']).lower()}`
- Content match: `{str(matrix['content_matches']).lower()}`

## Mismatches

{mismatch_text}

The replay wrote outputs only under the pipeline run directory and did not overwrite canonical Phase I artifacts.
"""
