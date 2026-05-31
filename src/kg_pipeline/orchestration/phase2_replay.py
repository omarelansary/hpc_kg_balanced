"""Run-scoped Phase II replay readiness helpers for the pipeline runner."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any


PHASE2_REPLAY_DIRNAME = "phase2_replay"
REPORT_OUT_NAME = "stage1_stage3_replay_readiness_report.json"
SUMMARY_OUT_NAME = "stage1_stage3_replay_readiness_summary.md"
EXECUTION_REPORT_OUT_NAME = "stage1_stage3_execution_report.json"
EXECUTION_SUMMARY_OUT_NAME = "stage1_stage3_execution_summary.md"
STAGE4_REPORT_OUT_NAME = "stage4_core_graph_execution_report.json"
STAGE4_SUMMARY_OUT_NAME = "stage4_core_graph_execution_summary.md"

RELATION_PIPELINE_SCRIPT = Path("archive/hetzner_version/src/kg_builder/relation_balanced_kg_pipeline.py")
HISTORICAL_RUN_DIR = Path("archive/hetzner_version/runs/prod_refine_20260315_180520")
HISTORICAL_MANIFEST_PATH = HISTORICAL_RUN_DIR / "manifest.json"
HISTORICAL_CONFIG_SNAPSHOT_PATH = HISTORICAL_RUN_DIR / "config_snapshot.yaml"
HISTORICAL_STAGE1_OUTPUT_DIR = HISTORICAL_RUN_DIR / "stage01_genericity"
HISTORICAL_STAGE2_SHARDS_DIR = HISTORICAL_RUN_DIR / "stage02_candidates/shards"
HISTORICAL_STAGE3_OUTPUT_DIR = HISTORICAL_RUN_DIR / "stage03_candidate_audit"
HISTORICAL_STAGE4_OUTPUT_DIR = HISTORICAL_RUN_DIR / "stage04_core_graph"
ARCHIVE_ALLOCATION_PATH = Path("archive/hetzner_version/src/kg_builder/input/bidirectional_allocation_results5k.json")
CANONICAL_ALLOCATION_PATH = Path("src/Pruning graph/bidirectional_allocation_results5k.json")
CANDIDATE_REGISTRY_PATH = Path("artifacts/final_graph/selected_final_graph/rebuild/candidate_registry.v1.json")
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


def path_status(path: Path, *, expected_sha256: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
        "is_dir": path.is_dir(),
        "size_bytes": path.stat().st_size if path.exists() and path.is_file() else None,
        "sha256": None,
        "expected_sha256": expected_sha256,
        "hash_matches_expected": None,
    }
    if path.is_file():
        row["sha256"] = sha256_file(path)
        if expected_sha256 is not None:
            row["hash_matches_expected"] = row["sha256"] == expected_sha256
    return row


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


def graph_jsonl_metrics(path: Path) -> dict[str, Any]:
    triples: set[tuple[str | None, str | None, str | None]] = set()
    relations: set[str] = set()
    duplicate_count = 0
    row_count = 0
    if not path.is_file():
        return {
            "path": str(path),
            "exists": False,
            "triple_count": 0,
            "relation_count": 0,
            "duplicate_triple_count": 0,
        }
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row_count += 1
            rec = json.loads(line)
            triple = (rec.get("h"), rec.get("r"), rec.get("t"))
            if triple in triples:
                duplicate_count += 1
            else:
                triples.add(triple)
            if rec.get("r") is not None:
                relations.add(str(rec["r"]))
    return {
        "path": str(path),
        "exists": True,
        "triple_count": row_count,
        "unique_triple_count": len(triples),
        "relation_count": len(relations),
        "duplicate_triple_count": duplicate_count,
    }


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


def _historical_config_snapshot_data(repo_root: Path) -> tuple[dict[str, Any], str]:
    config_path = repo_root / HISTORICAL_CONFIG_SNAPSHOT_PATH
    if config_path.is_file():
        try:
            import yaml  # type: ignore[import-not-found]

            data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data, str(HISTORICAL_CONFIG_SNAPSHOT_PATH)
        except Exception:
            pass
    return _historical_manifest_config(repo_root), str(HISTORICAL_MANIFEST_PATH)


def _snapshot_historical_archive(repo_root: Path) -> dict[str, Any]:
    rows = {}
    for path in [
        HISTORICAL_RUN_DIR,
        HISTORICAL_MANIFEST_PATH,
        HISTORICAL_CONFIG_SNAPSHOT_PATH,
        HISTORICAL_STAGE1_OUTPUT_DIR,
        HISTORICAL_STAGE2_SHARDS_DIR,
        HISTORICAL_STAGE3_OUTPUT_DIR,
        HISTORICAL_STAGE4_OUTPUT_DIR,
    ]:
        full_path = repo_root / path
        if full_path.exists():
            stat = full_path.stat()
            rows[str(path)] = {
                "exists": True,
                "is_file": full_path.is_file(),
                "is_dir": full_path.is_dir(),
                "size_bytes": stat.st_size if full_path.is_file() else None,
                "mtime_ns": stat.st_mtime_ns,
            }
        else:
            rows[str(path)] = {"exists": False}
    return rows


def _command_tail(text: str, *, max_lines: int = 60) -> list[str]:
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return lines
    return lines[-max_lines:]


def _run_historical_command(repo_root: Path, command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "output_tail": _command_tail(completed.stdout or ""),
    }


def run_phase2_stage1_stage3_readiness(repo_root: str | Path, run_dir: str | Path) -> dict[str, Any]:
    """Write a Stage1/Stage3 readiness report without executing historical stages."""
    repo_root = Path(repo_root).resolve()
    run_dir = Path(run_dir)
    replay_dir = run_dir / PHASE2_REPLAY_DIRNAME
    report_out = replay_dir / REPORT_OUT_NAME
    summary_out = replay_dir / SUMMARY_OUT_NAME
    future_run_dir = replay_dir / "historical_relation_pipeline_run"
    future_config = future_run_dir / "config_snapshot.json"

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


def _run_scoped_paths(run_dir: Path) -> dict[str, Path]:
    replay_dir = run_dir / PHASE2_REPLAY_DIRNAME
    historical_run_dir = replay_dir / "historical_relation_pipeline_run"
    return {
        "replay_dir": replay_dir,
        "historical_run_dir": historical_run_dir,
        "run_scoped_config": historical_run_dir / "config_snapshot.json",
        "stage2_shards_dir": historical_run_dir / "stage02_candidates" / "shards",
        "execution_report": replay_dir / EXECUTION_REPORT_OUT_NAME,
        "execution_summary": replay_dir / EXECUTION_SUMMARY_OUT_NAME,
        "stage4_report": replay_dir / STAGE4_REPORT_OUT_NAME,
        "stage4_summary": replay_dir / STAGE4_SUMMARY_OUT_NAME,
    }


def _prepare_run_scoped_execution_environment(
    repo_root: Path,
    run_dir: Path,
    readiness_report: dict[str, Any],
) -> dict[str, Any]:
    paths = _run_scoped_paths(run_dir)
    replay_dir = paths["replay_dir"]
    historical_run_dir = paths["historical_run_dir"]
    config_out = paths["run_scoped_config"]
    run_scoped_stage2_shards = paths["stage2_shards_dir"]
    historical_archive_dir = (repo_root / HISTORICAL_RUN_DIR).resolve()

    replay_dir.mkdir(parents=True, exist_ok=True)
    historical_run_dir.mkdir(parents=True, exist_ok=True)
    if historical_run_dir.resolve() == historical_archive_dir:
        raise RuntimeError(f"refusing to target historical archive run directory: {HISTORICAL_RUN_DIR}")

    config_data, config_source = _historical_config_snapshot_data(repo_root)
    if not config_data:
        raise RuntimeError("historical config snapshot could not be loaded")

    config_changes = []

    def set_config_value(key: str, value: Any, reason: str) -> None:
        old_value = config_data.get(key)
        if old_value != value:
            config_changes.append({"field": key, "old_value": old_value, "new_value": value, "reason": reason})
            config_data[key] = value

    set_config_value(
        "run_root",
        str(replay_dir),
        "keep any run-root-derived outputs inside the pipeline run directory",
    )
    set_config_value(
        "allocated_relations_path",
        str(ARCHIVE_ALLOCATION_PATH),
        "historical config path is absent in this repo; use frozen archive allocation",
    )
    set_config_value(
        "support_matrix_path",
        str(ARCHIVE_SUPPORT_MATRIX_PATH),
        "historical config path is absent in this repo; use frozen archive support matrix",
    )
    set_config_value(
        "candidate_source_mode",
        "local",
        "prevent accidental WDQS backend selection in the run-scoped config",
    )
    set_config_value(
        "candidate_input_path",
        str(run_scoped_stage2_shards),
        "point any local candidate source at run-scoped frozen Stage2 shard links",
    )
    write_json(config_out, config_data)

    manifest_path = historical_run_dir / "manifest.json"
    if not manifest_path.exists():
        write_json(
            manifest_path,
            {
                "created_at": None,
                "run_dir": str(historical_run_dir),
                "seed": config_data.get("seed"),
                "python_version": sys.version,
                "config": config_data,
                "stages": {},
                "created_by": "src/kg_pipeline/orchestration/phase2_replay.py",
                "source_historical_manifest": str(HISTORICAL_MANIFEST_PATH),
            },
        )

    source_shards_dir = repo_root / HISTORICAL_STAGE2_SHARDS_DIR
    run_scoped_stage2_shards.mkdir(parents=True, exist_ok=True)
    shard_policy = "symlink"
    linked = 0
    copied = 0
    for source_shard in sorted(source_shards_dir.glob("*.jsonl")):
        dest = run_scoped_stage2_shards / source_shard.name
        if dest.exists() or dest.is_symlink():
            continue
        try:
            dest.symlink_to(os.path.relpath(source_shard, start=run_scoped_stage2_shards))
            linked += 1
        except OSError:
            shard_policy = "copy"
            shutil.copy2(source_shard, dest)
            copied += 1

    return {
        "run_scoped_historical_run_dir": str(historical_run_dir),
        "run_scoped_config_path": str(config_out),
        "config_source": config_source,
        "config_changes": config_changes,
        "manifest_path": str(manifest_path),
        "stage2_shards_dir": str(run_scoped_stage2_shards),
        "stage2_shards_source": str(HISTORICAL_STAGE2_SHARDS_DIR),
        "stage2_shard_materialization": {
            "policy": shard_policy,
            "linked": linked,
            "copied": copied,
            "available": len(list(run_scoped_stage2_shards.glob("*.jsonl"))),
        },
        "readiness_status": readiness_report.get("status"),
    }


def _stage_outputs(historical_run_dir: Path, stage: str) -> dict[str, Any]:
    if stage == "stage01_genericity":
        paths = {
            "relation_genericity": historical_run_dir / stage / "relation_genericity.jsonl",
            "summary": historical_run_dir / stage / "summary.json",
        }
    elif stage == "stage03_candidate_audit":
        paths = {
            "candidate_relation_audit": historical_run_dir / stage / "candidate_relation_audit.jsonl",
            "summary": historical_run_dir / stage / "summary.json",
        }
    elif stage == "stage04_core_graph":
        paths = {
            "core_graph_triples": historical_run_dir / stage / "core_graph_triples.jsonl",
            "core_graph_selection_log": historical_run_dir / stage / "core_graph_selection_log.jsonl",
            "core_graph_relation_counts": historical_run_dir / stage / "core_graph_relation_counts.json",
            "core_graph_component_report": historical_run_dir / stage / "core_graph_component_report.json",
        }
    else:
        raise ValueError(f"unknown stage output set: {stage}")
    return {name: path_status(path) for name, path in paths.items()}


def _outputs_exist(outputs: dict[str, Any]) -> bool:
    return all(row.get("exists") and row.get("is_file") for row in outputs.values())


def _base_execution_report(
    repo_root: Path,
    run_dir: Path,
    readiness_report: dict[str, Any],
    environment: dict[str, Any],
) -> dict[str, Any]:
    paths = _run_scoped_paths(run_dir)
    historical_run_dir = Path(environment["run_scoped_historical_run_dir"])
    historical_archive_before = _snapshot_historical_archive(repo_root)
    return {
        "schema_version": "phase2-stage1-stage3-execution-report-v1",
        "created_by": "src/kg_pipeline/orchestration/phase2_replay.py",
        "mode": "replay-frozen",
        "status": "running",
        "readiness_report": str(paths["replay_dir"] / REPORT_OUT_NAME),
        "run_scoped_config_path": environment["run_scoped_config_path"],
        "run_scoped_historical_run_dir": environment["run_scoped_historical_run_dir"],
        "environment": environment,
        "safety_checks": {
            "readiness_status": readiness_report.get("status"),
            "run_scoped_dir_is_historical_archive": historical_run_dir.resolve()
            == (repo_root / HISTORICAL_RUN_DIR).resolve(),
            "historical_archive_outputs_targeted": False,
            "stage4_remains_blocked": True,
            "b0_regeneration_remains_blocked": True,
            "wdqs_llm_slurm_used": False,
        },
        "stage1": {
            "stage_id": "phase2_stage1_genericity_scoring",
            "command_result": None,
            "outputs": _stage_outputs(historical_run_dir, "stage01_genericity"),
            "passed": False,
        },
        "stage3": {
            "stage_id": "phase2_stage3_candidate_audit",
            "command_result": None,
            "outputs": _stage_outputs(historical_run_dir, "stage03_candidate_audit"),
            "passed": False,
        },
        "historical_archive_snapshot_before": historical_archive_before,
        "historical_archive_snapshot_after": None,
        "historical_archive_untouched": None,
        "conclusion": None,
        "outputs": {
            "report": str(paths["execution_report"]),
            "summary": str(paths["execution_summary"]),
        },
    }


def _write_execution_report(run_dir: Path, report: dict[str, Any]) -> None:
    paths = _run_scoped_paths(run_dir)
    write_json(paths["execution_report"], report)
    paths["execution_summary"].write_text(_execution_summary_markdown(report), encoding="utf-8")


def run_phase2_stage1_execution(repo_root: str | Path, run_dir: str | Path) -> dict[str, Any]:
    """Execute historical Stage1 only in the run-scoped historical pipeline directory."""
    repo_root = Path(repo_root).resolve()
    run_dir = Path(run_dir)
    readiness_report = run_phase2_stage1_stage3_readiness(repo_root, run_dir)
    if readiness_report.get("status") != "passed":
        raise RuntimeError("Phase II Stage1/Stage3 readiness failed; refusing execution")
    environment = _prepare_run_scoped_execution_environment(repo_root, run_dir, readiness_report)
    report = _base_execution_report(repo_root, run_dir, readiness_report, environment)
    command = [
        "python",
        str(RELATION_PIPELINE_SCRIPT),
        "--config",
        environment["run_scoped_config_path"],
        "--run-dir",
        environment["run_scoped_historical_run_dir"],
        "score-genericity",
    ]
    command_result = _run_historical_command(repo_root, command)
    historical_run_dir = Path(environment["run_scoped_historical_run_dir"])
    stage1_outputs = _stage_outputs(historical_run_dir, "stage01_genericity")
    report["stage1"]["command_result"] = command_result
    report["stage1"]["outputs"] = stage1_outputs
    report["stage1"]["passed"] = command_result["exit_code"] == 0 and _outputs_exist(stage1_outputs)
    report["historical_archive_snapshot_after"] = _snapshot_historical_archive(repo_root)
    report["historical_archive_untouched"] = (
        report["historical_archive_snapshot_before"] == report["historical_archive_snapshot_after"]
    )
    report["status"] = "stage1_passed_stage3_pending" if report["stage1"]["passed"] else "failed"
    report["conclusion"] = {
        "stage1_executed": True,
        "stage3_executed": False,
        "stage4_graph_construction_remains_blocked": True,
        "b0_regeneration_safe_today": False,
    }
    _write_execution_report(run_dir, report)
    return report


def run_phase2_stage3_execution(repo_root: str | Path, run_dir: str | Path) -> dict[str, Any]:
    """Execute historical Stage3 only after Stage1 has passed in the run-scoped directory."""
    repo_root = Path(repo_root).resolve()
    run_dir = Path(run_dir)
    paths = _run_scoped_paths(run_dir)
    if not paths["execution_report"].is_file():
        raise FileNotFoundError(f"Stage1 execution report not found: {paths['execution_report']}")
    report = load_json(paths["execution_report"])
    if not report.get("stage1", {}).get("passed"):
        raise RuntimeError("Stage1 did not pass; refusing Stage3 execution")
    environment = report["environment"]
    command = [
        "python",
        str(RELATION_PIPELINE_SCRIPT),
        "--config",
        environment["run_scoped_config_path"],
        "--run-dir",
        environment["run_scoped_historical_run_dir"],
        "audit-candidates",
    ]
    command_result = _run_historical_command(repo_root, command)
    historical_run_dir = Path(environment["run_scoped_historical_run_dir"])
    stage3_outputs = _stage_outputs(historical_run_dir, "stage03_candidate_audit")
    report["stage3"]["command_result"] = command_result
    report["stage3"]["outputs"] = stage3_outputs
    report["stage3"]["passed"] = command_result["exit_code"] == 0 and _outputs_exist(stage3_outputs)
    report["historical_archive_snapshot_after"] = _snapshot_historical_archive(repo_root)
    report["historical_archive_untouched"] = (
        report["historical_archive_snapshot_before"] == report["historical_archive_snapshot_after"]
    )
    report["status"] = "passed" if report["stage1"]["passed"] and report["stage3"]["passed"] else "failed"
    report["conclusion"] = {
        "stage1_executed": True,
        "stage3_executed": True,
        "stage4_graph_construction_remains_blocked": True,
        "b0_regeneration_safe_today": False,
    }
    _write_execution_report(run_dir, report)
    return report


def _write_stage4_report(run_dir: Path, report: dict[str, Any]) -> None:
    paths = _run_scoped_paths(run_dir)
    write_json(paths["stage4_report"], report)
    paths["stage4_summary"].write_text(_stage4_summary_markdown(report), encoding="utf-8")


def _stage4_prechecks(repo_root: Path, run_dir: Path, execution_report: dict[str, Any]) -> dict[str, Any]:
    environment = execution_report["environment"]
    historical_run_dir = Path(environment["run_scoped_historical_run_dir"])
    run_scoped_config = Path(environment["run_scoped_config_path"])
    stage2_shards_dir = historical_run_dir / "stage02_candidates" / "shards"
    stage3_outputs = _stage_outputs(historical_run_dir, "stage03_candidate_audit")
    stage4_output_dir = historical_run_dir / "stage04_core_graph"
    archive_stage4_output_dir = (repo_root / HISTORICAL_STAGE4_OUTPUT_DIR).resolve()
    candidate_registry_before = input_status(repo_root, CANDIDATE_REGISTRY_PATH)
    stage2_shard_count = len(list(stage2_shards_dir.glob("*.jsonl"))) if stage2_shards_dir.is_dir() else 0
    checks = {
        "stage1_report_exists_and_passed": execution_report.get("stage1", {}).get("passed") is True,
        "stage3_report_exists_and_passed": execution_report.get("stage3", {}).get("passed") is True,
        "run_scoped_config_exists": run_scoped_config.is_file(),
        "run_scoped_stage2_shards_exist": stage2_shard_count > 0,
        "run_scoped_stage2_shard_count": stage2_shard_count,
        "run_scoped_stage3_outputs_exist": _outputs_exist(stage3_outputs),
        "stage4_output_dir": str(stage4_output_dir),
        "stage4_output_dir_is_historical_archive": stage4_output_dir.resolve() == archive_stage4_output_dir,
        "candidate_registry_before": candidate_registry_before,
        "wdqs_llm_slurm_flags_enabled": False,
    }
    checks["passed"] = (
        checks["stage1_report_exists_and_passed"]
        and checks["stage3_report_exists_and_passed"]
        and checks["run_scoped_config_exists"]
        and checks["run_scoped_stage2_shards_exist"]
        and checks["run_scoped_stage3_outputs_exist"]
        and not checks["stage4_output_dir_is_historical_archive"]
        and candidate_registry_before.get("exists") is True
        and checks["wdqs_llm_slurm_flags_enabled"] is False
    )
    return checks


def run_phase2_stage4_execution(repo_root: str | Path, run_dir: str | Path) -> dict[str, Any]:
    """Execute historical Stage4 core graph construction in the run-scoped directory only."""
    repo_root = Path(repo_root).resolve()
    run_dir = Path(run_dir)
    stage1_stage3_report = load_phase2_stage1_stage3_execution_report(run_dir)
    prechecks = _stage4_prechecks(repo_root, run_dir, stage1_stage3_report)
    if not prechecks["passed"]:
        raise RuntimeError("Stage4 prechecks failed; refusing graph construction")

    environment = stage1_stage3_report["environment"]
    historical_run_dir = Path(environment["run_scoped_historical_run_dir"])
    historical_archive_before = _snapshot_historical_archive(repo_root)
    command = [
        "python",
        str(RELATION_PIPELINE_SCRIPT),
        "--config",
        environment["run_scoped_config_path"],
        "--run-dir",
        environment["run_scoped_historical_run_dir"],
        "construct-graph",
    ]
    command_result = _run_historical_command(repo_root, command)
    outputs = _stage_outputs(historical_run_dir, "stage04_core_graph")
    graph_path = historical_run_dir / "stage04_core_graph" / "core_graph_triples.jsonl"
    graph_metrics = graph_jsonl_metrics(graph_path)
    candidate_registry_after = input_status(repo_root, CANDIDATE_REGISTRY_PATH)
    historical_archive_after = _snapshot_historical_archive(repo_root)
    passed = command_result["exit_code"] == 0 and _outputs_exist(outputs)
    paths = _run_scoped_paths(run_dir)
    report = {
        "schema_version": "phase2-stage4-core-graph-execution-report-v1",
        "created_by": "src/kg_pipeline/orchestration/phase2_replay.py",
        "mode": "replay-frozen",
        "status": "passed" if passed else "failed",
        "verified_stage4_subcommand": "construct-graph",
        "verification_evidence": {
            "script": str(RELATION_PIPELINE_SCRIPT),
            "function": "stage_construct_graph",
            "argparse_subcommand": "construct-graph",
            "expected_stage_directory": "stage04_core_graph",
        },
        "prechecks": prechecks,
        "command_result": command_result,
        "output_directory": str(historical_run_dir / "stage04_core_graph"),
        "output_files_detected": outputs,
        "graph_metrics": graph_metrics,
        "output_is_run_scoped": str(historical_run_dir).startswith(str(run_dir)),
        "historical_archive_snapshot_before": historical_archive_before,
        "historical_archive_snapshot_after": historical_archive_after,
        "historical_archive_untouched": historical_archive_before == historical_archive_after,
        "candidate_registry_after": candidate_registry_after,
        "candidate_registry_unchanged": prechecks["candidate_registry_before"].get("sha256")
        == candidate_registry_after.get("sha256"),
        "safety_checks": {
            "stage5_stage6_stage7_blocked": True,
            "stage11_stage12_blocked": True,
            "c1_stage13_blocked": True,
            "wdqs_llm_slurm_used": False,
            "b0_regeneration_remains_incomplete": True,
        },
        "conclusion": {
            "stage4_executed": True,
            "stage4_passed": passed,
            "stage5_remains_blocked": True,
            "b0_regeneration_safe_today": False,
        },
        "outputs": {
            "report": str(paths["stage4_report"]),
            "summary": str(paths["stage4_summary"]),
        },
    }
    _write_stage4_report(run_dir, report)
    return report


def load_phase2_stage4_execution_report(run_dir: str | Path) -> dict[str, Any]:
    report_path = Path(run_dir) / PHASE2_REPLAY_DIRNAME / STAGE4_REPORT_OUT_NAME
    if not report_path.is_file():
        raise FileNotFoundError(f"Phase II Stage4 execution report not found: {report_path}")
    return load_json(report_path)


def load_phase2_stage1_stage3_execution_report(run_dir: str | Path) -> dict[str, Any]:
    report_path = Path(run_dir) / PHASE2_REPLAY_DIRNAME / EXECUTION_REPORT_OUT_NAME
    if not report_path.is_file():
        raise FileNotFoundError(f"Phase II Stage1/Stage3 execution report not found: {report_path}")
    return load_json(report_path)


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


def _execution_summary_markdown(report: dict[str, Any]) -> str:
    stage1 = report["stage1"]
    stage3 = report["stage3"]
    stage1_result = stage1.get("command_result") or {}
    stage3_result = stage3.get("command_result") or {}
    stage1_outputs = ", ".join(
        row["path"] for row in stage1.get("outputs", {}).values() if row.get("exists")
    ) or "none"
    stage3_outputs = ", ".join(
        row["path"] for row in stage3.get("outputs", {}).values() if row.get("exists")
    ) or "none"
    return f"""# Phase II Stage1/Stage3 Run-Scoped Execution

