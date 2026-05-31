"""Non-interactive runner for the reusable KG pipeline manifest."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Iterable

from .pipeline_manifest import PipelineManifest, PipelineStage
from .pipeline_state import PipelineState, default_run_id, latest_state_path

SAFE_VALIDATE_CLASS = "frozen_validation"
LIVE_CLASSES = {"driftable_live_wdqs", "driftable_live_llm"}


class PipelineRunner:
    """Execute or inspect stages from a pipeline manifest."""

    def __init__(self, manifest: PipelineManifest, repo_root: str | Path | None = None) -> None:
        self.manifest = manifest
        self.repo_root = Path(repo_root or ".").resolve()

    def list_stages(self) -> str:
        lines = ["stage_id\tphase\texecution_class\tdefault_enabled\trerun_policy\tdescription"]
        for stage in self.manifest.stages:
            lines.append(
                "\t".join(
                    [
                        stage.stage_id,
                        stage.phase,
                        stage.execution_class,
                        str(stage.default_enabled).lower(),
                        stage.rerun_policy,
                        stage.description,
                    ]
                )
            )
        return "\n".join(lines)

    def status(self, state_path: str | Path | None = None) -> str:
        chosen_path = Path(state_path) if state_path else latest_state_path(self.manifest.default_state_root)
        if chosen_path is None:
            return "No pipeline state found."
        state = PipelineState.load(chosen_path)
        lines = [
            f"state={chosen_path}",
            f"run_id={state.data.get('run_id')} mode={state.data.get('mode')} overall={state.data.get('overall_status')}",
            "stage_id\tstatus\texit_code\tmessage",
        ]
        for stage_id, row in state.data.get("stages", {}).items():
            lines.append(
                f"{stage_id}\t{row.get('status')}\t{row.get('exit_code')}\t{row.get('message') or ''}"
            )
        return "\n".join(lines)

    def plan(
        self,
        mode: str,
        *,
        allow_live: bool = False,
        allow_slurm: bool = False,
        force_stage_ids: Iterable[str] = (),
    ) -> list[tuple[PipelineStage, str, str]]:
        force_set = set(force_stage_ids)
        return [
            (stage, *self._stage_decision(stage, mode, allow_live, allow_slurm, force_set))
            for stage in self.manifest.stages
        ]

    def dry_run(
        self,
        mode: str,
        *,
        allow_live: bool = False,
        allow_slurm: bool = False,
        force_stage_ids: Iterable[str] = (),
    ) -> str:
        lines = [f"mode={mode}", "stage_id\taction\treason"]
        for stage, action, reason in self.plan(
            mode, allow_live=allow_live, allow_slurm=allow_slurm, force_stage_ids=force_stage_ids
        ):
            lines.append(f"{stage.stage_id}\t{action}\t{reason}")
        return "\n".join(lines)

    def run(
        self,
        mode: str,
        *,
        resume: bool = False,
        allow_live: bool = False,
        allow_slurm: bool = False,
        force_stage_ids: Iterable[str] = (),
    ) -> PipelineState:
        if mode == "construct-candidates":
            raise NotImplementedError("construct-candidates mode is not implemented yet")
        if mode == "live-rerun" and not allow_live:
            raise PermissionError("live-rerun refuses to run without --allow-live")
        if mode == "slurm-rerun" and not allow_slurm:
            raise PermissionError("slurm-rerun refuses to run without --allow-slurm")

        run_id = default_run_id()
        run_dir = Path(self.manifest.default_state_root) / run_id
        if resume:
            latest = latest_state_path(self.manifest.default_state_root)
            if latest is None:
                raise FileNotFoundError("--resume requested, but no previous pipeline_state.json exists")
            state = PipelineState.load(latest)
            run_dir = latest.parent
        else:
            state = PipelineState.create(
                run_dir / "pipeline_state.json",
                run_id,
                str(self.manifest.path),
                mode,
                [stage.stage_id for stage in self.manifest.stages],
            )
            self._write_resolved_manifest(run_dir)

        force_set = set(force_stage_ids)
        for stage in self.manifest.stages:
            action, reason = self._stage_decision(stage, mode, allow_live, allow_slurm, force_set)
            current_status = state.data.get("stages", {}).get(stage.stage_id, {}).get("status")
            if resume and current_status == "passed" and stage.stage_id not in force_set:
                state.set_stage(stage.stage_id, "skipped", message="already passed in resumed state")
                continue
            if action == "skip":
                state.set_stage(stage.stage_id, "skipped", message=reason)
                continue
            if action == "block":
                state.set_stage(stage.stage_id, "blocked", message=reason)
                continue
            self._run_stage(stage, state, run_dir)
        state.finalize()
        return state

    def _stage_decision(
        self,
        stage: PipelineStage,
        mode: str,
        allow_live: bool,
        allow_slurm: bool,
        force_stage_ids: set[str],
    ) -> tuple[str, str]:
        if stage.stage_id in force_stage_ids:
            if stage.execution_class in LIVE_CLASSES:
                if not allow_live:
                    return "block", "forced live stage requires --allow-live"
                return "block", "live WDQS/LLM execution is not implemented in this foundation"
            if stage.execution_class == "slurm_expensive":
                if not allow_slurm:
                    return "block", "forced SLURM stage requires --allow-slurm"
                return "block", "SLURM submission is not implemented in this foundation"
            if stage.execution_class == "graph_construction":
                return "block", "graph construction is not implemented in this foundation"
            return "run", "forced by --force-stage"

        if mode == "validate-frozen":
            if stage.execution_class == SAFE_VALIDATE_CLASS and stage.default_enabled:
                return "run", "default safe frozen validation stage"
            return "skip", f"not enabled for validate-frozen ({stage.execution_class})"

        if mode == "replay-frozen":
            if stage.execution_class == SAFE_VALIDATE_CLASS and stage.default_enabled:
                return "run", "safe validation stage included in replay"
            if (
                stage.execution_class == "deterministic_replay"
                and stage.rerun_policy == "allowed_in_replay"
                and stage.default_enabled
            ):
                return "run", "default deterministic replay stage allowed"
            return "skip", f"not enabled for replay-frozen ({stage.rerun_policy})"

        if mode == "live-rerun":
            if stage.execution_class in LIVE_CLASSES:
                if not allow_live:
                    return "block", "live stage requires --allow-live"
                return "block", "live WDQS/LLM execution is not implemented in this foundation"
            return "skip", f"not a live stage ({stage.execution_class})"

        if mode == "slurm-rerun":
            if stage.execution_class == "slurm_expensive":
                if not allow_slurm:
                    return "block", "SLURM stage requires --allow-slurm"
                return "block", "SLURM submission is not implemented in this foundation"
            return "skip", f"not a SLURM stage ({stage.execution_class})"

        if mode == "construct-candidates":
            if stage.execution_class == "graph_construction":
                return "block", "construct-candidates is not implemented yet"
            return "skip", f"not a graph construction stage ({stage.execution_class})"

        raise ValueError(f"unknown mode: {mode}")

    def _run_stage(self, stage: PipelineStage, state: PipelineState, run_dir: Path) -> None:
        logs_dir = run_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / f"{stage.stage_id}.log"
        state.set_stage(stage.stage_id, "running", log_path=str(log_path), message="running")
        command = [self._format_value(part, run_dir) for part in stage.command]
        env = os.environ.copy()
        env.update({key: self._format_value(value, run_dir) for key, value in stage.env.items()})
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"stage_id={stage.stage_id}\n")
            log.write(f"command={command!r}\n\n")
            log.flush()
            completed = subprocess.run(
                command,
                cwd=self.repo_root,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                shell=False,
                check=False,
            )
        if completed.returncode == 0:
            state.set_stage(stage.stage_id, "passed", exit_code=0, log_path=str(log_path), message="passed")
        else:
            state.set_stage(
                stage.stage_id,
                "failed",
                exit_code=completed.returncode,
                log_path=str(log_path),
                message=f"failed with exit code {completed.returncode}",
            )
            state.finalize()
            raise subprocess.CalledProcessError(completed.returncode, command)

    def _write_resolved_manifest(self, run_dir: Path) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "manifest.resolved.json"
        path.write_text(json.dumps(self.manifest.to_resolved_dict(), indent=2) + "\n", encoding="utf-8")

    def _format_value(self, value: str, run_dir: Path) -> str:
        return value.format(repo_root=str(self.repo_root), run_dir=str(run_dir))
