#!/usr/bin/env python3
"""Run or inspect the reusable KG construction pipeline manifest."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.kg_pipeline.orchestration.pipeline_manifest import load_manifest  # noqa: E402
from src.kg_pipeline.orchestration.pipeline_runner import PipelineRunner  # noqa: E402

DEFAULT_MANIFEST = Path("configs/pipeline/kg_pipeline.default.json")
MODES = ["validate-frozen", "replay-frozen", "live-rerun", "construct-candidates"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--mode", choices=MODES, default="validate-frozen")
    parser.add_argument("--status", action="store_true", help="Print latest run state and exit")
    parser.add_argument("--state", type=Path, default=None, help="Specific pipeline_state.json to inspect")
    parser.add_argument("--dry-run", action="store_true", help="Print execution plan without running stages")
    parser.add_argument("--resume", action="store_true", help="Resume latest run state")
    parser.add_argument("--force-stage", action="append", default=[], metavar="STAGE_ID")
    parser.add_argument("--list-stages", action="store_true")
    parser.add_argument("--allow-live", action="store_true", help="Required before live WDQS/LLM stages can run")
    parser.add_argument("--allow-slurm", action="store_true", help="Required before SLURM stages can run")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.manifest)
    runner = PipelineRunner(manifest, repo_root=REPO_ROOT)

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
                force_stage_ids=args.force_stage,
            )
        )
        return 0
    if args.mode == "construct-candidates":
        print("construct-candidates mode is not implemented yet")
        return 2

    try:
        state = runner.run(
            args.mode,
            resume=args.resume,
            allow_live=args.allow_live,
            allow_slurm=args.allow_slurm,
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
