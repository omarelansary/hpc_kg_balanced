#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/00_common.sh"

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
  shift
fi
[[ "$#" -eq 0 ]] || die "usage: $0 [--force]"

cd "${REPO_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python}"
REBUILD_DIR="artifacts/final_graph/selected_final_graph/rebuild"
OUT="${REBUILD_DIR}/stage5_to_B0_chain_verification.json"

RUN_DIR="archive/hetzner_version/runs/prod_refine_20260315_180520"
STAGE4_CORE_GRAPH="${RUN_DIR}/stage04_core_graph/core_graph_triples.jsonl"

STAGE5_DIR="${RUN_DIR}/stage05_repair"
STAGE5_SUMMARY="${STAGE5_DIR}/summary.json"
STAGE5_REPAIR_TRIPLES="${STAGE5_DIR}/repair_triples.jsonl"

STAGE6_GRAPH="${RUN_DIR}/stage06_refine_graph/refined_graph_triples.jsonl"
STAGE6_SUMMARY="${RUN_DIR}/stage06_refine_graph/summary.json"
STAGE6_REFINEMENT_MOVES="${RUN_DIR}/stage06_refine_graph/refinement_moves.jsonl"

STAGE6_TO_B0_VERIFICATION="artifacts/final_graph/selected_final_graph/rebuild/stage6_to_B0_chain_verification.json"
STAGE6_TO_B0_DOC="docs/reconstruction/27_stage6_to_B0_chain_verification.md"

for path in \
  "${STAGE4_CORE_GRAPH}" \
  "${STAGE5_SUMMARY}" \
  "${STAGE5_REPAIR_TRIPLES}" \
  "${STAGE6_GRAPH}" \
  "${STAGE6_SUMMARY}" \
  "${STAGE6_REFINEMENT_MOVES}" \
  "${STAGE6_TO_B0_VERIFICATION}" \
  "${STAGE6_TO_B0_DOC}"; do
  require_file "${path}"
done

if [[ "${FORCE}" -ne 1 ]]; then
  [[ ! -e "${OUT}" ]] || die "refusing to overwrite ${OUT}; rerun with --force"
fi

safe_mkdir "${REBUILD_DIR}"

"${PYTHON_BIN}" - \
  "${OUT}" \
  "${RUN_DIR}" \
  "${STAGE4_CORE_GRAPH}" \
  "${STAGE5_DIR}" \
  "${STAGE5_SUMMARY}" \
  "${STAGE5_REPAIR_TRIPLES}" \
  "${STAGE6_GRAPH}" \
  "${STAGE6_SUMMARY}" \
  "${STAGE6_REFINEMENT_MOVES}" \
  "${STAGE6_TO_B0_VERIFICATION}" \
  "${STAGE6_TO_B0_DOC}" <<'PY'
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

(
    out_path,
    run_dir,
    stage4_core_graph,
    stage5_dir,
    stage5_summary,
    stage5_repair_triples,
    stage6_graph,
    stage6_summary,
    stage6_refinement_moves,
    stage6_to_b0_verification,
    stage6_to_b0_doc,
) = [Path(x) for x in sys.argv[1:]]

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)

def triple_from_obj(obj):
    if isinstance(obj, dict):
        for keys in (("h", "r", "t"), ("head", "relation", "tail"), ("subject", "predicate", "object")):
            if all(k in obj for k in keys):
                vals = tuple(str(obj[k]) for k in keys)
                if all(vals):
                    return vals
        if "triple" in obj and isinstance(obj["triple"], list) and len(obj["triple"]) >= 3:
            vals = tuple(str(x) for x in obj["triple"][:3])
            if all(vals):
                return vals
    if isinstance(obj, list) and len(obj) >= 3:
        vals = tuple(str(x) for x in obj[:3])
        if all(vals):
            return vals
    return None

def read_jsonl_graph(path: Path) -> dict:
    rows = 0
    parse_errors = 0
    hrt_records = 0
    triples = set()
    relations = set()
    first_keys = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows += 1
            try:
                obj = json.loads(line)
            except Exception:
                parse_errors += 1
                continue
            if not first_keys and isinstance(obj, dict):
                first_keys = list(obj.keys())
            triple = triple_from_obj(obj)
            if triple:
                hrt_records += 1
                triples.add(triple)
                relations.add(triple[1])
    return {
        "path": str(path),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "row_count": rows,
        "jsonl_parse_ok": parse_errors == 0,
        "parse_error_count": parse_errors,
        "first_record_keys": first_keys,
        "h_r_t_like_record_count": hrt_records,
        "unique_triples": len(triples),
        "unique_relations": len(relations),
        "_triples": triples,
    }

