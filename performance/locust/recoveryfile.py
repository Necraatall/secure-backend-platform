"""Run existing API scenarios with the Recovery load profile."""

import os
from time import monotonic

import gevent

from config import LoadConfig, Profile, recovery_request_time
from locustfile import BackendUser

BackendUser.abstract = True


class RecoveryUser(BackendUser):
    """Execute API tasks according to the Recovery load schedule."""

    abstract = False

    def on_start(self) -> None:
        self.config = LoadConfig(
            profile=Profile.RECOVERY,
            baseline_rpm=float(os.getenv("LOCUST_BASELINE_RPM", "60")),
            target_rpm=float(os.getenv("LOCUST_RECOVERY_RPM", "180")),
            duration_seconds=int(os.getenv("LOCUST_BASELINE_SECONDS", "10")),
            peak_seconds=int(os.getenv("LOCUST_SPIKE_SECONDS", "10")),
            recovery_seconds=int(os.getenv("LOCUST_RECOVERY_SECONDS", "10")),
        )
        self.config.validate()

        super().on_start()

        self.started_at = monotonic()
        self.completed_tasks = 0

        first_request = recovery_request_time(self.config, 1)
        if first_request is None:
            raise RuntimeError("Recovery profile schedules no requests")

        gevent.sleep(first_request)

    def wait_time(self) -> float:
        """Wait until the next scheduled API task."""
        self.completed_tasks += 1

        next_time = recovery_request_time(
            self.config,
            self.completed_tasks + 1,
        )

        if next_time is None:
            self.environment.runner.quit()
            return 0.0

        elapsed = monotonic() - self.started_at
        return max(0.0, next_time - elapsed)
