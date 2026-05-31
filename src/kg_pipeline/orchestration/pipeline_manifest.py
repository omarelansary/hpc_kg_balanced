"""Manifest parsing and validation for the reusable KG pipeline runner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = "kg-pipeline-manifest-v1"

EXECUTION_CLASSES = {
    "frozen_validation",
    "deterministic_replay",
    "driftable_live_wdqs",
    "driftable_live_llm",
    "slurm_expensive",
    "graph_construction",
    "manual_ui_optional",
}

RERUN_POLICIES = {
    "never_by_default",
    "allowed_in_replay",
    "requires_explicit_live_flag",
    "requires_slurm_submit",
    "manual_only",
}

REQUIRED_STAGE_KEYS = {
    "stage_id",
    "phase",
    "description",
    "command",
    "inputs",
    "outputs",
    "expected_hashes",
    "execution_class",
    "default_enabled",
    "rerun_policy",
}


@dataclass(frozen=True)
class PipelineStage:
    """One manifest stage entry."""

    stage_id: str
    phase: str
    description: str
    command: list[str]
    inputs: list[str]
    outputs: list[str]
    expected_hashes: dict[str, str]
    execution_class: str
    default_enabled: bool
    rerun_policy: str
    env: dict[str, str]

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> "PipelineStage":
        command = row.get("command")
        if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
            raise ValueError(f"stage {row.get('stage_id')!r} command must be a list of strings")
        inputs = row.get("inputs", [])
        outputs = row.get("outputs", [])
        expected_hashes = row.get("expected_hashes", {})
        env = row.get("env", {})
        if not isinstance(inputs, list) or not all(isinstance(item, str) for item in inputs):
            raise ValueError(f"stage {row.get('stage_id')!r} inputs must be a list of strings")
        if not isinstance(outputs, list) or not all(isinstance(item, str) for item in outputs):
            raise ValueError(f"stage {row.get('stage_id')!r} outputs must be a list of strings")
        if not isinstance(expected_hashes, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in expected_hashes.items()
        ):
            raise ValueError(f"stage {row.get('stage_id')!r} expected_hashes must map strings to strings")
        if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            raise ValueError(f"stage {row.get('stage_id')!r} env must map strings to strings")
        return cls(
            stage_id=str(row["stage_id"]),
            phase=str(row["phase"]),
            description=str(row["description"]),
            command=command,
            inputs=inputs,
            outputs=outputs,
            expected_hashes=expected_hashes,
            execution_class=str(row["execution_class"]),
            default_enabled=bool(row["default_enabled"]),
            rerun_policy=str(row["rerun_policy"]),
            env=env,
        )


@dataclass(frozen=True)
class PipelineManifest:
    """Validated pipeline manifest."""

    path: Path
    schema_version: str
    name: str
    description: str
    default_state_root: str
    stages: list[PipelineStage]

    def stage_by_id(self, stage_id: str) -> PipelineStage | None:
        for stage in self.stages:
            if stage.stage_id == stage_id:
                return stage
        return None

    def to_resolved_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "default_state_root": self.default_state_root,
            "source_manifest_path": str(self.path),
            "stages": [stage.__dict__ for stage in self.stages],
        }


def load_manifest(path: str | Path) -> PipelineManifest:
    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = validate_manifest_dict(data)
    if errors:
        joined = "\n".join(f"- {error}" for error in errors)
        raise ValueError(f"Invalid pipeline manifest {manifest_path}:\n{joined}")
    return PipelineManifest(
        path=manifest_path,
        schema_version=data["schema_version"],
        name=data.get("name", "kg_pipeline"),
        description=data.get("description", ""),
        default_state_root=data.get("default_state_root", "outputs/pipeline_runs"),
        stages=[PipelineStage.from_dict(row) for row in data["stages"]],
    )


def validate_manifest_dict(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be {MANIFEST_SCHEMA_VERSION!r}, got {data.get('schema_version')!r}"
        )
    stages = data.get("stages")
    if not isinstance(stages, list):
        errors.append("stages must be a list")
        return errors
    seen: set[str] = set()
    for index, row in enumerate(stages):
        if not isinstance(row, dict):
            errors.append(f"stage[{index}] must be an object")
            continue
        missing = sorted(REQUIRED_STAGE_KEYS - set(row))
        if missing:
            errors.append(f"stage[{index}] missing keys: {missing}")
            continue
        stage_id = row.get("stage_id")
        if not stage_id:
            errors.append(f"stage[{index}] missing stage_id")
        elif stage_id in seen:
            errors.append(f"duplicate stage_id: {stage_id}")
        else:
            seen.add(str(stage_id))
        if row.get("execution_class") not in EXECUTION_CLASSES:
            errors.append(f"stage[{stage_id}] invalid execution_class: {row.get('execution_class')!r}")
        if row.get("rerun_policy") not in RERUN_POLICIES:
            errors.append(f"stage[{stage_id}] invalid rerun_policy: {row.get('rerun_policy')!r}")
        try:
            PipelineStage.from_dict(row)
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(str(exc))
    return errors