def public_graph(info: dict) -> dict:
    return {k: v for k, v in info.items() if not k.startswith("_")}

def byte_equal(left: Path, right: Path) -> bool:
    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as a, right.open("rb") as b:
        while True:
            ca = a.read(1024 * 1024)
            cb = b.read(1024 * 1024)
            if ca != cb:
                return False
            if not ca:
                return True

def find_stage5_full_graph_candidates(stage5_dir: Path) -> list[Path]:
    patterns = ("graph", "triples", "refined", "repaired", "selected")
    candidates = []
    for path in sorted(stage5_dir.rglob("*.jsonl")):
        name = path.name.lower()
        if path == stage5_repair_triples:
            continue
        if ("graph" in name and "triples" in name) or any(term in name for term in ("refined", "repaired", "selected")):
            candidates.append(path)
    return candidates

stage4 = read_jsonl_graph(stage4_core_graph)
stage5_delta = read_jsonl_graph(stage5_repair_triples)
stage6 = read_jsonl_graph(stage6_graph)

stage5_summary_data = load_json(stage5_summary)
stage6_summary_data = load_json(stage6_summary)
stage6_to_b0_data = load_json(stage6_to_b0_verification)

stage5_full_candidates = find_stage5_full_graph_candidates(stage5_dir)
stage5_full_candidate_profiles = [public_graph(read_jsonl_graph(path)) for path in stage5_full_candidates]
if stage5_full_candidates:
    stage5_full_graph_status = "full_graph_candidate_found_needs_review"
elif stage5_delta["row_count"] == 0:
    stage5_full_graph_status = "no_full_graph_artifact_found_empty_repair_delta"
else:
    stage5_full_graph_status = "no_full_graph_artifact_found_nonempty_repair_delta_ambiguous"

objective_before = stage6_summary_data.get("objective_before")
objective_after = stage6_summary_data.get("objective_after")

checks = {
    "stage5_dir_exists": stage5_dir.is_dir(),
    "stage5_repair_triples_exists": stage5_repair_triples.exists(),
    "stage5_repair_triples_rows_0": stage5_delta["row_count"] == 0,
    "stage5_summary_missing_relation_repairs_0": stage5_summary_data.get("missing_relation_repairs") == 0,
    "stage5_summary_component_merge_repairs_0": stage5_summary_data.get("component_merge_repairs") == 0,
    "stage5_summary_auxiliary_repair_disabled": stage5_summary_data.get("auxiliary_repair_enabled") is False,
    "stage5_full_graph_artifact_absent": len(stage5_full_candidates) == 0,
    "stage4_core_graph_rows_18513": stage4["row_count"] == 18513,
    "stage4_core_graph_unique_triples_18513": stage4["unique_triples"] == 18513,
    "stage6_graph_rows_18513": stage6["row_count"] == 18513,
    "stage6_graph_unique_triples_18513": stage6["unique_triples"] == 18513,
    "stage4_subset_of_stage6": stage4["_triples"] <= stage6["_triples"],
    "stage6_subset_of_stage4": stage6["_triples"] <= stage4["_triples"],
    "stage4_stage6_set_difference_empty": len(stage4["_triples"] - stage6["_triples"]) == 0 and len(stage6["_triples"] - stage4["_triples"]) == 0,
    "stage4_stage6_sha256_equal": stage4["sha256"] == stage6["sha256"],
    "stage4_stage6_byte_equal": byte_equal(stage4_core_graph, stage6_graph),
    "stage6_summary_accepted_moves_0": stage6_summary_data.get("accepted_moves") == 0,
    "stage6_summary_total_proposals_evaluated_0": stage6_summary_data.get("total_proposals_evaluated") == 0,
    "stage6_summary_termination_no_addition_candidates": stage6_summary_data.get("termination_reason") == "no_addition_candidates",
    "stage6_refinement_moves_empty": stage6_refinement_moves.stat().st_size == 0 and read_jsonl_graph(stage6_refinement_moves)["row_count"] == 0,
    "stage6_objective_before_equals_after": objective_before == objective_after,
    "stage6_to_B0_previous_verification_passed": stage6_to_b0_data.get("overall_pass") is True,
}

