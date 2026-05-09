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
OUT="${REBUILD_DIR}/stage3_to_B0_chain_verification.json"

RUN_DIR="archive/hetzner_version/runs/prod_refine_20260315_180520"
RUN_MANIFEST="${RUN_DIR}/manifest.json"

PIPELINE_SCRIPT="archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py"
PIPELINE_CONFIG="archive/hetzner_version/src/kg_builder/config.yaml"
PIPELINE_RUNTIME_CONFIG="archive/hetzner_version/src/kg_builder/config.runtime.json"

STAGE02_SUMMARY="${RUN_DIR}/stage02_candidates/reports/summary.json"
STAGE02_SHARDS_DIR="${RUN_DIR}/stage02_candidates/shards"

STAGE03_AUDIT_JSONL="${RUN_DIR}/stage03_candidate_audit/candidate_relation_audit.jsonl"
STAGE03_SUMMARY="${RUN_DIR}/stage03_candidate_audit/summary.json"

STAGE04_CORE_GRAPH="${RUN_DIR}/stage04_core_graph/core_graph_triples.jsonl"
STAGE04_SELECTION_LOG="${RUN_DIR}/stage04_core_graph/core_graph_selection_log.jsonl"
STAGE04_RELATION_COUNTS="${RUN_DIR}/stage04_core_graph/core_graph_relation_counts.json"
STAGE04_COMPONENT_REPORT="${RUN_DIR}/stage04_core_graph/core_graph_component_report.json"

STAGE5_TO_B0_VERIFICATION="artifacts/final_graph/selected_final_graph/rebuild/stage5_to_B0_chain_verification.json"
STAGE5_TO_B0_DOC="docs/reconstruction/28_stage5_to_B0_chain_verification.md"
B0_GRAPH="src/Pruning graph/stage11_eta_aware_connectivity_repair_full/stage12_path_repair_prod/largest_component.csv"

for path in \
  "${RUN_MANIFEST}" \
  "${PIPELINE_SCRIPT}" \
  "${PIPELINE_CONFIG}" \
  "${PIPELINE_RUNTIME_CONFIG}" \
  "${STAGE02_SUMMARY}" \
  "${STAGE03_AUDIT_JSONL}" \
  "${STAGE03_SUMMARY}" \
  "${STAGE04_CORE_GRAPH}" \
  "${STAGE04_SELECTION_LOG}" \
  "${STAGE04_RELATION_COUNTS}" \
  "${STAGE04_COMPONENT_REPORT}" \
  "${STAGE5_TO_B0_VERIFICATION}" \
  "${STAGE5_TO_B0_DOC}" \
  "${B0_GRAPH}"; do
  require_file "${path}"
done
[[ -d "${STAGE02_SHARDS_DIR}" ]] || die "required directory not found: ${STAGE02_SHARDS_DIR}"

if [[ "${FORCE}" -ne 1 ]]; then
  [[ ! -e "${OUT}" ]] || die "refusing to overwrite ${OUT}; rerun with --force"
fi

safe_mkdir "${REBUILD_DIR}"

"${PYTHON_BIN}" - \
  "${OUT}" \
  "${RUN_DIR}" \
  "${RUN_MANIFEST}" \
  "${PIPELINE_SCRIPT}" \
  "${PIPELINE_CONFIG}" \
  "${PIPELINE_RUNTIME_CONFIG}" \
  "${STAGE02_SUMMARY}" \
  "${STAGE02_SHARDS_DIR}" \
  "${STAGE03_AUDIT_JSONL}" \
  "${STAGE03_SUMMARY}" \
  "${STAGE04_CORE_GRAPH}" \
  "${STAGE04_SELECTION_LOG}" \
  "${STAGE04_RELATION_COUNTS}" \
  "${STAGE04_COMPONENT_REPORT}" \
  "${STAGE5_TO_B0_VERIFICATION}" \
  "${STAGE5_TO_B0_DOC}" \
  "${B0_GRAPH}" <<'PY'
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

(
    out_path,
    run_dir,
    run_manifest,
    pipeline_script,
    pipeline_config,
    pipeline_runtime_config,
    stage02_summary,
    stage02_shards_dir,
    stage03_audit_jsonl,
    stage03_summary,
    stage04_core_graph,
    stage04_selection_log,
    stage04_relation_counts,
    stage04_component_report,
    stage5_to_b0_verification,
    stage5_to_b0_doc,
    b0_graph,
) = [Path(x) for x in sys.argv[1:]]

