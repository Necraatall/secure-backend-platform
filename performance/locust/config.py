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
