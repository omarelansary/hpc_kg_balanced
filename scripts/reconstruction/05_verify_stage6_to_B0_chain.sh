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
OUT="${REBUILD_DIR}/stage6_to_B0_chain_verification.json"

EXPECTED_STAGE6_GRAPH="archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/refined_graph_triples.jsonl"
STAGE6_RUN_DIR="archive/hetzner_version/runs/prod_refine_20260315_180520"
STAGE6_GRAPH="${EXPECTED_STAGE6_GRAPH}"
if [[ ! -f "${STAGE6_GRAPH}" ]]; then
  STAGE6_GRAPH="$(find "${STAGE6_RUN_DIR}" -type f \( -path '*stage06*' -o -path '*stage6*' \) \( -name '*graph*triples*.jsonl' -o -name '*refined*.jsonl' \) | sort | head -1)"
  [[ -n "${STAGE6_GRAPH}" ]] || die "could not find Stage6 refined graph under ${STAGE6_RUN_DIR}"
fi

STAGE6_SUMMARY="archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/summary.json"
STAGE6_REFINEMENT_MOVES="archive/hetzner_version/runs/prod_refine_20260315_180520/stage06_refine_graph/refinement_moves.jsonl"

STAGE7_GRAPH="archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/filtered_graph_triples.jsonl"
STAGE7_MANIFEST="archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/manifest.json"
STAGE7_SUMMARY="archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/summary.json"
STAGE7_PROGRESS="archive/hetzner_version/runs/prod_refine_20260315_180520/stage07_filtering_eta_aware_prod/progress.json"
STAGE7_LOG="archive/hetzner_version/logs/eta_aware_component_filter_prod.out"

STAGE11_MANIFEST="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/manifest.json"
STAGE11_REPORT="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/report.json"
STAGE11_STATE="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/state.json"
STAGE11_GRAPH_OUTPUT="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/graph_output.jsonl"

STAGE12_MANIFEST="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/manifest.json"
STAGE12_REPORT="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/report.json"
STAGE12_STATE="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/state.json"
STAGE12_GRAPH_OUTPUT="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/graph_output.jsonl"
B0_GRAPH="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv"

PATH_TRANSLATION_V3="artifacts/final_graph/selected_final_graph/rebuild/path_translation_manifest.v3.json"
STAGE7_TO_B0_VERIFICATION="artifacts/final_graph/selected_final_graph/rebuild/stage7_to_B0_chain_verification.json"
STAGE7_RESOLUTION_DOC="docs/reconstruction/25_pre_stage11_input_mapping_hetzner_resolution.md"
STAGE7_TO_B0_DOC="docs/reconstruction/26_stage7_to_B0_chain_verification.md"

for path in \
  "${STAGE6_GRAPH}" \
  "${STAGE6_SUMMARY}" \
  "${STAGE6_REFINEMENT_MOVES}" \
  "${STAGE7_GRAPH}" \
  "${STAGE7_MANIFEST}" \
  "${STAGE7_SUMMARY}" \
  "${STAGE7_PROGRESS}" \
  "${STAGE7_LOG}" \
  "${STAGE11_MANIFEST}" \
  "${STAGE11_REPORT}" \
  "${STAGE11_STATE}" \
  "${STAGE11_GRAPH_OUTPUT}" \
  "${STAGE12_MANIFEST}" \
  "${STAGE12_REPORT}" \
  "${STAGE12_STATE}" \
  "${STAGE12_GRAPH_OUTPUT}" \
  "${B0_GRAPH}" \
  "${PATH_TRANSLATION_V3}" \
  "${STAGE7_TO_B0_VERIFICATION}" \
  "${STAGE7_RESOLUTION_DOC}" \
  "${STAGE7_TO_B0_DOC}"; do
  require_file "${path}"
done

if [[ "${FORCE}" -ne 1 ]]; then
  [[ ! -e "${OUT}" ]] || die "refusing to overwrite ${OUT}; rerun with --force"
fi

safe_mkdir "${REBUILD_DIR}"

