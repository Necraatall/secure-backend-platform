"""Run existing API scenarios with the Hold + Bell load profile."""

import os
from time import monotonic

import gevent

from config import LoadConfig, Profile, hold_bell_request_time
from locustfile import BackendUser

BackendUser.abstract = True


class HoldBellUser(BackendUser):
    """Execute API tasks at the scheduled Hold + Bell rate."""

    abstract = False

    def on_start(self) -> None:
        self.config = LoadConfig(
            profile=Profile.HOLD_BELL,
            baseline_rpm=float(os.getenv("LOCUST_BASELINE_RPM", "60")),
            target_rpm=float(os.getenv("LOCUST_HOLD_BELL_RPM", "120")),
            ramp_up_seconds=int(os.getenv("LOCUST_BELL_RAMP_UP", "10")),
            peak_seconds=int(os.getenv("LOCUST_BELL_PEAK", "10")),
            ramp_down_seconds=int(os.getenv("LOCUST_BELL_RAMP_DOWN", "10")),
        )
        self.config.validate()

        super().on_start()

        self.started_at = monotonic()
        self.completed_tasks = 0

        first_request = hold_bell_request_time(self.config, 1)
        if first_request is None:
            raise RuntimeError("Hold + Bell schedules no requests")

        gevent.sleep(first_request)

    def wait_time(self) -> float:
        """Wait until the next scheduled API task."""
        self.completed_tasks += 1

        next_time = hold_bell_request_time(
            self.config,
            self.completed_tasks + 1,
        )

        if next_time is None:
            self.environment.runner.quit()
            return 0.0

        elapsed = monotonic() - self.started_at
        return max(0.0, next_time - elapsed)
