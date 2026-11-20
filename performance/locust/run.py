"""Run an existing Locust performance profile."""

import subprocess
import sys
from pathlib import Path

RUNNERS = {
    "hold": "run_hold.py",
    "bell": "run_bell.py",
    "hold-bell": "run_hold_bell.py",
    "recovery": "run_recovery.py",
}


def main() -> int:
    """Dispatch a profile and forward its CLI arguments."""
    if len(sys.argv) < 2 or sys.argv[1] not in RUNNERS:
        print("Usage: run.py <profile> [profile options]")
        print("Available profiles:", ", ".join(RUNNERS))
        return 2

    profile = sys.argv[1]
    runner = Path(__file__).with_name(RUNNERS[profile])

    result = subprocess.run(
        [sys.executable, str(runner), *sys.argv[2:]],
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
