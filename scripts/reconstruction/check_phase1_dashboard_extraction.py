#!/usr/bin/env python3
"""Golden-master check for extracted Phase I dashboard logic.

This script uses frozen local artifacts only. It does not query WDQS, call LLMs,
generate graphs, or import Streamlit.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
# The local environment has an incompatible optional pyarrow build with NumPy 2.
# Pandas handles missing pyarrow cleanly, so hide only this optional backend for
# this read-only validation script to keep the pass/fail output deterministic.
sys.modules.setdefault("pyarrow", None)

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.phase1.allocation_export import (  # noqa: E402
    allocation_results_to_rows,
    normalize_allocation_rows,
    positive_eta_relations,
    run_phase3_allocation,
)
from src.kg_pipeline.phase1.genericity_matrix import (  # noqa: E402
    build_square_adjacency_matrix,
    build_weight_matrix,
    extract_relation_submatrix,
    matrix_to_nested_json_dict,
)
from src.kg_pipeline.phase1.pattern_evidence import (  # noqa: E402
    load_composition_verified_compact,
    load_pair_counts,
)
from src.kg_pipeline.phase1.pattern_groups import (  # noqa: E402
    build_pattern_groups,
    filter_composition_candidates,
    filter_pair_universe,
    pattern_group_counts,
    select_anti_symmetric_candidates,
    select_inverse_candidates,
    select_symmetric_candidates,
    unique_preserve,
)


HOP_SUPPORT_PATH = REPO_ROOT / "data/processed/hop_support_v3/hop_support_v3_final_output_patched_from_v2.jsonl"
COMPOSITION_PATH = (
    REPO_ROOT
    / "data/processed/hop_support_v3/min8_hop_support_v3_with_compatible_targets_dom_rng_v1.composition_verified.compact.jsonl"
)
ALLOCATION_PATH = REPO_ROOT / "src/Pruning graph/bidirectional_allocation_results5k.json"
GENERICITY_MATRIX_CANDIDATES = [
    REPO_ROOT / "archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json",
    REPO_ROOT / "src/Pruning graph/genericity_support_matrix.adjacency_support.json",
    REPO_ROOT / "src/kg_builder/input/genericity_support_matrix.adjacency_support.json",
]

EXPECTED_GROUP_COUNTS = {
    "symmetric": 18,
    "anti_symmetric": 66,
    "inverse": 44,
    "composition": 26,
}
COMPOSITION_MIN_EXAMINED = 50
COMPOSITION_MIN_SHORTCUTS = 1
WILSON_Z_95 = 1.959963984540054
ETA_EXPECTED_ABS_TOL = 1e-9


def require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"required frozen input not found: {path.relative_to(REPO_ROOT)}")


def load_json(path: Path):
    require_file(path)
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def find_genericity_matrix_path() -> Path:
    for path in GENERICITY_MATRIX_CANDIDATES:
        if path.is_file():
            return path
    candidates = "\n".join(f"- {path.relative_to(REPO_ROOT)}" for path in GENERICITY_MATRIX_CANDIDATES)
    raise SystemExit(f"genericity support matrix not found. Checked:\n{candidates}")


def relation_set_by_pattern(allocation: dict) -> dict[str, set[str]]:
    return {pattern: set(relations) for pattern, relations in allocation["pattern_groups"].items()}


def compare_pattern_groups(actual: dict[str, list[str]], expected: dict[str, list[str]]) -> None:
    actual_counts = pattern_group_counts(actual)
    if actual_counts != EXPECTED_GROUP_COUNTS:
        raise SystemExit(f"pattern group counts mismatch: actual={actual_counts}, expected={EXPECTED_GROUP_COUNTS}")

    actual_sets = {pattern: set(relations) for pattern, relations in actual.items()}
    expected_sets = {pattern: set(relations) for pattern, relations in expected.items()}
    mismatches = []
    for pattern in EXPECTED_GROUP_COUNTS:
        missing = sorted(expected_sets[pattern] - actual_sets[pattern])
        extra = sorted(actual_sets[pattern] - expected_sets[pattern])
        if missing or extra:
            mismatches.append({"pattern": pattern, "missing": missing, "extra": extra})
    if mismatches:
        raise SystemExit(f"pattern relation-set mismatch: {json.dumps(mismatches, indent=2)}")


def compare_allocation_rows(actual_rows: list[dict], canonical_rows: list[dict]) -> None:
    actual = normalize_allocation_rows(actual_rows)
    expected = normalize_allocation_rows(canonical_rows)
    if len(actual) != len(expected):
        raise SystemExit(f"allocation row count mismatch: actual={len(actual)}, expected={len(expected)}")

    actual_by_key = {(row["pattern"], row["relation"]): row for row in actual}
    expected_by_key = {(row["pattern"], row["relation"]): row for row in expected}
    if set(actual_by_key) != set(expected_by_key):
        missing = sorted(set(expected_by_key) - set(actual_by_key))
        extra = sorted(set(actual_by_key) - set(expected_by_key))
        raise SystemExit(f"allocation row keys mismatch: missing={missing[:20]}, extra={extra[:20]}")

    mismatches = []
    for key in sorted(expected_by_key):
        a = actual_by_key[key]
        e = expected_by_key[key]
        if a["eta_total"] != e["eta_total"] or a["eta_integer"] != e["eta_integer"]:
            mismatches.append({"key": key, "actual": a, "expected": e})
            continue
        if not math.isclose(a["eta_expected"], e["eta_expected"], rel_tol=0.0, abs_tol=ETA_EXPECTED_ABS_TOL):
            mismatches.append({"key": key, "actual": a, "expected": e})
    if mismatches:
        raise SystemExit(f"allocation row value mismatch: {json.dumps(mismatches[:10], indent=2)}")


def main() -> int:
    for path in [HOP_SUPPORT_PATH, COMPOSITION_PATH, ALLOCATION_PATH]:
        require_file(path)
    genericity_matrix_path = find_genericity_matrix_path()

    allocation = load_json(ALLOCATION_PATH)
    support_matrix = load_json(genericity_matrix_path)
    config = allocation["config"]

    pair_counts = load_pair_counts(HOP_SUPPORT_PATH, only_success=True)
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

    composition_input = load_composition_verified_compact(COMPOSITION_PATH, only_success=True)
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
        raise SystemExit(f"unexpected symmetric/anti-symmetric overlap: {overlap}")
    compare_pattern_groups(pattern_groups, allocation["pattern_groups"])

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

    _, alloc_results = run_phase3_allocation(
        pattern_groups=pattern_groups,
        eta_per_group={name: int(value) for name, value in allocation["eta_per_group"].items()},
        relations_universe=relations_universe,
        adjacency=adjacency,
        matrix_mode=str(config["matrix_mode"]),
        temperature=float(config["temperature"]),
        epsilon=float(config["epsilon"]),
        integerize=bool(config["integerize"]),
    )
    weight_matrix = build_weight_matrix(adjacency, matrix_mode=str(config["matrix_mode"]))
    allocation_rows = allocation_results_to_rows(alloc_results, relations_universe, weight_matrix)
    compare_allocation_rows(allocation_rows, allocation["allocations"])

    positive_relations = positive_eta_relations(allocation_rows)
    genericity_relations, genericity_adjacency = extract_relation_submatrix(
        adjacency,
        relations_universe,
        positive_relations,
    )
    genericity_matrix = build_weight_matrix(genericity_adjacency, matrix_mode="adjacency_support")
    genericity_export = matrix_to_nested_json_dict(genericity_relations, genericity_matrix)

    if set(genericity_export) != set(support_matrix):
        missing = sorted(set(support_matrix) - set(genericity_export))
        extra = sorted(set(genericity_export) - set(support_matrix))
        raise SystemExit(f"genericity matrix relation set mismatch: missing={missing[:20]}, extra={extra[:20]}")

    print("Phase I dashboard extraction golden-master check passed.")
    print(f"hop_support_input={HOP_SUPPORT_PATH.relative_to(REPO_ROOT)}")
    print(f"composition_input={COMPOSITION_PATH.relative_to(REPO_ROOT)}")
    print(f"allocation_input={ALLOCATION_PATH.relative_to(REPO_ROOT)}")
    print(f"genericity_matrix_input={genericity_matrix_path.relative_to(REPO_ROOT)}")
    print(f"pattern_group_counts={json.dumps(pattern_group_counts(pattern_groups), sort_keys=True)}")
    print("allocation_relation_sets_match=true")
    print("allocation_rows_match=true")
    print("genericity_matrix_relation_set_match=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