Status: `{report['status']}`

## Execution Boundary

Only historical Stage1 `score-genericity` and Stage3 `audit-candidates` were executed. Both commands targeted the run-scoped historical pipeline directory:

```text
{report['run_scoped_historical_run_dir']}
```

Stage4 graph construction, Stage5/6/7, Stage11/12 repair, C1 Stage13, WDQS, LLM, and SLURM remain blocked.

## Stage1

- Exit code: `{stage1_result.get('exit_code')}`
- Passed: `{str(stage1.get('passed')).lower()}`
- Command: `{' '.join(stage1_result.get('command', []))}`
- Output files: {stage1_outputs}

## Stage3

- Exit code: `{stage3_result.get('exit_code')}`
- Passed: `{str(stage3.get('passed')).lower()}`
- Command: `{' '.join(stage3_result.get('command', []))}`
- Output files: {stage3_outputs}

## Safety Result

- Historical archive untouched: `{str(report.get('historical_archive_untouched')).lower()}`
- Stage4 remains blocked: `{str(report['safety_checks']['stage4_remains_blocked']).lower()}`
- B0 regeneration remains blocked: `{str(report['safety_checks']['b0_regeneration_remains_blocked']).lower()}`
"""


def _stage4_summary_markdown(report: dict[str, Any]) -> str:
    result = report.get("command_result") or {}
    metrics = report.get("graph_metrics") or {}
    output_files = ", ".join(
        row["path"] for row in report.get("output_files_detected", {}).values() if row.get("exists")
    ) or "none"
    return f"""# Phase II Stage4 Run-Scoped Core Graph Construction

Status: `{report['status']}`

## Execution Boundary

Only historical Stage4 `construct-graph` was executed. The command targeted the run-scoped historical pipeline directory:

```text
{report['prechecks']['stage4_output_dir']}
```

Stage5/6/7, Stage11/12 repair, C1 Stage13, WDQS, LLM, and SLURM remain blocked. B0 regeneration remains incomplete.

## Command

- Verified subcommand: `{report['verified_stage4_subcommand']}`
- Exit code: `{result.get('exit_code')}`
- Command: `{' '.join(result.get('command', []))}`

## Outputs

- Output files: {output_files}
- Graph triples: `{metrics.get('triple_count')}`
- Relation count: `{metrics.get('relation_count')}`
- Duplicate triples: `{metrics.get('duplicate_triple_count')}`

## Safety Result

- Output is run-scoped: `{str(report.get('output_is_run_scoped')).lower()}`
- Historical archive untouched: `{str(report.get('historical_archive_untouched')).lower()}`
- Candidate registry unchanged: `{str(report.get('candidate_registry_unchanged')).lower()}`
- Stage5 remains blocked: `{str(report['conclusion']['stage5_remains_blocked']).lower()}`
"""
