"""Run a configurable local Locust Hold test."""

import argparse
import csv
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Locust Hold test")
    parser.add_argument("--rpm", type=float, default=60)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--tolerance-pct", type=float, default=20)
    args = parser.parse_args()

    if not 0 < args.rpm <= 3000:
        parser.error("--rpm must be between 0 and 3000")
    if not 10 <= args.duration <= 3600:
        parser.error("--duration must be between 10 and 3600 seconds")

    if not 0 <= args.tolerance_pct <= 50:
        parser.error("--tolerance-pct must be between 0 and 50")

    env = os.environ.copy()
    env.update(
        {
            key: value
            for key, value in dotenv_values(".env").items()
            if value is not None
        }
    )
    env["LOCUST_HOLD_RPM"] = str(args.rpm)

    reports = Path("performance/reports")
    reports.mkdir(parents=True, exist_ok=True)
    prefix = reports / "hold"

    command = [
        "uv",
        "run",
        "--locked",
        "locust",
        "-f",
        "performance/locust/locustfile.py",
        "--headless",
        "--host",
        "http://localhost:8000",
        "--users",
        "1",
        "--spawn-rate",
        "1",
        "--run-time",
        f"{args.duration}s",
        "--only-summary",
        "--exit-code-on-error",
        "1",
        "--csv",
        str(prefix),
    ]

    result = subprocess.run(command, env=env, check=False)
    if result.returncode != 0:
        return result.returncode

    with Path(f"{prefix}_stats.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))

    summary = next(
        (row for row in rows if row["Name"] == "Aggregated"),
        None,
    )
    if summary is None:
        raise RuntimeError("Missing aggregated Locust statistics")

    requests = int(summary["Request Count"])
    failures = int(summary["Failure Count"])
    actual_rps = float(summary["Requests/s"])

    print(f"Target: {args.rpm:.1f} tasks/min")
    print(f"Actual: {actual_rps:.2f} HTTP requests/s")
    print(f"Requests: {requests}, failures: {failures}")

    completed_tasks = sum(
        int(row["Request Count"])
        for row in rows
        if row["Name"] not in ("Aggregated", "POST /login/access-token")
    )
    minimum = args.rpm * args.duration / 60 * (1 - args.tolerance_pct / 100)

    print(f"Completed tasks: {completed_tasks}")
    print(f"Minimum required: {minimum:.1f}")

    if requests == 0 or failures or completed_tasks < minimum:
        print("Hold result: FAIL")
        return 1

    print("Hold result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
