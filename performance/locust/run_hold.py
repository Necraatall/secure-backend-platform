"""Run a configurable local Locust Hold test."""

import argparse
import csv
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values

from config import LoadConfig, Profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Locust Hold test")
    parser.add_argument("--rpm", type=float, default=60)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--tolerance-pct", type=float, default=20)
    args = parser.parse_args()

    config = LoadConfig(
        profile=Profile.HOLD,
        target_rpm=args.rpm,
        duration_seconds=args.duration,
        tolerance_pct=args.tolerance_pct,
    )
    try:
        config.validate()
    except ValueError as exc:
        parser.error(str(exc))

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
        "--html",
        str(reports / "hold.html"),
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

    print(f"Target: {args.rpm:.1f} HTTP requests/min (excluding login)")
    print(f"Actual: {actual_rps:.2f} HTTP requests/s")
    print(f"Requests: {requests}, failures: {failures}")

    completed_tasks = sum(
        int(row["Request Count"])
        for row in rows
        if row["Name"] not in ("Aggregated", "POST /login/access-token")
    )
    minimum = args.rpm * args.duration / 60 * (1 - args.tolerance_pct / 100)

    print(f"Measured HTTP requests (excluding login): {completed_tasks}")
    print(f"Minimum required: {minimum:.1f}")

    history_path = Path(f"{prefix}_stats_history.csv")
    with history_path.open(newline="") as file:
        history = [row for row in csv.DictReader(file) if row["Name"] == "Aggregated"]

    if len(history) >= 2:
        start = int(history[0]["Timestamp"])
        buckets: dict[int, int] = {}

        for previous, current in zip(history, history[1:]):
            elapsed = int(current["Timestamp"]) - start
            bucket = max(0, (elapsed - 1) // 10)
            count = int(current["Total Request Count"]) - int(
                previous["Total Request Count"]
            )
            buckets[bucket] = buckets.get(bucket, 0) + count

        print("HTTP requests by 10-second interval:")
        for bucket, count in sorted(buckets.items()):
            begin = bucket * 10
            print(f"  {begin:02d}-{begin + 10:02d}s: {count}")

    if requests == 0 or failures or completed_tasks < minimum:
        print("Hold result: FAIL")
        return 1

    print("Hold result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
