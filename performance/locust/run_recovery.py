"""Run and validate a local Locust Recovery load test."""

import argparse
import csv
import os
import subprocess
from pathlib import Path

from dotenv import dotenv_values

from config import LoadConfig, Profile, recovery_expected_requests


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read a Locust CSV report."""
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def count_phases(
    samples: list[dict[str, str]],
    baseline_seconds: int,
    spike_seconds: int,
    recovery_seconds: int,
) -> list[int]:
    """Count requests in the three phases using CSV history."""
    if len(samples) < 2:
        raise ValueError("Insufficient history samples")

    start = int(samples[0]["Timestamp"])
    spike_end = baseline_seconds + spike_seconds
    end = spike_end + recovery_seconds
    phases = [0, 0, 0]

    for previous, current in zip(samples, samples[1:]):
        elapsed = int(current["Timestamp"]) - start
        count = int(current["Total Request Count"]) - int(
            previous["Total Request Count"]
        )

        if count < 0:
            raise ValueError("Request counter decreased")

        if elapsed <= baseline_seconds:
            phases[0] += count
        elif elapsed <= spike_end:
            phases[1] += count
        elif elapsed <= end:
            phases[2] += count

    return phases


def main() -> int:
    """Execute Recovery and validate request counts and load shape."""
    parser = argparse.ArgumentParser(description="Run Locust Recovery test")
    parser.add_argument("--baseline-rpm", type=float, default=60)
    parser.add_argument("--rpm", type=float, default=180)
    parser.add_argument("--baseline", type=int, default=10)
    parser.add_argument("--spike", type=int, default=10)
    parser.add_argument("--recovery", type=int, default=10)
    parser.add_argument("--tolerance-pct", type=float, default=20)
    args = parser.parse_args()

    config = LoadConfig(
        profile=Profile.RECOVERY,
        baseline_rpm=args.baseline_rpm,
        target_rpm=args.rpm,
        duration_seconds=args.baseline,
        peak_seconds=args.spike,
        recovery_seconds=args.recovery,
        tolerance_pct=args.tolerance_pct,
    )

    try:
        config.validate()
        if config.target_rpm <= config.baseline_rpm:
            raise ValueError("rpm must exceed baseline-rpm")
        expected = recovery_expected_requests(
            config,
            args.baseline + args.spike + args.recovery,
        )
        if expected < 1:
            raise ValueError("Profile must schedule at least one request")
    except ValueError as exc:
        parser.error(str(exc))

    duration = args.baseline + args.spike + args.recovery
    reports = Path("performance/reports")
    reports.mkdir(parents=True, exist_ok=True)

    prefix = reports / "recovery"
    stats_path = reports / "recovery_stats.csv"
    history_path = reports / "recovery_stats_history.csv"
    html_path = reports / "recovery.html"

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
            "LOCUST_BASELINE_RPM": str(args.baseline_rpm),
            "LOCUST_RECOVERY_RPM": str(args.rpm),
            "LOCUST_BASELINE_SECONDS": str(args.baseline),
            "LOCUST_SPIKE_SECONDS": str(args.spike),
            "LOCUST_RECOVERY_SECONDS": str(args.recovery),
        }
    )

    for path in (stats_path, history_path, html_path):
        path.unlink(missing_ok=True)

    command = [
        "uv",
        "run",
        "--locked",
        "locust",
        "-f",
        "performance/locust/recoveryfile.py",
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
        str(html_path),
    ]

    result = subprocess.run(command, env=env, check=False)
    if result.returncode != 0:
        print(f"Recovery result: FAIL — Locust exit {result.returncode}")
        return 1

    if not stats_path.is_file() or not history_path.is_file():
        print("Recovery result: FAIL — missing reports")
        return 1

    try:
        rows = read_rows(stats_path)
        summary = next(row for row in rows if row["Name"] == "Aggregated")

        total = int(summary["Request Count"])
        failures = int(summary["Failure Count"])
        login = sum(
            int(row["Request Count"])
            for row in rows
            if row["Name"] == "POST /login/access-token"
        )
        measured = total - login

        samples = [
            row for row in read_rows(history_path) if row["Name"] == "Aggregated"
        ]
        phases = count_phases(
            samples,
            args.baseline,
            args.spike,
            args.recovery,
        )
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        print(f"Recovery result: FAIL — invalid report: {exc}")
        return 1

    minimum = expected * (1 - args.tolerance_pct / 100)

    expected_phase_counts = [
        args.baseline * config.baseline_rps,
        args.spike * config.target_rps,
        args.recovery * config.baseline_rps,
    ]
    tolerance = args.tolerance_pct / 100

    phase_counts_ok = all(
        abs(actual - target) <= max(1, target * tolerance)
        for actual, target in zip(phases, expected_phase_counts)
    )

    baseline_rate = phases[0] / args.baseline
    spike_rate = phases[1] / args.spike
    recovery_rate = phases[2] / args.recovery

    shape_ok = spike_rate > baseline_rate and spike_rate > recovery_rate

    print(f"Duration: {duration}s")
    print(f"Baseline: {args.baseline_rpm:.1f} requests/min")
    print(f"Spike target: {args.rpm:.1f} requests/min")
    print(f"Expected (excluding login): {expected:.1f}")
    print(f"Measured (excluding login): {measured}")
    print(f"Minimum required: {minimum:.1f}")
    print(f"HTTP failures: {failures}")
    print(f"Phases (including login): {phases}")
    print(f"Phase counts within tolerance: {phase_counts_ok}")
    print(f"Spike higher than baseline/recovery: {shape_ok}")
    print("Latency recovery: NOT VERIFIED")

    if failures or measured < minimum or not phase_counts_ok or not shape_ok:
        print("Recovery result: FAIL")
        return 1

    print("Recovery result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