EXPECTED_STAGE4_SHA = "54f5ae7af3bd2b9a117817adeaa0cea355bbf2a385ed25a97d0551c4e0f975fd"

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def aggregate_manifest_hash(rows: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(f"{row['path']}\t{row['sha256']}\t{row['size_bytes']}\n".encode("utf-8"))
    return digest.hexdigest()

def load_json(path: Path) -> Any:
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

def read_jsonl_profile(path: Path, collect_triples: bool = True) -> dict[str, Any]:
    rows = 0
    parse_errors = 0
    hrt_records = 0
    triples = set()
    relations = set()
    relation_field_values = set()
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
            if isinstance(obj, dict) and "relation" in obj:
                relation_field_values.add(str(obj["relation"]))
            triple = triple_from_obj(obj)
            if triple:
                hrt_records += 1
                if collect_triples:
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
        "records_contain_h_r_t_or_equivalent": hrt_records > 0,
        "h_r_t_like_record_count": hrt_records,
        "unique_triple_count": len(triples) if collect_triples else None,
        "unique_relation_count": len(relations) if collect_triples else None,
        "unique_relation_field_count": len(relation_field_values),
        "_triples": triples,
    }

def read_csv_graph(path: Path) -> dict[str, Any]:
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

def public_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in profile.items() if not k.startswith("_")}

def json_artifact_profile(path: Path) -> dict[str, Any]:
    try:
        data = load_json(path)
        parse_ok = True
        parse_error = None
    except Exception as exc:
        data = None
        parse_ok = False
        parse_error = str(exc)
    row_count = len(data) if isinstance(data, list) else (len(data) if isinstance(data, dict) else None)
    return {
        "path": str(path),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
        "file_type": "json",
        "json_parse_ok": parse_ok,
        "parse_error": parse_error,
        "row_or_key_count": row_count,
        "top_level_type": type(data).__name__ if parse_ok else None,
        "records_contain_h_r_t_or_equivalent": False,
        "unique_triple_count": None,
        "unique_relation_count": None,
    }

def snippet_evidence(text: str) -> dict[str, bool]:
    return {
        "has_stage_audit_candidates_function": "def stage_audit_candidates" in text,
        "stage03_audit_reads_stage02_shards": 'ctx.run_dir / "stage02_candidates" / "shards"' in text and "audit_candidate_relation" in text,
        "has_stage_construct_graph_function": "def stage_construct_graph" in text,
        "stage04_construct_reads_stage02_shards": 'candidate_dir = ctx.run_dir / "stage02_candidates" / "shards"' in text and "construct_core_graph(candidate_dir" in text,
        "stage04_writes_core_graph_triples": "core_graph_triples.jsonl" in text,
        "pipeline_order_stage03_before_stage04": '("stage03_candidate_audit", stage_audit_candidates)' in text and '("stage04_core_graph", stage_construct_graph)' in text,
    }

run_manifest_data = load_json(run_manifest)
stage02_summary_data = load_json(stage02_summary)
stage03_summary_data = load_json(stage03_summary)
stage04_relation_counts_data = load_json(stage04_relation_counts)
stage04_component_report_data = load_json(stage04_component_report)
stage5_to_b0_data = load_json(stage5_to_b0_verification)
pipeline_text = pipeline_script.read_text(encoding="utf-8", errors="replace")

stage03_audit = read_jsonl_profile(stage03_audit_jsonl, collect_triples=True)
stage04_core = read_jsonl_profile(stage04_core_graph, collect_triples=True)
stage04_selection = read_jsonl_profile(stage04_selection_log, collect_triples=True)
b0 = read_csv_graph(b0_graph)

shard_paths = sorted(stage02_shards_dir.glob("*.jsonl"))
stage02_shard_hashes = [
    {"path": str(path), "sha256": sha256(path), "size_bytes": path.stat().st_size}
    for path in shard_paths
]
stage02_triples = set()
stage02_relations = set()
stage02_rows = 0
stage02_parse_errors = 0
stage02_hrt_records = 0
stage02_first_keys = []
for path in shard_paths:
    prof = read_jsonl_profile(path, collect_triples=True)
    stage02_rows += prof["row_count"]
    stage02_parse_errors += prof["parse_error_count"]
    stage02_hrt_records += prof["h_r_t_like_record_count"]
    if not stage02_first_keys and prof["first_record_keys"]:
        stage02_first_keys = prof["first_record_keys"]
    stage02_triples.update(prof["_triples"])
    stage02_relations.update(triple[1] for triple in prof["_triples"])

