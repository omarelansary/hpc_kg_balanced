"""Run-scoped Phase II replay readiness helpers for the pipeline runner."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any


PHASE2_REPLAY_DIRNAME = "phase2_replay"
REPORT_OUT_NAME = "stage1_stage3_replay_readiness_report.json"
SUMMARY_OUT_NAME = "stage1_stage3_replay_readiness_summary.md"

RELATION_PIPELINE_SCRIPT = Path("archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py")
HISTORICAL_RUN_DIR = Path("archive/hetzner_version/runs/prod_refine_20260315_180520")
HISTORICAL_MANIFEST_PATH = HISTORICAL_RUN_DIR / "manifest.json"
HISTORICAL_CONFIG_SNAPSHOT_PATH = HISTORICAL_RUN_DIR / "config_snapshot.yaml"
HISTORICAL_STAGE1_OUTPUT_DIR = HISTORICAL_RUN_DIR / "stage01_genericity"
HISTORICAL_STAGE2_SHARDS_DIR = HISTORICAL_RUN_DIR / "stage02_candidates/shards"
HISTORICAL_STAGE3_OUTPUT_DIR = HISTORICAL_RUN_DIR / "stage03_candidate_audit"
ARCHIVE_ALLOCATION_PATH = Path("archive/hetzner_version/src/kg_builder/input/bidirectional_allocation_results5k.json")
CANONICAL_ALLOCATION_PATH = Path("src/Pruning graph/bidirectional_allocation_results5k.json")
ARCHIVE_SUPPORT_MATRIX_PATH = Path(
    "archive/hetzner_version/src/kg_builder/input/genericity_support_matrix.adjacency_support.json"
)
EXPECTED_ALLOCATION_SHA256 = "a0bb00a1e9b1e624c2ff6ee8fb215456b017b3aca679ef231f749ea796c310bb"


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


def relpath(repo_root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def input_status(repo_root: Path, path: Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    full_path = repo_root / path
    row: dict[str, Any] = {
        "path": str(path),
        "exists": full_path.exists(),
        "is_file": full_path.is_file(),
        "is_dir": full_path.is_dir(),
        "size_bytes": full_path.stat().st_size if full_path.exists() and full_path.is_file() else None,
        "sha256": None,
        "expected_sha256": expected_sha256,
        "hash_matches_expected": None,
    }
    if full_path.is_file():
        row["sha256"] = sha256_file(full_path)
        if expected_sha256 is not None:
            row["hash_matches_expected"] = row["sha256"] == expected_sha256
    return row


def count_jsonl_rows(path: Path) -> int:
    count = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def inspect_stage2_shards(repo_root: Path) -> dict[str, Any]:
    shards_dir = repo_root / HISTORICAL_STAGE2_SHARDS_DIR
    if not shards_dir.is_dir():
        return {
            "path": str(HISTORICAL_STAGE2_SHARDS_DIR),
            "exists": False,
            "shard_count": 0,
            "nonempty_shard_count": 0,
            "total_rows": 0,
            "sample_shards": [],
        }

    shards = sorted(shards_dir.glob("*.jsonl"))
    total_rows = 0
    nonempty = 0
    sample = []
    for index, shard in enumerate(shards):
        rows = count_jsonl_rows(shard)
        total_rows += rows
        if rows > 0:
            nonempty += 1
        if index < 10:
            sample.append({"path": relpath(repo_root, shard), "rows": rows})
    return {
        "path": str(HISTORICAL_STAGE2_SHARDS_DIR),
        "exists": True,
        "shard_count": len(shards),
        "nonempty_shard_count": nonempty,
        "total_rows": total_rows,
        "sample_shards": sample,
    }


def _historical_manifest_config(repo_root: Path) -> dict[str, Any]:
    manifest = repo_root / HISTORICAL_MANIFEST_PATH
    if not manifest.is_file():
        return {}
    data = load_json(manifest)
    config = data.get("config")
    return config if isinstance(config, dict) else {}


def run_phase2_stage1_stage3_readiness(repo_root: str | Path, run_dir: str | Path) -> dict[str, Any]:
    """Write a Stage1/Stage3 readiness report without executing historical stages."""
    repo_root = Path(repo_root).resolve()
    run_dir = Path(run_dir)
    replay_dir = run_dir / PHASE2_REPLAY_DIRNAME
    report_out = replay_dir / REPORT_OUT_NAME
    summary_out = replay_dir / SUMMARY_OUT_NAME
    future_run_dir = replay_dir / "historical_relation_pipeline_run"
    future_config = future_run_dir / "config_snapshot.yaml"

    archive_allocation = input_status(repo_root, ARCHIVE_ALLOCATION_PATH, expected_sha256=EXPECTED_ALLOCATION_SHA256)
    canonical_allocation = input_status(repo_root, CANONICAL_ALLOCATION_PATH, expected_sha256=EXPECTED_ALLOCATION_SHA256)
    support_matrix = input_status(repo_root, ARCHIVE_SUPPORT_MATRIX_PATH)
    script_status = input_status(repo_root, RELATION_PIPELINE_SCRIPT)
    manifest_status = input_status(repo_root, HISTORICAL_MANIFEST_PATH)
    config_status = input_status(repo_root, HISTORICAL_CONFIG_SNAPSHOT_PATH)
    historical_stage1_relation_genericity = input_status(
        repo_root,
        HISTORICAL_STAGE1_OUTPUT_DIR / "relation_genericity.jsonl",
    )
    historical_stage1_summary = input_status(repo_root, HISTORICAL_STAGE1_OUTPUT_DIR / "summary.json")
    historical_stage3_audit = input_status(repo_root, HISTORICAL_STAGE3_OUTPUT_DIR / "candidate_relation_audit.jsonl")
    historical_stage3_summary = input_status(repo_root, HISTORICAL_STAGE3_OUTPUT_DIR / "summary.json")
    shard_summary = inspect_stage2_shards(repo_root)
    historical_config = _historical_manifest_config(repo_root)

    stage1_missing = [
        row["path"]
        for row in [
            script_status,
            manifest_status,
            config_status,
            archive_allocation,
            canonical_allocation,
            support_matrix,
        ]
        if not row["exists"]
    ]
    if archive_allocation.get("hash_matches_expected") is False:
        stage1_missing.append(f"{ARCHIVE_ALLOCATION_PATH} hash mismatch")
    if canonical_allocation.get("hash_matches_expected") is False:
        stage1_missing.append(f"{CANONICAL_ALLOCATION_PATH} hash mismatch")

    stage3_missing = []
    if not shard_summary["exists"]:
        stage3_missing.append(str(HISTORICAL_STAGE2_SHARDS_DIR))
    if shard_summary["shard_count"] == 0:
        stage3_missing.append("no Stage2 shard JSONL files found")
    if shard_summary["total_rows"] == 0:
        stage3_missing.append("Stage2 shard JSONL files contain no candidate rows")
    if not archive_allocation["exists"]:
        stage3_missing.append(str(ARCHIVE_ALLOCATION_PATH))

    stage1_ready = not stage1_missing
    stage3_ready = not stage3_missing
    status = "passed" if stage1_ready and stage3_ready else "failed"

    corrected_stage1_command = [
        "python",
        str(RELATION_PIPELINE_SCRIPT),
        "--config",
        str(future_config),
        "--run-dir",
        str(future_run_dir),
        "score-genericity",
    ]
    corrected_stage3_command = [
        "python",
        str(RELATION_PIPELINE_SCRIPT),
        "--config",
        str(future_config),
        "--run-dir",
        str(future_run_dir),
        "audit-candidates",
    ]

    report = {
        "schema_version": "phase2-stage1-stage3-readiness-report-v1",
        "created_by": "src/kg_pipeline/orchestration/phase2_replay.py",
        "mode": "replay-frozen",
        "status": status,
        "execution_enabled_now": False,
        "historical_scripts_executed": False,
        "graph_construction_executed": False,
        "wdqs_llm_slurm_used": False,
        "outputs": {
            "report": str(report_out),
            "summary": str(summary_out),
        },
        "historical_command_mismatch_findings": [
            "The current manifest used pseudo --stage arguments for relation_balanced_kg_pipeline.py.",
            "The historical script actually requires --config, --run-dir or --run-name, and a subcommand.",
            "Corrected Stage1 subcommand is score-genericity.",
            "Corrected Stage3 subcommand is audit-candidates.",
        ],
        "stage1": {
            "stage_id": "phase2_stage1_genericity_scoring",
            "readiness_status": "ready_for_future_run_scoped_wrapper" if stage1_ready else "missing_required_inputs",
            "required_inputs": {
                "relation_pipeline_script": script_status,
                "historical_manifest": manifest_status,
                "historical_config_snapshot": config_status,
                "archive_allocation": archive_allocation,
                "canonical_allocation": canonical_allocation,
                "support_matrix": support_matrix,
            },
            "historical_config_paths": {
                "allocated_relations_path": historical_config.get("allocated_relations_path"),
                "support_matrix_path": historical_config.get("support_matrix_path"),
                "candidate_source_mode": historical_config.get("candidate_source_mode"),
                "candidate_input_path": historical_config.get("candidate_input_path"),
            },
            "historical_outputs_present_for_comparison": {
                "relation_genericity": historical_stage1_relation_genericity,
                "summary": historical_stage1_summary,
            },
            "corrected_command_for_future_wrapper": corrected_stage1_command,
            "missing_or_failed_requirements": stage1_missing,
            "executed_now": False,
        },
        "stage3": {
            "stage_id": "phase2_stage3_candidate_audit",
            "readiness_status": "ready_for_future_run_scoped_wrapper" if stage3_ready else "missing_required_inputs",
            "stage2_shards": shard_summary,
            "archive_allocation": archive_allocation,
            "historical_outputs_present_for_comparison": {
                "candidate_relation_audit": historical_stage3_audit,
                "summary": historical_stage3_summary,
            },
            "corrected_command_for_future_wrapper": corrected_stage3_command,
            "missing_or_failed_requirements": stage3_missing,
            "executed_now": False,
        },
        "run_scoped_wrapper_requirements": [
            "Create a fresh run directory under outputs/pipeline_runs/<run_id>/phase2_replay/ before executing historical subcommands.",
            "Write or copy a config snapshot whose run_root and inputs point to run-scoped or read-only frozen paths.",
            "For Stage3, provide Stage2 shards under <run_dir>/stage02_candidates/shards using copy or symlink policy before audit-candidates is enabled.",
            "Never target archive/hetzner_version/runs/prod_refine_20260315_180520 as an output directory.",
            "Keep Stage4 graph construction disabled until Stage1/Stage3 replay outputs are validated and a separate graph-construction wrapper exists.",
        ],
        "conclusion": {
            "stage1_executed": False,
            "stage3_executed": False,
            "stage1_stage3_prepared_for_future_run_scoped_replay": stage1_ready and stage3_ready,
            "b0_regeneration_safe_today": False,
            "stage4_graph_construction_remains_blocked": True,
        },
    }
    write_json(report_out, report)
    summary_out.write_text(_summary_markdown(report), encoding="utf-8")
    return report


def load_phase2_stage1_stage3_report(run_dir: str | Path) -> dict[str, Any]:
    report_path = Path(run_dir) / PHASE2_REPLAY_DIRNAME / REPORT_OUT_NAME
    if not report_path.is_file():
        raise FileNotFoundError(f"Phase II Stage1/Stage3 readiness report not found: {report_path}")
    return load_json(report_path)


def _summary_markdown(report: dict[str, Any]) -> str:
    stage1 = report["stage1"]
    stage3 = report["stage3"]
    shards = stage3["stage2_shards"]
    stage1_missing = ", ".join(stage1["missing_or_failed_requirements"]) or "none"
    stage3_missing = ", ".join(stage3["missing_or_failed_requirements"]) or "none"
    return f"""# Phase II Stage1/Stage3 Run-Scoped Replay Readiness

