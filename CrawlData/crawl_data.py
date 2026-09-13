"""Run link collection and detail extraction sequentially."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def run(command: list[str]) -> None:
    print("Running:", " ".join(command))
    completed = subprocess.run(command, cwd=BASE_DIR)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the complete crawl pipeline")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int, default=25)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--launch-delay", type=float, default=2.0)
    parser.add_argument("--skip-links", action="store_true", help="Skip phase 1")
    parser.add_argument("--skip-details", action="store_true", help="Skip phase 2")
    args = parser.parse_args()
    print(f"Pipeline PID: {os.getpid()}")

    common = [
        "--workers", str(args.workers),
        "--retries", str(args.retries),
        "--timeout", str(args.timeout),
        "--launch-delay", str(args.launch_delay),
    ]
    if not args.skip_links:
        run([
            sys.executable,
            str(BASE_DIR / "1_GetLinkNhaDat.py"),
            "--start-page", str(args.start_page),
            "--end-page", str(args.end_page),
            *common,
        ])
    if not args.skip_details:
        command = [
            sys.executable,
            str(BASE_DIR / "2_LocDataLink.py"),
            "--start-index", str(args.start_index),
            *common,
        ]
        if args.limit is not None:
            command.extend(["--limit", str(args.limit)])
        run(command)


if __name__ == "__main__":
    main()