stage02_pool_profile = {
    "path": str(stage02_shards_dir),
    "file_type": "jsonl_shard_directory",
    "shard_count": len(shard_paths),
    "aggregate_sha256_manifest": aggregate_manifest_hash(stage02_shard_hashes),
    "row_count": stage02_rows,
    "jsonl_parse_ok": stage02_parse_errors == 0,
    "parse_error_count": stage02_parse_errors,
    "first_record_keys": stage02_first_keys,
    "records_contain_h_r_t_or_equivalent": stage02_hrt_records > 0,
    "h_r_t_like_record_count": stage02_hrt_records,
    "unique_triple_count": len(stage02_triples),
    "unique_relation_count": len(stage02_relations),
    "stage4_core_triples_subset": stage04_core["_triples"] <= stage02_triples,
    "stage4_overlap_count": len(stage04_core["_triples"] & stage02_triples),
    "appears_direct_stage4_input": True,
    "evidence_for_or_against": "Archived pipeline code constructs Stage4 from ctx.run_dir/stage02_candidates/shards; Stage4 core triples are a subset of the combined shard triple set.",
}

stage03_artifacts = [
    {
        **public_profile(stage03_audit),
        "file_type": "jsonl",
        "stage4_core_triples_subset": False,
        "stage4_overlap_count": None,
        "appears_direct_stage4_input": False,
        "evidence_for_or_against": "Relation-level audit rows; no h/r/t triples. Pipeline code audits Stage2 shards, but Stage4 construction reads Stage2 shards directly rather than this audit JSONL.",
    },
    {
        **json_artifact_profile(stage03_summary),
        "stage4_core_triples_subset": False,
        "stage4_overlap_count": None,
        "appears_direct_stage4_input": False,
        "evidence_for_or_against": "Stage3 relation-audit summary; no h/r/t triples.",
    },
    stage02_pool_profile,
]

stage04_evidence_artifacts = [
    {
        **public_profile(stage04_core),
        "file_type": "jsonl",
        "stage4_core_triples_subset": True,
        "stage4_overlap_count": stage04_core["unique_triple_count"],
        "appears_direct_stage4_input": False,
        "evidence_for_or_against": "Stage4 output graph, not an input.",
    },
    {
        **public_profile(stage04_selection),
        "file_type": "jsonl",
        "stage4_core_triples_subset": stage04_core["_triples"] <= stage04_selection["_triples"],
        "stage4_overlap_count": len(stage04_core["_triples"] & stage04_selection["_triples"]),
        "appears_direct_stage4_input": False,
        "evidence_for_or_against": "Stage4 selection log; byte/content-equivalent selected triples log, not an upstream input.",
    },
    {
        **json_artifact_profile(stage04_relation_counts),
        "relation_count_entries": len(stage04_relation_counts_data) if isinstance(stage04_relation_counts_data, dict) else None,
        "relation_count_total": sum(stage04_relation_counts_data.values()) if isinstance(stage04_relation_counts_data, dict) else None,
        "evidence_for_or_against": "Stage4 output relation count report.",
    },
    {
        **json_artifact_profile(stage04_component_report),
        "component_count": len(stage04_component_report_data) if isinstance(stage04_component_report_data, list) else None,
        "component_triple_count_total": sum(row.get("triple_count", 0) for row in stage04_component_report_data) if isinstance(stage04_component_report_data, list) else None,
        "evidence_for_or_against": "Stage4 output component report.",
    },
]

script_evidence = snippet_evidence(pipeline_text)
manifest_stages = run_manifest_data.get("stages", {})
stage04_manifest_info = manifest_stages.get("stage04_core_graph", {})
stage03_manifest_info = manifest_stages.get("stage03_candidate_audit", {})

stage04_log_evidence = {
    "stage4_specific_log_found": False,
    "notes": "No separate Stage4 log file was found under archive/hetzner_version/logs or run logs; run-level manifest and archived pipeline code provide the main command/procedure evidence.",
}

