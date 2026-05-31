"""Level 1 frozen candidate packaging for the pipeline runner."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, TextIO

from src.kg_pipeline.registry.candidate_registry import candidate_by_id, load_registry, sha256_file

DEFAULT_REGISTRY_PATH = Path("artifacts/final_graph/selected_final_graph/rebuild/candidate_registry.v1.json")
CREATED_BY = "scripts/pipeline/run_kg_pipeline.py --mode construct-candidates --from-frozen"
PACKAGE_MANIFEST_SCHEMA_VERSION = "kg-frozen-candidate-package-manifest-v1"


def package_frozen_candidate(
    *,
    repo_root: Path,
    run_dir: Path,
    candidate_id: str,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    log: TextIO | None = None,
) -> dict[str, Any]:
    """Package one existing registry graph candidate without generating a graph."""
    repo_root = repo_root.resolve()
    registry_path = _resolve(repo_root, registry_path)
    registry = load_registry(registry_path)
    candidate = candidate_by_id(registry, candidate_id)
    if candidate is None:
        raise ValueError(f"candidate_id {candidate_id!r} not found in {registry_path}")
    if not candidate.get("is_graph_candidate"):
        raise ValueError(f"candidate_id {candidate_id!r} is not a graph candidate")

    source_graph_rel = candidate.get("graph_path")
    expected_graph_sha = candidate.get("graph_sha256")
    if not source_graph_rel or not expected_graph_sha:
        raise ValueError(f"candidate_id {candidate_id!r} must have graph_path and graph_sha256")
    source_graph = _resolve(repo_root, Path(source_graph_rel))
    if not source_graph.is_file():
        raise FileNotFoundError(f"candidate graph does not exist: {source_graph_rel}")

    source_graph_sha = sha256_file(source_graph)
    if source_graph_sha != expected_graph_sha:
        raise ValueError(
            f"candidate graph hash mismatch for {candidate_id}: "
            f"expected {expected_graph_sha}, observed {source_graph_sha}"
        )

    allocation_rel = registry.get("canonical_allocation_path") or candidate.get("allocation_path")
    expected_allocation_sha = registry.get("canonical_allocation_sha256") or candidate.get("allocation_sha256")
    if not allocation_rel or not expected_allocation_sha:
        raise ValueError("registry must define canonical allocation path and sha256")
    allocation_path = _resolve(repo_root, Path(allocation_rel))
    if not allocation_path.is_file():
        raise FileNotFoundError(f"canonical allocation file does not exist: {allocation_rel}")
    allocation_sha = sha256_file(allocation_path)
    if allocation_sha != expected_allocation_sha:
        raise ValueError(
            f"canonical allocation hash mismatch: expected {expected_allocation_sha}, observed {allocation_sha}"
        )

    package_dir = run_dir / "candidates" / candidate_id
    package_dir.mkdir(parents=True, exist_ok=True)
    packaged_graph = package_dir / source_graph.name
    shutil.copy2(source_graph, packaged_graph)
    packaged_graph_sha = sha256_file(packaged_graph)
    if packaged_graph_sha != source_graph_sha:
        raise ValueError(
            f"packaged graph hash mismatch: source {source_graph_sha}, packaged {packaged_graph_sha}"
        )

    evaluator_out_dir = package_dir / "evaluation"
    evaluator_cmd = [
        "python",
        "scripts/graph_candidates/evaluate_candidate.py",
        "--candidate-id",
        candidate_id,
        "--label",
        str(candidate.get("label") or candidate_id),
        "--graph",
        str(packaged_graph),
        "--allocation",
        str(allocation_path),
        "--out-dir",
        str(evaluator_out_dir),
        "--force",
    ]
    if candidate.get("parent_candidate_id"):
        evaluator_cmd.extend(["--parent-candidate-id", str(candidate["parent_candidate_id"])])
    _log(log, f"running evaluator: {evaluator_cmd!r}")
    completed = subprocess.run(
        evaluator_cmd,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=False,
        check=False,
    )
    _log(log, completed.stdout.rstrip())
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(completed.returncode, evaluator_cmd, output=completed.stdout)

    evaluator_outputs = {
        "report_json": str(evaluator_out_dir / "report.json"),
        "summary_md": str(evaluator_out_dir / "summary.md"),
        "relation_quota_report_tsv": str(evaluator_out_dir / "relation_quota_report.tsv"),
        "pattern_balance_report_tsv": str(evaluator_out_dir / "pattern_balance_report.tsv"),
        "manifest_json": str(evaluator_out_dir / "manifest.json"),
    }
    report_path = evaluator_out_dir / "report.json"
    evaluator_status = "report_written" if report_path.is_file() else "missing_report"

    manifest = {
        "schema_version": PACKAGE_MANIFEST_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "source_registry_path": _repo_relative(repo_root, registry_path),
        "source_graph_path": str(source_graph_rel),
        "source_graph_sha256": source_graph_sha,
        "packaged_graph_path": _repo_relative(repo_root, packaged_graph),
        "packaged_graph_sha256": packaged_graph_sha,
        "allocation_path": str(allocation_rel),
        "allocation_sha256": allocation_sha,
        "evaluator_outputs": evaluator_outputs,
        "created_by": CREATED_BY,
        "status": "passed" if evaluator_status == "report_written" else "failed",
        "evaluator_status": evaluator_status,
        "notes": [
            "Level 1 packaging copies an existing frozen registered graph candidate.",
            "No graph was generated, pruned, repaired, or modified.",
            "candidate_registry.v1.json was read but not modified.",
        ],
    }
    manifest_path = package_dir / "candidate_package_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _log(log, f"candidate package manifest: {manifest_path}")
    return manifest


def _resolve(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return repo_root / path


def _repo_relative(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _log(log: TextIO | None, message: str) -> None:
    if log is not None and message:
        log.write(message + "\n")
        log.flush()