"${PYTHON_BIN}" - \
  "${OUT}" \
  "${STAGE6_GRAPH}" \
  "${STAGE6_SUMMARY}" \
  "${STAGE6_REFINEMENT_MOVES}" \
  "${STAGE7_GRAPH}" \
  "${STAGE7_MANIFEST}" \
  "${STAGE7_SUMMARY}" \
  "${STAGE7_PROGRESS}" \
  "${STAGE7_LOG}" \
  "${STAGE11_MANIFEST}" \
  "${STAGE11_REPORT}" \
  "${STAGE11_STATE}" \
  "${STAGE11_GRAPH_OUTPUT}" \
  "${STAGE12_MANIFEST}" \
  "${STAGE12_REPORT}" \
  "${STAGE12_STATE}" \
  "${STAGE12_GRAPH_OUTPUT}" \
  "${B0_GRAPH}" \
  "${PATH_TRANSLATION_V3}" \
  "${STAGE7_TO_B0_VERIFICATION}" \
  "${STAGE7_RESOLUTION_DOC}" \
  "${STAGE7_TO_B0_DOC}" <<'PY'
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

args = [Path(x) for x in sys.argv[1:]]
(
    out_path,
    stage6_graph,
    stage6_summary,
    stage6_refinement_moves,
    stage7_graph,
    stage7_manifest,
    stage7_summary,
    stage7_progress,
    stage7_log,
    stage11_manifest,
    stage11_report,
    stage11_state,
    stage11_graph_output,
    stage12_manifest,
    stage12_report,
    stage12_state,
    stage12_graph_output,
    b0_graph,
    path_translation_v3,
    stage7_to_b0_verification,
    stage7_resolution_doc,
    stage7_to_b0_doc,
) = args

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

def read_csv_graph(path: Path) -> dict:
    rows = 0
    triples = set()
    relations = set()
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        for row in reader:
            rows += 1
            if all(k in row and row[k] for k in ("h", "r", "t")):
                triple = (str(row["h"]), str(row["r"]), str(row["t"]))
                triples.add(triple)
                relations.add(triple[1])
    return {
        "path": str(path),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "row_count": rows,
        "fieldnames": fieldnames,
        "has_h_r_t_fields": {"h", "r", "t"}.issubset(set(fieldnames)),
        "unique_triples": len(triples),
        "unique_relations": len(relations),
        "_triples": triples,
    }

stage6 = read_jsonl_graph(stage6_graph)
stage7 = read_jsonl_graph(stage7_graph)
stage11 = read_jsonl_graph(stage11_graph_output)
stage12 = read_jsonl_graph(stage12_graph_output)
b0 = read_csv_graph(b0_graph)

stage6_summary_data = load_json(stage6_summary)
stage7_manifest_data = load_json(stage7_manifest)
stage7_summary_data = load_json(stage7_summary)
stage7_progress_data = load_json(stage7_progress)
stage11_report_data = load_json(stage11_report)
stage11_state_data = load_json(stage11_state)
stage12_report_data = load_json(stage12_report)
stage12_state_data = load_json(stage12_state)
path_translation_data = load_json(path_translation_v3)
stage7_to_b0_data = load_json(stage7_to_b0_verification)
stage7_log_text = stage7_log.read_text(encoding="utf-8", errors="replace")

stage11_added_core = set()
for item in stage11_state_data.get("added_core_triples", []):
    triple = triple_from_obj(item)
    if triple:
        stage11_added_core.add(triple)

stage12_added_path = set()
for item in stage12_state_data.get("added_path_triples", []):
    triple = triple_from_obj(item)
    if triple:
        stage12_added_path.add(triple)

stage12_expected_unique = (
    stage12_report_data.get("final_graph", {}).get("unique_triples")
    or stage12_report_data.get("original_graph", {}).get("unique_triples", 0)
    + stage12_report_data.get("added_path_triples_count", stage12_report_data.get("triples_added", 0))
)

log_checks = {
    "loaded_18513_prefilter_rows": "Loaded 18513 pre-filter rows" in stage7_log_text,
    "loaded_from_stage06_refined_graph": "stage06_refine_graph/refined_graph_triples.jsonl" in stage7_log_text,
    "kept_triples_17965": "kept_triples=17965" in stage7_log_text or '"kept_triples": 17965' in stage7_log_text,
    "removed_triples_548": "removed_triples_estimate=548" in stage7_log_text or '"removed_triples": 548' in stage7_log_text,
    "run_completed_successfully": "Run completed successfully" in stage7_log_text,
}

