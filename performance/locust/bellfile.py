"""Run existing API scenarios with a time-controlled Bell profile."""

import os
from time import monotonic

import gevent

from config import LoadConfig, Profile, bell_request_time
from locustfile import BackendUser

BackendUser.abstract = True


class BellUser(BackendUser):
    abstract = False
    """Schedule API tasks according to the Bell load curve."""

    def on_start(self) -> None:
        self.config = LoadConfig(
            profile=Profile.BELL,
            target_rpm=float(os.getenv("LOCUST_BELL_RPM", "60")),
            ramp_up_seconds=int(os.getenv("LOCUST_BELL_RAMP_UP", "30")),
            peak_seconds=int(os.getenv("LOCUST_BELL_PEAK", "30")),
            ramp_down_seconds=int(os.getenv("LOCUST_BELL_RAMP_DOWN", "30")),
        )
        self.config.validate()

        super().on_start()

        self.started_at = monotonic()
        self.completed_tasks = 0

        first_request = bell_request_time(self.config, 1)
        if first_request is None:
            raise RuntimeError("Bell profile schedules no requests")

        gevent.sleep(first_request)

    def wait_time(self) -> float:
        """Wait until the next scheduled API task."""
        self.completed_tasks += 1

        next_time = bell_request_time(
            self.config,
            self.completed_tasks + 1,
        )

        if next_time is None:
            self.environment.runner.quit()
            return 0.0

        elapsed = monotonic() - self.started_at
        return max(0.0, next_time - elapsed)
