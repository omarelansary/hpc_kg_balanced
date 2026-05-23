"""Reusable graph candidate registry helpers."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA_VERSION = "kg-candidate-registry-v1"

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "created_from",
    "canonical_allocation_path",
    "canonical_allocation_sha256",
    "candidates",
}

REQUIRED_CANDIDATE_KEYS = {
    "candidate_id",
    "label",
    "role",
    "is_graph_candidate",
    "status",
    "decision",
    "parent_candidate_id",
    "graph_path",
    "graph_sha256",
    "allocation_path",
    "allocation_sha256",
    "report_path",
    "report_schema",
    "report_sha256",
    "evidence_paths",
    "notes",
}

ALLOWED_ROLES = {
    "selected_baseline",
    "active_candidate",
    "nonselected_candidate",
    "rejected_candidate",
    "diagnostic_ablation",
    "probe_only",
}


def load_registry(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validate_registry_schema(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing_top = REQUIRED_TOP_LEVEL_KEYS - set(registry)
    if missing_top:
        errors.append(f"missing top-level keys: {sorted(missing_top)}")
    if registry.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {REGISTRY_SCHEMA_VERSION!r}, got {registry.get('schema_version')!r}"
        )
    candidates = registry.get("candidates")
    if not isinstance(candidates, list):
        errors.append("candidates must be a list")
        return errors

    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append(f"candidate[{index}] must be an object")
            continue
        missing = REQUIRED_CANDIDATE_KEYS - set(candidate)
        if missing:
            errors.append(f"candidate[{index}] missing keys: {sorted(missing)}")
        candidate_id = candidate.get("candidate_id")
        if not candidate_id:
            errors.append(f"candidate[{index}] missing candidate_id")
        elif candidate_id in seen:
            errors.append(f"duplicate candidate_id: {candidate_id}")
        else:
            seen.add(str(candidate_id))
        role = candidate.get("role")
        if role not in ALLOWED_ROLES:
            errors.append(f"candidate[{candidate_id}] has unknown role: {role!r}")
        if not isinstance(candidate.get("is_graph_candidate"), bool):
            errors.append(f"candidate[{candidate_id}] is_graph_candidate must be boolean")
        if not isinstance(candidate.get("evidence_paths"), list):
            errors.append(f"candidate[{candidate_id}] evidence_paths must be a list")
    return errors


def candidate_by_id(registry: dict[str, Any], candidate_id: str) -> dict[str, Any] | None:
    for candidate in registry.get("candidates", []):
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    return None


def graph_candidates(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in registry.get("candidates", [])
        if candidate.get("is_graph_candidate") is True
    ]


def evidence_only_entries(registry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in registry.get("candidates", [])
        if candidate.get("is_graph_candidate") is False
    ]


def required_artifact_paths(registry: dict[str, Any]) -> list[str]:
    paths: set[str] = set()
    allocation = registry.get("canonical_allocation_path")
    if allocation:
        paths.add(str(allocation))
    for candidate in registry.get("candidates", []):
        for key in ("graph_path", "allocation_path", "report_path"):
            value = candidate.get(key)
            if value:
                paths.add(str(value))
        for evidence_path in candidate.get("evidence_paths") or []:
            if evidence_path:
                paths.add(str(evidence_path))
    return sorted(paths)


def resolve_registry_path(path: str | None, base_dir: str | Path = ".") -> Path | None:
    if not path:
        return None
    candidate_path = Path(path)
    if candidate_path.is_absolute():
        return candidate_path
    return Path(base_dir) / candidate_path


def validate_candidate_paths_exist(
    registry: dict[str, Any],
    base_dir: str | Path = ".",
) -> dict[str, Any]:
    missing: list[dict[str, str]] = []
    present: list[str] = []
    for path in required_artifact_paths(registry):
        resolved = resolve_registry_path(path, base_dir)
        if resolved is None:
            continue
        if resolved.is_file():
            present.append(path)
        else:
            missing.append({"path": path, "resolved_path": str(resolved)})
    return {"present": present, "missing": missing}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_candidate_hashes(
    registry: dict[str, Any],
    base_dir: str | Path = ".",
) -> dict[str, Any]:
    checked: list[dict[str, str]] = []
    mismatched: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []

    hash_specs: list[tuple[str, str, str | None, str | None]] = [
        (
            "canonical_allocation",
            "canonical_allocation_path",
            registry.get("canonical_allocation_path"),
            registry.get("canonical_allocation_sha256"),
        )
    ]
    for candidate in registry.get("candidates", []):
        candidate_id = str(candidate.get("candidate_id"))
        hash_specs.extend(
            [
                (candidate_id, "graph_path", candidate.get("graph_path"), candidate.get("graph_sha256")),
                (candidate_id, "allocation_path", candidate.get("allocation_path"), candidate.get("allocation_sha256")),
                (candidate_id, "report_path", candidate.get("report_path"), candidate.get("report_sha256")),
            ]
        )

    for owner, field, path, expected in hash_specs:
        if not path or not expected:
            continue
        resolved = resolve_registry_path(path, base_dir)
        if resolved is None or not resolved.is_file():
            missing.append({"owner": owner, "field": field, "path": str(path)})
            continue
        observed = sha256_file(resolved)
        row = {
            "owner": owner,
            "field": field,
            "path": str(path),
            "expected_sha256": str(expected),
            "observed_sha256": observed,
        }
        checked.append(row)
        if observed != expected:
            mismatched.append(row)
    return {"checked": checked, "mismatched": mismatched, "missing": missing}


def summarize_registry(registry: dict[str, Any]) -> dict[str, Any]:
    candidates = registry.get("candidates", [])
    role_counts = Counter(candidate.get("role") for candidate in candidates)
    status_counts = Counter(candidate.get("status") for candidate in candidates)
    graph_candidate_count = sum(1 for candidate in candidates if candidate.get("is_graph_candidate"))
    evidence_only_count = len(candidates) - graph_candidate_count
    return {
        "schema_version": registry.get("schema_version"),
        "candidate_count": len(candidates),
        "graph_candidate_count": graph_candidate_count,
        "evidence_only_count": evidence_only_count,
        "role_counts": dict(sorted(role_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "candidate_ids": [candidate.get("candidate_id") for candidate in candidates],
    }