stage3_to_stage4_status = "unresolved"
if (
    script_evidence["stage04_construct_reads_stage02_shards"]
    and stage02_pool_profile["stage4_core_triples_subset"]
    and stage04_manifest_info.get("core_triple_count") == stage04_core["unique_triple_count"]
):
    if script_evidence["stage03_audit_reads_stage02_shards"] and stage03_manifest_info.get("relation_count") == 139:
        stage3_to_stage4_status = "partial"
    else:
        stage3_to_stage4_status = "partial"

checks = {
    "stage4_core_graph_exists": stage04_core_graph.exists(),
    "stage4_core_hash_matches_known": stage04_core["sha256"] == EXPECTED_STAGE4_SHA,
    "stage4_core_rows_18513": stage04_core["row_count"] == 18513,
    "stage4_core_unique_triples_18513": stage04_core["unique_triple_count"] == 18513,
    "stage4_core_unique_relations_139": stage04_core["unique_relation_count"] == 139,
    "run_manifest_stage03_completed": bool(stage03_manifest_info.get("completed_at")),
    "run_manifest_stage04_completed": bool(stage04_manifest_info.get("completed_at")),
    "run_manifest_stage04_core_triple_count_18513": stage04_manifest_info.get("core_triple_count") == 18513,
    "run_manifest_stage04_realized_relations_139": stage04_manifest_info.get("realized_relations") == 139,
    "stage03_audit_rows_139": stage03_audit["row_count"] == 139,
    "stage03_summary_relation_count_139": stage03_summary_data.get("relation_count") == 139,
    "stage03_summary_zero_candidate_relations_0": stage03_summary_data.get("relations_with_zero_candidates") == 0,
    "stage02_summary_total_written_candidates_81958": stage02_summary_data.get("total_written_candidates") == 81958,
    "stage02_shard_count_139": len(shard_paths) == 139,
    "stage02_combined_rows_match_summary": stage02_rows == stage02_summary_data.get("total_written_candidates"),
    "stage02_combined_unique_relations_139": len(stage02_relations) == 139,
    "stage4_core_subset_of_stage02_candidate_shards": stage04_core["_triples"] <= stage02_triples,
    "stage4_core_overlap_stage02_candidate_shards_18513": len(stage04_core["_triples"] & stage02_triples) == 18513,
    "stage4_selection_log_equals_core_graph_set": stage04_core["_triples"] == stage04_selection["_triples"],
    "stage4_selection_log_sha_matches_core_graph": stage04_selection["sha256"] == stage04_core["sha256"],
    "stage04_relation_counts_entries_139": len(stage04_relation_counts_data) == 139,
    "stage04_relation_counts_total_18513": sum(stage04_relation_counts_data.values()) == 18513,
    "stage04_component_report_count_6524": len(stage04_component_report_data) == 6524,
    "pipeline_code_stage03_before_stage04": script_evidence["pipeline_order_stage03_before_stage04"],
    "pipeline_code_stage04_reads_stage02_shards": script_evidence["stage04_construct_reads_stage02_shards"],
    "stage5_to_B0_previous_verification_passed": stage5_to_b0_data.get("overall_pass") is True,
}

hash_inputs = {
    "run_manifest": run_manifest,
    "pipeline_script": pipeline_script,
    "pipeline_config": pipeline_config,
    "pipeline_runtime_config": pipeline_runtime_config,
    "stage02_summary": stage02_summary,
    "stage03_audit_jsonl": stage03_audit_jsonl,
    "stage03_summary": stage03_summary,
    "stage04_core_graph": stage04_core_graph,
    "stage04_selection_log": stage04_selection_log,
    "stage04_relation_counts": stage04_relation_counts,
    "stage04_component_report": stage04_component_report,
    "stage5_to_B0_verification": stage5_to_b0_verification,
    "stage5_to_B0_doc": stage5_to_b0_doc,
    "B0_largest_component": b0_graph,
    "this_verification_script": Path("scripts/reconstruction/07_verify_stage3_to_B0_chain.sh"),
}

overall_pass = (
    checks["stage4_core_hash_matches_known"]
    and checks["run_manifest_stage04_core_triple_count_18513"]
    and checks["stage02_combined_rows_match_summary"]
    and checks["stage4_core_subset_of_stage02_candidate_shards"]
    and checks["pipeline_code_stage04_reads_stage02_shards"]
    and checks["stage5_to_B0_previous_verification_passed"]
)