stage5_to_stage6_relationship = {
    "stage5_full_graph_status": stage5_full_graph_status,
    "verified_stage5_repair_delta_noop": all(
        checks[k]
        for k in (
            "stage5_repair_triples_rows_0",
            "stage5_summary_missing_relation_repairs_0",
            "stage5_summary_component_merge_repairs_0",
            "stage5_summary_auxiliary_repair_disabled",
        )
    ),
    "verified_stage6_refinement_noop": all(
        checks[k]
        for k in (
            "stage6_summary_accepted_moves_0",
            "stage6_summary_total_proposals_evaluated_0",
            "stage6_summary_termination_no_addition_candidates",
            "stage6_refinement_moves_empty",
            "stage6_objective_before_equals_after",
        )
    ),
    "verified_stage4_to_stage6_identity": all(
        checks[k]
        for k in (
            "stage4_subset_of_stage6",
            "stage6_subset_of_stage4",
            "stage4_stage6_set_difference_empty",
            "stage4_stage6_sha256_equal",
            "stage4_stage6_byte_equal",
        )
    ),
    "interpretation": (
        "No full Stage5 graph artifact was found. Stage5 repair evidence is an empty repair delta, "
        "and Stage6 is byte-identical to the Stage4 core graph with zero accepted refinement moves. "
        "Thus the Stage5 repair and Stage6 refinement steps are verified as no-op transitions relative "
        "to the last full graph artifact, Stage4 core_graph_triples.jsonl."
    ),
}

hash_inputs = {
    "stage4_core_graph": stage4_core_graph,
    "stage5_summary": stage5_summary,
    "stage5_repair_triples": stage5_repair_triples,
    "stage6_refined_graph": stage6_graph,
    "stage6_summary": stage6_summary,
    "stage6_refinement_moves": stage6_refinement_moves,
    "stage6_to_B0_verification": stage6_to_b0_verification,
    "stage6_to_B0_doc": stage6_to_b0_doc,
    "this_verification_script": Path("scripts/reconstruction/06_verify_stage5_to_B0_chain.sh"),
}

overall_pass = (
    checks["stage5_dir_exists"]
    and checks["stage5_repair_triples_exists"]
    and stage5_to_stage6_relationship["verified_stage5_repair_delta_noop"]
    and stage5_to_stage6_relationship["verified_stage6_refinement_noop"]
    and stage5_to_stage6_relationship["verified_stage4_to_stage6_identity"]
    and checks["stage6_to_B0_previous_verification_passed"]
)

verification = {
    "created_on": datetime.now(timezone.utc).isoformat(),
    "created_by": "scripts/reconstruction/06_verify_stage5_to_B0_chain.sh",
    "scope": "Read-only verification of Stage5 repair/no-op and Stage6 -> B0 evidence chain.",
    "overall_pass": overall_pass,
    "stage5_resolution_status": stage5_full_graph_status,
    "checks": checks,
    "hashes": {role: {"path": str(path), "sha256": sha256(path), "size_bytes": path.stat().st_size} for role, path in hash_inputs.items()},
    "stage5_full_graph_candidates": stage5_full_candidate_profiles,
    "stage4_core_graph": public_graph(stage4),
    "stage5_repair_delta": public_graph(stage5_delta),
    "stage5_summary": stage5_summary_data,
    "stage6_refined_graph": public_graph(stage6),
    "stage6_summary": stage6_summary_data,
    "stage5_to_stage6_relationship": stage5_to_stage6_relationship,
    "set_relationships": {
        "stage4_overlap_with_stage6": len(stage4["_triples"] & stage6["_triples"]),
        "stage4_minus_stage6_triples": len(stage4["_triples"] - stage6["_triples"]),
        "stage6_minus_stage4_triples": len(stage6["_triples"] - stage4["_triples"]),
        "stage5_repair_delta_unique_triples": stage5_delta["unique_triples"],
    },
    "previous_stage6_to_B0_verification": {
        "path": str(stage6_to_b0_verification),
        "sha256": sha256(stage6_to_b0_verification),
        "overall_pass": stage6_to_b0_data.get("overall_pass"),
    },
    "notes": [
        "No Stage4, Stage5, Stage6, Stage7, Stage11, Stage12, B0, or allocation artifact was modified.",
        "No graph was generated.",
        "No WDQS or LLM call was made.",
        "Stage5 has no full graph artifact in the archive; the verified evidence is an empty repair delta and Stage4-to-Stage6 identity.",
        "This narrows the Stage5/Stage6 portion of the historical hash chain, but does not establish Stage1-to-Stage4 provenance or full Phase I reproducibility.",
    ],
}

out_path.write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(f"stage5_to_B0_chain_verification={out_path}")
print(f"overall_pass={verification['overall_pass']}")
print(f"stage5_resolution_status={stage5_full_graph_status}")
for key, value in checks.items():
    print(f"{key}={value}")

if not verification["overall_pass"]:
    raise SystemExit(1)
PY
