"""Non-interactive runner for the reusable KG pipeline manifest."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Iterable

from .phase1_replay import load_phase1_replay_report, run_phase1_replay
from .phase2_replay import run_phase2_stage1_execution, run_phase2_stage3_execution, run_phase2_stage4_execution
from .pipeline_manifest import PipelineManifest, PipelineStage
from .pipeline_state import PipelineState, default_run_id, latest_state_path

SAFE_VALIDATE_CLASS = "frozen_validation"
LIVE_CLASSES = {"driftable_live_wdqs", "driftable_live_llm"}
PHASE1_REPLAY_STAGE_IDS = {
    "phase1_symmetry_inverse_evidence",
    "phase1_allocation_export",
    "phase1_support_genericity_matrix_export",
}
PHASE2_READINESS_STAGE_IDS = {
    "phase2_stage1_genericity_scoring",
    "phase2_stage3_candidate_audit",
}
PHASE2_STAGE4_EXECUTION_STAGE_IDS = {
    "phase2_stage4_core_graph_construction",
}


class PipelineRunner:
    """Execute or inspect stages from a pipeline manifest."""

    def __init__(
        self,
        manifest: PipelineManifest,
        repo_root: str | Path | None = None,
        state_root: str | Path | None = None,
    ) -> None:
        self.manifest = manifest
        self.repo_root = Path(repo_root or ".").resolve()
        self.state_root = Path(state_root) if state_root is not None else Path(self.manifest.default_state_root)

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
        chosen_path = Path(state_path) if state_path else latest_state_path(self.state_root)
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
        execute_stage4: bool = False,
        force_stage_ids: Iterable[str] = (),
    ) -> list[tuple[PipelineStage, str, str]]:
        force_set = set(force_stage_ids)
        return [
            (stage, *self._stage_decision(stage, mode, allow_live, allow_slurm, execute_stage4, force_set))
            for stage in self.manifest.stages
        ]

    def dry_run(
        self,
        mode: str,
        *,
        allow_live: bool = False,
        allow_slurm: bool = False,
        execute_stage4: bool = False,
        force_stage_ids: Iterable[str] = (),
    ) -> str:
        lines = [f"mode={mode}", "stage_id\taction\treason"]
        for stage, action, reason in self.plan(
            mode,
            allow_live=allow_live,
            allow_slurm=allow_slurm,
            execute_stage4=execute_stage4,
            force_stage_ids=force_stage_ids,
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
        execute_stage4: bool = False,
        force_stage_ids: Iterable[str] = (),
    ) -> PipelineState:
        if mode == "construct-candidates":
            raise NotImplementedError("construct-candidates mode is not implemented yet")
        if mode == "live-rerun" and not allow_live:
            raise PermissionError("live-rerun refuses to run without --allow-live")
        if mode == "slurm-rerun" and not allow_slurm:
            raise PermissionError("slurm-rerun refuses to run without --allow-slurm")

        run_id = default_run_id()
        run_dir = self.state_root / run_id
        if resume:
            latest = latest_state_path(self.state_root)
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
            action, reason = self._stage_decision(stage, mode, allow_live, allow_slurm, execute_stage4, force_set)
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
        execute_stage4: bool,
        force_stage_ids: set[str],
    ) -> tuple[str, str]:
        if stage.stage_id in PHASE2_STAGE4_EXECUTION_STAGE_IDS:
            if mode != "replay-frozen":
                return "skip", "Stage4 construct-graph is only available in replay-frozen with --execute-stage4"
            if execute_stage4:
                return "run", "explicit --execute-stage4 run-scoped graph construction stage"
            return "skip", "Stage4 construct-graph is long-running and requires --execute-stage4"

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
            if stage.stage_id in PHASE1_REPLAY_STAGE_IDS:
                return "run", "safe Phase I run-scoped replay stage"
            if stage.stage_id in PHASE2_READINESS_STAGE_IDS:
                return "run", "safe Phase II Stage1/Stage3 run-scoped execution stage"
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
        if stage.stage_id == "phase1_allocation_export":
            self._run_phase1_allocation_export_stage(stage, state, run_dir, log_path)
            return
        if stage.stage_id == "phase1_support_genericity_matrix_export":
            self._run_phase1_matrix_export_stage(stage, state, run_dir, log_path)
            return
        if stage.stage_id == "phase2_stage1_genericity_scoring":
            self._run_phase2_stage1_readiness_stage(stage, state, run_dir, log_path)
            return
        if stage.stage_id == "phase2_stage3_candidate_audit":
            self._run_phase2_stage3_readiness_stage(stage, state, run_dir, log_path)
            return
        if stage.stage_id == "phase2_stage4_core_graph_construction":
            self._run_phase2_stage4_execution_stage(stage, state, run_dir, log_path)
            return
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

    def _run_phase1_allocation_export_stage(
        self,
        stage: PipelineStage,
        state: PipelineState,
        run_dir: Path,
        log_path: Path,
    ) -> None:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"stage_id={stage.stage_id}\n")
            log.write("internal=phase1_run_scoped_replay_export\n\n")
            try:
                report = run_phase1_replay(self.repo_root, run_dir)
            except Exception as exc:  # noqa: BLE001 - runner records arbitrary stage failures.
                log.write(f"error={exc}\n")
                state.set_stage(stage.stage_id, "failed", exit_code=1, log_path=str(log_path), message=str(exc))
                state.finalize()
                raise subprocess.CalledProcessError(1, ["internal", "phase1_run_scoped_replay_export"]) from exc
            log.write(json.dumps(report, indent=2) + "\n")

        if report.get("status") == "passed" and report.get("allocation", {}).get("matches_exactly") is True:
            state.set_stage(
                stage.stage_id,
                "passed",
                exit_code=0,
                log_path=str(log_path),
                message="run-scoped allocation replay matched canonical allocation",
            )
            return

        message = "run-scoped allocation replay mismatch"
        state.set_stage(stage.stage_id, "failed", exit_code=1, log_path=str(log_path), message=message)
        state.finalize()
        raise subprocess.CalledProcessError(1, ["internal", "phase1_run_scoped_replay_export"])

    def _run_phase1_matrix_export_stage(
        self,
        stage: PipelineStage,
        state: PipelineState,
        run_dir: Path,
        log_path: Path,
    ) -> None:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"stage_id={stage.stage_id}\n")
            log.write("internal=phase1_run_scoped_matrix_replay_validation\n\n")
            try:
                report = load_phase1_replay_report(run_dir)
            except Exception as exc:  # noqa: BLE001 - runner records arbitrary stage failures.
                log.write(f"error={exc}\n")
                state.set_stage(stage.stage_id, "failed", exit_code=1, log_path=str(log_path), message=str(exc))
                state.finalize()
                raise subprocess.CalledProcessError(1, ["internal", "phase1_run_scoped_matrix_replay_validation"]) from exc
            log.write(json.dumps(report, indent=2) + "\n")

        matrix_report = report.get("genericity_support_matrix", {})
        if (
            report.get("status") == "passed"
            and matrix_report.get("relation_set_matches") is True
            and matrix_report.get("content_matches") is True
        ):
            state.set_stage(
                stage.stage_id,
                "passed",
                exit_code=0,
                log_path=str(log_path),
                message="run-scoped genericity matrix replay matched canonical matrix",
            )
            return

        message = "run-scoped genericity matrix replay mismatch"
        state.set_stage(stage.stage_id, "failed", exit_code=1, log_path=str(log_path), message=message)
        state.finalize()
        raise subprocess.CalledProcessError(1, ["internal", "phase1_run_scoped_matrix_replay_validation"])

    def _run_phase2_stage1_readiness_stage(
        self,
        stage: PipelineStage,
        state: PipelineState,
        run_dir: Path,
        log_path: Path,
    ) -> None:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"stage_id={stage.stage_id}\n")
            log.write("internal=phase2_stage1_run_scoped_execution\n\n")
            try:
                report = run_phase2_stage1_execution(self.repo_root, run_dir)
            except Exception as exc:  # noqa: BLE001 - runner records arbitrary stage failures.
                log.write(f"error={exc}\n")
                state.set_stage(stage.stage_id, "failed", exit_code=1, log_path=str(log_path), message=str(exc))
                state.finalize()
                raise subprocess.CalledProcessError(1, ["internal", "phase2_stage1_run_scoped_execution"]) from exc
            log.write(json.dumps(report, indent=2) + "\n")

        if report.get("stage1", {}).get("passed") is True:
            state.set_stage(
                stage.stage_id,
                "passed",
                exit_code=0,
                log_path=str(log_path),
                message="Stage1 score-genericity executed in run-scoped directory",
            )
            return

        message = "Phase II Stage1 readiness failed"
        state.set_stage(stage.stage_id, "failed", exit_code=1, log_path=str(log_path), message=message)
        state.finalize()
        raise subprocess.CalledProcessError(1, ["internal", "phase2_stage1_run_scoped_execution"])

    def _run_phase2_stage3_readiness_stage(
        self,
        stage: PipelineStage,
        state: PipelineState,
        run_dir: Path,
        log_path: Path,
    ) -> None:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"stage_id={stage.stage_id}\n")
            log.write("internal=phase2_stage3_run_scoped_execution\n\n")
            try:
                report = run_phase2_stage3_execution(self.repo_root, run_dir)
            except Exception as exc:  # noqa: BLE001 - runner records arbitrary stage failures.
                log.write(f"error={exc}\n")
                state.set_stage(stage.stage_id, "failed", exit_code=1, log_path=str(log_path), message=str(exc))
                state.finalize()
                raise subprocess.CalledProcessError(1, ["internal", "phase2_stage3_run_scoped_execution"]) from exc
            log.write(json.dumps(report, indent=2) + "\n")

        stage3 = report.get("stage3", {})
        if report.get("status") == "passed" and stage3.get("passed") is True:
            state.set_stage(
                stage.stage_id,
                "passed",
                exit_code=0,
                log_path=str(log_path),
                message="Stage3 audit-candidates executed in run-scoped directory",
            )
            return

        message = "Phase II Stage3 readiness failed"
        state.set_stage(stage.stage_id, "failed", exit_code=1, log_path=str(log_path), message=message)
        state.finalize()
        raise subprocess.CalledProcessError(1, ["internal", "phase2_stage3_run_scoped_execution"])

    def _run_phase2_stage4_execution_stage(
        self,
        stage: PipelineStage,
        state: PipelineState,
        run_dir: Path,
        log_path: Path,
    ) -> None:
        with log_path.open("w", encoding="utf-8") as log:
            log.write(f"stage_id={stage.stage_id}\n")
            log.write("internal=phase2_stage4_run_scoped_graph_construction\n\n")
            try:
                report = run_phase2_stage4_execution(self.repo_root, run_dir)
            except Exception as exc:  # noqa: BLE001 - runner records arbitrary stage failures.
                log.write(f"error={exc}\n")
                state.set_stage(stage.stage_id, "failed", exit_code=1, log_path=str(log_path), message=str(exc))
                state.finalize()
                raise subprocess.CalledProcessError(1, ["internal", "phase2_stage4_run_scoped_graph_construction"]) from exc
            log.write(json.dumps(report, indent=2) + "\n")

        if report.get("status") == "passed":
            state.set_stage(
                stage.stage_id,
                "passed",
                exit_code=0,
                log_path=str(log_path),
                message="Stage4 construct-graph executed in run-scoped directory",
            )
            return

        message = "Phase II Stage4 core graph construction failed"
        state.set_stage(stage.stage_id, "failed", exit_code=1, log_path=str(log_path), message=message)
        state.finalize()
        raise subprocess.CalledProcessError(1, ["internal", "phase2_stage4_run_scoped_graph_construction"])

    def _write_resolved_manifest(self, run_dir: Path) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / "manifest.resolved.json"
        path.write_text(json.dumps(self.manifest.to_resolved_dict(), indent=2) + "\n", encoding="utf-8")

    def _format_value(self, value: str, run_dir: Path) -> str:
        return value.format(repo_root=str(self.repo_root), run_dir=str(run_dir))
