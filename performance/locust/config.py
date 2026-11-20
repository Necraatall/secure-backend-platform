"""Shared configuration for Locust performance profiles."""

from dataclasses import dataclass
from enum import StrEnum


class Profile(StrEnum):
    HOLD = "hold"
    BELL = "bell"
    HOLD_BELL = "hold_bell"
    RECOVERY = "recovery"


@dataclass(frozen=True, slots=True)
class LoadConfig:
    """Requested load profile and its target intensity."""

    profile: Profile = Profile.HOLD

    target_rpm: float = 60
    baseline_rpm: float = 60
    duration_seconds: int = 60

    ramp_up_seconds: int = 30
    peak_seconds: int = 30
    ramp_down_seconds: int = 30
    recovery_seconds: int = 60

    tolerance_pct: float = 20

    def validate(self) -> None:
        """Reject invalid or unsafe demonstration settings."""
        if not 0 < self.target_rpm <= 3000:
            raise ValueError("target_rpm must be between 0 and 3000")

        if not 0 < self.baseline_rpm <= 3000:
            raise ValueError("baseline_rpm must be between 0 and 3000")

        if self.profile == Profile.HOLD:
            if not 10 <= self.duration_seconds <= 3600:
                raise ValueError("duration_seconds must be 10..3600")
        else:
            durations = (
                self.ramp_up_seconds,
                self.peak_seconds,
                self.ramp_down_seconds,
            )
            if any(not 1 <= value <= 3600 for value in durations):
                raise ValueError("Bell phase durations must be 1..3600")

        if self.profile == Profile.RECOVERY:
            if not 10 <= self.recovery_seconds <= 3600:
                raise ValueError("recovery_seconds must be 10..3600")

        if not 0 <= self.tolerance_pct <= 50:
            raise ValueError("tolerance_pct must be 0..50")

    @property
    def target_rps(self) -> float:
        """Convert requested HTTP rate to requests per second."""
        return self.target_rpm / 60

    @property
    def baseline_rps(self) -> float:
        """Convert baseline HTTP rate to requests per second."""
        return self.baseline_rpm / 60


def bell_target_rpm(config: LoadConfig, elapsed_seconds: float) -> float:
    """Return the target request rate for a Bell profile."""
    config.validate()

    if config.profile != Profile.BELL:
        raise ValueError("Bell profile required")

    ramp_up = config.ramp_up_seconds
    peak_end = ramp_up + config.peak_seconds
    end = peak_end + config.ramp_down_seconds

    if elapsed_seconds < 0 or elapsed_seconds >= end:
        return 0.0
    if elapsed_seconds < ramp_up:
        return config.target_rpm * elapsed_seconds / ramp_up
    if elapsed_seconds < peak_end:
        return config.target_rpm

    return config.target_rpm * (end - elapsed_seconds) / config.ramp_down_seconds


def bell_expected_requests(config: LoadConfig, elapsed_seconds: float) -> float:
    """Calculate cumulative target requests under the Bell profile."""
    config.validate()

    if config.profile != Profile.BELL:
        raise ValueError("Bell profile required")

    up = config.ramp_up_seconds
    peak = config.peak_seconds
    down = config.ramp_down_seconds
    rate = config.target_rpm / 60
    t = max(0.0, elapsed_seconds)

    if t <= up:
        return rate * t * t / (2 * up)

    total = rate * up / 2
    t -= up

    if t <= peak:
        return total + rate * t

    total += rate * peak
    t = min(t - peak, down)

    return total + rate * (t - t * t / (2 * down))


def bell_request_time(config: LoadConfig, request_number: int) -> float | None:
    """Return scheduled time for a request, or None after the Bell ends."""
    if request_number < 1:
        raise ValueError("request_number must be positive")

    duration = config.ramp_up_seconds + config.peak_seconds + config.ramp_down_seconds

    if bell_expected_requests(config, duration) < request_number:
        return None

    low, high = 0.0, float(duration)

    for _ in range(50):
        middle = (low + high) / 2

        if bell_expected_requests(config, middle) < request_number:
            low = middle
        else:
            high = middle

    return high
