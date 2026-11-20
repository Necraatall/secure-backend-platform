"""Run and validate a local Locust Bell load test."""

import argparse
import csv
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values

from config import LoadConfig, Profile, bell_expected_requests


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Locust Bell test")
    parser.add_argument("--rpm", type=float, default=120)
    parser.add_argument("--ramp-up", type=int, default=10)
    parser.add_argument("--peak", type=int, default=10)
    parser.add_argument("--ramp-down", type=int, default=10)
    parser.add_argument("--tolerance-pct", type=float, default=20)
    args = parser.parse_args()

    config = LoadConfig(
        profile=Profile.BELL,
        target_rpm=args.rpm,
        ramp_up_seconds=args.ramp_up,
        peak_seconds=args.peak,
        ramp_down_seconds=args.ramp_down,
        tolerance_pct=args.tolerance_pct,
    )
    try:
        config.validate()
    except ValueError as exc:
        parser.error(str(exc))

    duration = args.ramp_up + args.peak + args.ramp_down
    expected = bell_expected_requests(config, duration)

    if expected < 1:
        parser.error("Bell must schedule at least one request")

    env = os.environ.copy()
    env.update(
        {
            key: value
            for key, value in dotenv_values(".env").items()
            if value is not None
        }
    )
    env.update(
        {
            "LOCUST_BELL_RPM": str(args.rpm),
            "LOCUST_BELL_RAMP_UP": str(args.ramp_up),
            "LOCUST_BELL_PEAK": str(args.peak),
            "LOCUST_BELL_RAMP_DOWN": str(args.ramp_down),
        }
    )

    reports = Path("performance/reports")
    reports.mkdir(parents=True, exist_ok=True)
    prefix = reports / "bell"

    command = [
        "uv",
        "run",
        "--locked",
        "locust",
        "-f",
        "performance/locust/bellfile.py",
        "--headless",
        "--host",
        "http://localhost:8000",
        "--users",
        "1",
        "--spawn-rate",
        "1",
        "--run-time",
        f"{duration + 15}s",
        "--only-summary",
        "--exit-code-on-error",
        "1",
        "--csv",
        str(prefix),
        "--html",
        str(reports / "bell.html"),
    ]

    result = subprocess.run(command, env=env, check=False)
    if result.returncode != 0:
        print(f"Bell Locust exit code: {result.returncode}")
        return result.returncode

    with Path(f"{prefix}_stats.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))

    summary = next(
        (row for row in rows if row["Name"] == "Aggregated"),
        None,
    )
    if summary is None:
        print("Bell result: FAIL — missing statistics")
        return 1

    requests = int(summary["Request Count"])
    failures = int(summary["Failure Count"])
    login_requests = sum(
        int(row["Request Count"])
        for row in rows
        if row["Name"] == "POST /login/access-token"
    )

    measured = requests - login_requests
    minimum = expected * (1 - args.tolerance_pct / 100)

    print(f"Bell duration: {duration}s")
    print(f"Target peak: {args.rpm:.1f} HTTP requests/min")
    print(f"Expected requests (excluding login): {expected:.1f}")
    print(f"Measured requests (excluding login): {measured}")
    print(f"Minimum required: {minimum:.1f}")
    print(f"HTTP failures: {failures}")

    if failures or measured < minimum:
        print("Bell result: FAIL")
        return 1

    history = Path(f"{prefix}_stats_history.csv")
    if not history.exists():
        print("Bell result: FAIL — missing history")
        return 1

    with history.open(newline="") as file:
        samples = [row for row in csv.DictReader(file) if row["Name"] == "Aggregated"]

    if len(samples) < 2:
        print("Bell result: FAIL — insufficient history")
        return 1

    start = int(samples[0]["Timestamp"])
    up_end = args.ramp_up
    peak_end = up_end + args.peak
    end = peak_end + args.ramp_down
    phases = [0, 0, 0]

    for previous, current in zip(samples, samples[1:]):
        elapsed = int(current["Timestamp"]) - start
        count = int(current["Total Request Count"]) - int(
            previous["Total Request Count"]
        )

        if elapsed <= up_end:
            phases[0] += count
        elif elapsed <= peak_end:
            phases[1] += count
        elif elapsed <= end:
            phases[2] += count

    rates = [
        phases[0] / args.ramp_up,
        phases[1] / args.peak,
        phases[2] / args.ramp_down,
    ]

    print(f"Bell phases (including login): {phases}")

    if not (rates[1] > rates[0] and rates[1] > rates[2]):
        print("Bell result: FAIL — invalid load shape")
        return 1

    print("Bell result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
