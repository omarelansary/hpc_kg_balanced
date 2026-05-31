#!/usr/bin/env python3
"""Run or inspect the reusable KG construction pipeline manifest."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.orchestration.candidate_packaging import package_frozen_candidate  # noqa: E402
from src.kg_pipeline.orchestration.pipeline_manifest import load_manifest  # noqa: E402
from src.kg_pipeline.orchestration.pipeline_runner import PipelineRunner  # noqa: E402
from src.kg_pipeline.orchestration.pipeline_state import PipelineState, default_run_id  # noqa: E402

DEFAULT_MANIFEST = Path("configs/pipeline/kg_pipeline.default.json")
MODES = ["validate-frozen", "replay-frozen", "live-rerun", "slurm-rerun", "construct-candidates"]
CONSTRUCT_STAGE_ID = "construct_candidates_package_frozen"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--mode", choices=MODES, default="validate-frozen")
    parser.add_argument("--status", action="store_true", help="Print latest run state and exit")
    parser.add_argument("--state", type=Path, default=None, help="Specific pipeline_state.json to inspect")
    parser.add_argument(
        "--state-root",
        type=Path,
        default=None,
        help="Override the pipeline run root. Defaults to KG_PIPELINE_STATE_ROOT or the manifest default.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print execution plan without running stages")
    parser.add_argument("--resume", action="store_true", help="Resume latest run state")
    parser.add_argument("--force-stage", action="append", default=[], metavar="STAGE_ID")
    parser.add_argument("--list-stages", action="store_true")
    parser.add_argument("--allow-live", action="store_true", help="Required before live WDQS/LLM stages can run")
    parser.add_argument("--allow-slurm", action="store_true", help="Required before SLURM stages can run")
    parser.add_argument(
        "--execute-stage4",
        action="store_true",
        help="Allow run-scoped Phase II Stage4 construct-graph execution in replay-frozen mode.",
    )
    parser.add_argument("--candidate-id", default=None, help="Candidate id for construct-candidates mode")
    parser.add_argument("--from-frozen", action="store_true", help="Package an existing frozen registered candidate")
    parser.add_argument("--generate", action="store_true", help="Reserved for future graph generation; blocked in Level 1")
    return parser.parse_args()


def resolve_state_root(args: argparse.Namespace, manifest) -> Path:
    """Resolve the state root from CLI, environment, or manifest default."""
    if args.state_root is not None:
        return args.state_root
    env_root = os.environ.get("KG_PIPELINE_STATE_ROOT")
    if env_root:
        return Path(env_root)
    return Path(manifest.default_state_root)


def run_construct_candidates(args: argparse.Namespace, manifest, state_root: Path) -> int:
    if args.generate:
        print("graph generation is not implemented in Level 1; no graph generated", file=sys.stderr)
        return 2
    if not args.from_frozen:
        print("Level 1 construct-candidates requires --from-frozen", file=sys.stderr)
        return 2
    if not args.candidate_id:
        print("Level 1 construct-candidates requires --candidate-id", file=sys.stderr)
        return 2

    run_id = default_run_id()
    run_dir = state_root / run_id
    state = PipelineState.create(
        run_dir / "pipeline_state.json",
        run_id,
        str(manifest.path),
        "construct-candidates",
        [CONSTRUCT_STAGE_ID],
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.resolved.json").write_text(
        json.dumps(manifest.to_resolved_dict(), indent=2) + "\n",
        encoding="utf-8",
    )
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{CONSTRUCT_STAGE_ID}.log"

    state.set_stage(
        CONSTRUCT_STAGE_ID,
        "running",
        log_path=str(log_path),
        message="packaging frozen candidate",
    )
    try:
        with log_path.open("w", encoding="utf-8") as log:
            result = package_frozen_candidate(
                repo_root=REPO_ROOT,
                run_dir=run_dir,
                candidate_id=args.candidate_id,
                log=log,
            )
    except Exception as exc:  # noqa: BLE001 - command-line runner should record any packaging failure.
        state.set_stage(CONSTRUCT_STAGE_ID, "failed", exit_code=1, log_path=str(log_path), message=str(exc))
        state.finalize()
        print(f"construct-candidates failed: {exc}", file=sys.stderr)
        print(f"state={state.path}")
        return 1

    state.set_stage(
        CONSTRUCT_STAGE_ID,
        "passed",
        exit_code=0,
        log_path=str(log_path),
        message="packaged frozen candidate",
    )
    state.finalize()
    print(f"run_id={run_id}")
    print(f"state={state.path}")
    print(f"candidate_package={run_dir / 'candidates' / args.candidate_id}")
    print(f"source_graph_sha256={result['source_graph_sha256']}")
    print(f"packaged_graph_sha256={result['packaged_graph_sha256']}")
    print(f"overall_status={state.data.get('overall_status')}")
    return 0


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest)
    state_root = resolve_state_root(args, manifest)
    runner = PipelineRunner(manifest, repo_root=REPO_ROOT, state_root=state_root)

    if args.list_stages:
        print(runner.list_stages())
        return 0
    if args.status:
        print(runner.status(args.state))
        return 0
    if args.dry_run:
        print(
            runner.dry_run(
                args.mode,
                allow_live=args.allow_live,
                allow_slurm=args.allow_slurm,
                execute_stage4=args.execute_stage4,
                force_stage_ids=args.force_stage,
            )
        )
        return 0
    if args.mode == "construct-candidates":
        return run_construct_candidates(args, manifest, state_root)

    try:
        state = runner.run(
            args.mode,
            resume=args.resume,
            allow_live=args.allow_live,
            allow_slurm=args.allow_slurm,
            execute_stage4=args.execute_stage4,
            force_stage_ids=args.force_stage,
        )
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except PermissionError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"stage command failed: {exc.cmd!r}", file=sys.stderr)
        return exc.returncode or 1

    print(f"run_id={state.data.get('run_id')}")
    print(f"state={state.path}")
    print(f"overall_status={state.data.get('overall_status')}")
    return 0 if state.data.get("overall_status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