hash_inputs = {
    "stage6_refined_graph": stage6_graph,
    "stage6_summary": stage6_summary,
    "stage6_refinement_moves": stage6_refinement_moves,
    "stage7_filtered_graph": stage7_graph,
    "stage7_manifest": stage7_manifest,
    "stage7_summary": stage7_summary,
    "stage7_progress": stage7_progress,
    "stage7_log": stage7_log,
    "stage11_manifest": stage11_manifest,
    "stage11_report": stage11_report,
    "stage11_state": stage11_state,
    "stage11_graph_output": stage11_graph_output,
    "stage12_manifest": stage12_manifest,
    "stage12_report": stage12_report,
    "stage12_state": stage12_state,
    "stage12_graph_output": stage12_graph_output,
    "B0_largest_component": b0_graph,
    "path_translation_manifest_v3": path_translation_v3,
    "stage7_to_B0_verification": stage7_to_b0_verification,
    "stage7_resolution_doc": stage7_resolution_doc,
    "stage7_to_B0_doc": stage7_to_b0_doc,
    "this_verification_script": Path("scripts/reconstruction/05_verify_stage6_to_B0_chain.sh"),
}

checks = {
    "stage6_graph_exists": stage6_graph.exists(),
    "stage6_row_count_18513": stage6["row_count"] == 18513,
    "stage6_unique_triples_18513": stage6["unique_triples"] == 18513,
    "stage6_has_h_r_t_like_fields": {"h", "r", "t"}.issubset(set(stage6["first_record_keys"])),
    "stage7_unique_triples_17965": stage7["unique_triples"] == 17965,
    "stage7_subset_of_stage6": stage7["_triples"] <= stage6["_triples"],
    "stage6_minus_stage7_unique_triples_548": len(stage6["_triples"] - stage7["_triples"]) == 548,
    "stage7_summary_input_triples_18513": stage7_summary_data.get("input_triples") == 18513,
    "stage7_summary_kept_triples_17965": stage7_summary_data.get("kept_triples") == 17965,
    "stage7_summary_removed_triples_548": stage7_summary_data.get("removed_triples") == 548,
    "stage7_summary_prefilter_source_stage06": stage7_summary_data.get("prefilter_source") == "stage06_refine_graph",
    "stage7_progress_kept_triples_17965": stage7_progress_data.get("kept_triples_estimate") == 17965,
    "stage7_progress_removed_triples_548": stage7_progress_data.get("removed_triples_estimate") == 548,
    "stage7_log_supports_transition": all(log_checks.values()),
    "stage7_to_B0_previous_verification_passed": stage7_to_b0_data.get("overall_pass") is True,
    "stage11_graph_output_unique_triples_24670": stage11["unique_triples"] == 24670,
    "stage11_added_core_unique_triples_6705": len(stage11_added_core) == 6705,
    "stage7_subset_of_stage11_graph_output": stage7["_triples"] <= stage11["_triples"],
    "stage11_output_minus_stage7_equals_added_core": (stage11["_triples"] - stage7["_triples"]) == stage11_added_core,
    "stage12_graph_output_matches_report_expected_unique_triples": stage12["unique_triples"] == stage12_expected_unique,
    "stage12_graph_output_unique_triples_24715": stage12["unique_triples"] == 24715,
    "stage12_added_path_unique_triples_45": len(stage12_added_path) == 45,
    "stage11_subset_of_stage12_graph_output": stage11["_triples"] <= stage12["_triples"],
    "stage12_output_minus_stage11_equals_added_path_triples": (stage12["_triples"] - stage11["_triples"]) == stage12_added_path,
    "B0_unique_triples_24683": b0["unique_triples"] == 24683,
    "B0_subset_of_stage12_graph_output": b0["_triples"] <= stage12["_triples"],
    "path_translation_status_resolved_strong": path_translation_data.get("investigation_status") == "resolved_strong",
}

def public_graph(info: dict) -> dict:
    return {k: v for k, v in info.items() if not k.startswith("_")}

