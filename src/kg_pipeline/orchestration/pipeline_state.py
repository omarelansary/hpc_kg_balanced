"""State persistence for resumable KG pipeline runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGE_STATUSES = {"pending", "skipped", "running", "passed", "failed", "blocked"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@dataclass
class PipelineState:
    """JSON-backed state for one pipeline run."""

    path: Path
    data: dict[str, Any]

    @classmethod
    def create(
        cls,
        path: str | Path,
        run_id: str,
        manifest_path: str,
        mode: str,
        stage_ids: list[str],
    ) -> "PipelineState":
        now = utc_now_iso()
        data = {
            "schema_version": "kg-pipeline-state-v1",
            "run_id": run_id,
            "manifest_path": manifest_path,
            "mode": mode,
            "created_at_utc": now,
            "updated_at_utc": now,
            "overall_status": "running",
            "stages": {
                stage_id: {
                    "status": "pending",
                    "started_at_utc": None,
                    "finished_at_utc": None,
                    "exit_code": None,
                    "log_path": None,
                    "message": None,
                }
                for stage_id in stage_ids
            },
        }
        state = cls(Path(path), data)
        state.save()
        return state

    @classmethod
    def load(cls, path: str | Path) -> "PipelineState":
        state_path = Path(path)
        return cls(state_path, json.loads(state_path.read_text(encoding="utf-8")))

    def save(self) -> None:
        self.data["updated_at_utc"] = utc_now_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2) + "\n", encoding="utf-8")

    def set_stage(
        self,
        stage_id: str,
        status: str,
        *,
        exit_code: int | None = None,
        log_path: str | None = None,
        message: str | None = None,
    ) -> None:
        if status not in STAGE_STATUSES:
            raise ValueError(f"invalid stage status: {status}")
        stage = self.data["stages"].setdefault(stage_id, {})
        if status == "running":
            stage["started_at_utc"] = utc_now_iso()
            stage["finished_at_utc"] = None
        elif status in {"passed", "failed", "blocked", "skipped"}:
            stage["finished_at_utc"] = utc_now_iso()
        stage["status"] = status
        stage["exit_code"] = exit_code
        if log_path is not None:
            stage["log_path"] = log_path
        if message is not None:
            stage["message"] = message
        self.save()

    def finalize(self) -> None:
        statuses = [row.get("status") for row in self.data.get("stages", {}).values()]
        if any(status == "failed" for status in statuses):
            overall = "failed"
        elif any(status == "blocked" for status in statuses):
            overall = "blocked"
        elif all(status in {"passed", "skipped"} for status in statuses):
            overall = "passed"
        else:
            overall = "running"
        self.data["overall_status"] = overall
        self.save()


def latest_state_path(state_root: str | Path) -> Path | None:
    root = Path(state_root)
    if not root.is_dir():
        return None
    candidates = sorted(root.glob("*/pipeline_state.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None