Status: `{report['status']}`

## Execution Boundary

No historical Phase II script was executed. This readiness slice validates local frozen inputs and records the corrected historical commands needed for a future run-scoped wrapper. Stage4 graph construction remains blocked.

## Stage1 Genericity Scoring

- Readiness: `{stage1['readiness_status']}`
- Corrected future command: `{' '.join(stage1['corrected_command_for_future_wrapper'])}`
- Archive allocation hash matches expected: `{str(stage1['required_inputs']['archive_allocation']['hash_matches_expected']).lower()}`
- Canonical allocation hash matches expected: `{str(stage1['required_inputs']['canonical_allocation']['hash_matches_expected']).lower()}`
- Missing requirements: {stage1_missing}

## Stage3 Candidate Audit

- Readiness: `{stage3['readiness_status']}`
- Corrected future command: `{' '.join(stage3['corrected_command_for_future_wrapper'])}`
- Stage2 shard count: {shards['shard_count']}
- Non-empty Stage2 shards: {shards['nonempty_shard_count']}
- Stage2 candidate rows: {shards['total_rows']}
- Missing requirements: {stage3_missing}

## Conclusion

Stage1 and Stage3 are prepared for a future run-scoped replay wrapper, but execution is not enabled in this slice. B0 regeneration is still not safe through the runner.
"""