verification = {
    "created_on": datetime.now(timezone.utc).isoformat(),
    "created_by": "scripts/reconstruction/05_verify_stage6_to_B0_chain.sh",
    "scope": "Read-only verification of the Stage6 -> Stage7 -> Stage11 -> Stage12 -> B0 evidence chain.",
    "overall_pass": all(checks.values()),
    "checks": checks,
    "stage7_log_checks": log_checks,
    "hashes": {role: {"path": str(path), "sha256": sha256(path), "size_bytes": path.stat().st_size} for role, path in hash_inputs.items()},
    "stage6_refined_graph": public_graph(stage6),
    "stage6_summary_extract": stage6_summary_data,
    "stage7_filtered_graph": public_graph(stage7),
    "stage7_manifest_extract": {
        "script": stage7_manifest_data.get("script"),
        "run_dir": stage7_manifest_data.get("run_dir"),
        "out_dir": stage7_manifest_data.get("out_dir"),
        "status": stage7_manifest_data.get("status"),
        "started_at": stage7_manifest_data.get("started_at"),
        "completed_at": stage7_manifest_data.get("completed_at"),
        "args": stage7_manifest_data.get("args"),
    },
    "stage7_summary_extract": {
        "input_triples": stage7_summary_data.get("input_triples"),
        "kept_triples": stage7_summary_data.get("kept_triples"),
        "removed_triples": stage7_summary_data.get("removed_triples"),
        "prefilter_source": stage7_summary_data.get("prefilter_source"),
        "input_component_count": stage7_summary_data.get("input_component_count"),
        "kept_component_count": stage7_summary_data.get("kept_component_count"),
        "removed_component_count": stage7_summary_data.get("removed_component_count"),
        "realized_relations_before": stage7_summary_data.get("realized_relations_before"),
        "realized_relations_after": stage7_summary_data.get("realized_relations_after"),
        "total_prefilter_selected": stage7_summary_data.get("total_prefilter_selected"),
        "total_postfilter_selected": stage7_summary_data.get("total_postfilter_selected"),
    },
    "stage7_progress_extract": {
        "phase": stage7_progress_data.get("phase"),
        "kept_triples_estimate": stage7_progress_data.get("kept_triples_estimate"),
        "removed_triples_estimate": stage7_progress_data.get("removed_triples_estimate"),
        "note": stage7_progress_data.get("note"),
    },
    "stage11_graph_output": public_graph(stage11),
    "stage11_report_extract": {
        "original_graph": stage11_report_data.get("original_graph"),
        "final_graph": stage11_report_data.get("final_graph"),
        "added_core_triples_count": stage11_report_data.get("added_core_triples_count"),
        "completed": stage11_report_data.get("completed"),
        "successful": stage11_report_data.get("successful"),
    },
    "stage11_state_added_core_unique_triples": len(stage11_added_core),
    "stage12_graph_output": public_graph(stage12),
    "stage12_report_extract": {
        "original_graph": stage12_report_data.get("original_graph"),
        "final_graph": stage12_report_data.get("final_graph"),
        "added_path_triples_count": stage12_report_data.get("added_path_triples_count"),
        "triples_added": stage12_report_data.get("triples_added"),
        "derived_expected_unique_triples": stage12_expected_unique,
        "completed": stage12_report_data.get("completed"),
        "successful": stage12_report_data.get("successful"),
    },
    "stage12_state_added_path_unique_triples": len(stage12_added_path),
    "B0_largest_component": public_graph(b0),
    "set_relationships": {
        "stage7_overlap_with_stage6": len(stage7["_triples"] & stage6["_triples"]),
        "stage6_minus_stage7_triples": len(stage6["_triples"] - stage7["_triples"]),
        "stage7_overlap_with_stage11_graph_output": len(stage7["_triples"] & stage11["_triples"]),
        "stage11_output_minus_stage7_triples": len(stage11["_triples"] - stage7["_triples"]),
        "stage11_overlap_with_stage12_graph_output": len(stage11["_triples"] & stage12["_triples"]),
        "stage12_output_minus_stage11_triples": len(stage12["_triples"] - stage11["_triples"]),
        "B0_overlap_with_stage12_graph_output": len(b0["_triples"] & stage12["_triples"]),
        "stage12_output_minus_B0_triples": len(stage12["_triples"] - b0["_triples"]),
    },
    "path_translation_manifest_v3": {
        "path": str(path_translation_v3),
        "sha256": sha256(path_translation_v3),
        "investigation_status": path_translation_data.get("investigation_status"),
        "resolved_local_equivalent": path_translation_data.get("resolved_local_equivalent", {}).get("path"),
        "resolved_local_equivalent_sha256": path_translation_data.get("resolved_local_equivalent", {}).get("sha256"),
    },
    "previous_stage7_to_B0_verification": {
        "path": str(stage7_to_b0_verification),
        "sha256": sha256(stage7_to_b0_verification),
        "overall_pass": stage7_to_b0_data.get("overall_pass"),
    },
    "notes": [
        "No Stage6, Stage7, Stage11, Stage12, B0, or allocation artifact was modified.",
        "No graph was generated.",
        "No WDQS or LLM call was made.",
        "This narrows the Stage6-to-B0 historical hash chain; it does not prove Stage1-to-Stage6 provenance or full Phase I end-to-end reproducibility.",
    ],
}

out_path.write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(f"stage6_to_B0_chain_verification={out_path}")
print(f"overall_pass={verification['overall_pass']}")
for key, value in checks.items():
    print(f"{key}={value}")

if not verification["overall_pass"]:
    raise SystemExit(1)
PY