verification = {
    "created_on": datetime.now(timezone.utc).isoformat(),
    "created_by": "scripts/reconstruction/07_verify_stage3_to_B0_chain.sh",
    "scope": "Read-only verification of Stage3/Stage4 evidence and Stage4 -> B0 chain.",
    "overall_pass": overall_pass,
    "stage3_to_stage4_status": stage3_to_stage4_status,
    "stage3_to_stage4_interpretation": (
        "Partial. The archived pipeline code and run manifest confirm Stage3 candidate audit precedes Stage4, "
        "and Stage4 construction reads the frozen Stage2 candidate shard directory. Stage4 core triples are a "
        "subset of the combined Stage2 candidate shards. The Stage3 audit artifact itself is relation-level "
        "and contains no h/r/t triples, so it is not a direct graph input to Stage4."
    ),
    "checks": checks,
    "hashes": {role: {"path": str(path), "sha256": sha256(path), "size_bytes": path.stat().st_size} for role, path in hash_inputs.items()},
    "stage02_shard_hashes": stage02_shard_hashes,
    "stage02_candidate_pool_profile": stage02_pool_profile,
    "stage03_candidate_or_audit_artifacts": stage03_artifacts,
    "stage04_manifest_summary_log_evidence": {
        "run_manifest_path": str(run_manifest),
        "run_manifest_sha256": sha256(run_manifest),
        "pipeline_script_path": str(pipeline_script),
        "pipeline_script_sha256": sha256(pipeline_script),
        "stage03_manifest_info": stage03_manifest_info,
        "stage04_manifest_info": stage04_manifest_info,
        "script_evidence": script_evidence,
        "log_evidence": stage04_log_evidence,
        "stage04_input_paths_from_code": [
            "runs/prod_refine_20260315_180520/stage02_candidates/shards",
            run_manifest_data.get("config", {}).get("allocated_relations_path"),
        ],
        "stage04_output_paths": [
            str(stage04_core_graph),
            str(stage04_selection_log),
            str(stage04_relation_counts),
            str(stage04_component_report),
        ],
        "selected_triples_count": stage04_core["unique_triple_count"],
        "relation_count": stage04_core["unique_relation_count"],
        "completion_status": "completed" if stage04_manifest_info.get("completed_at") else "unclear",
    },
    "stage04_evidence_artifacts": stage04_evidence_artifacts,
    "stage04_core_graph": public_profile(stage04_core),
    "B0_largest_component": {k: v for k, v in b0.items() if not k.startswith("_")},
    "set_relationships": {
        "stage4_core_overlap_with_stage02_candidate_pool": len(stage04_core["_triples"] & stage02_triples),
        "stage4_core_minus_stage02_candidate_pool": len(stage04_core["_triples"] - stage02_triples),
        "stage02_candidate_pool_minus_stage4_core": len(stage02_triples - stage04_core["_triples"]),
        "stage4_selection_log_overlap_with_core": len(stage04_selection["_triples"] & stage04_core["_triples"]),
        "stage4_selection_log_minus_core": len(stage04_selection["_triples"] - stage04_core["_triples"]),
        "core_minus_stage4_selection_log": len(stage04_core["_triples"] - stage04_selection["_triples"]),
    },
    "previous_stage5_to_B0_verification": {
        "path": str(stage5_to_b0_verification),
        "sha256": sha256(stage5_to_b0_verification),
        "overall_pass": stage5_to_b0_data.get("overall_pass"),
    },
    "notes": [
        "No Stage2, Stage3, Stage4, Stage5, Stage6, Stage7, Stage11, Stage12, B0, or allocation artifact was modified.",
        "No graph was generated.",
        "No WDQS or LLM call was made.",
        "Stage3 audit is not a direct h/r/t graph input; Stage4 construction is linked to Stage2 candidate shards by archived pipeline code and subset evidence.",
        "This narrows the Stage3/Stage4 evidence chain, but does not establish Stage1-to-Stage2 collection reproducibility, allocation export provenance, exact environment locking, or full Phase I reproducibility.",
    ],
}

out_path.write_text(json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8")

print(f"stage3_to_B0_chain_verification={out_path}")
print(f"overall_pass={verification['overall_pass']}")
print(f"stage3_to_stage4_status={stage3_to_stage4_status}")
for key, value in checks.items():
    print(f"{key}={value}")

if not verification["overall_pass"]:
    raise SystemExit(1)
PY
