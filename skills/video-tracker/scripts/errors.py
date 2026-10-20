"""Shared exception types for video-tracker."""


class TrackerError(Exception):
    """Base error for the video tracker skill."""


class ConfigError(TrackerError):
    """Invalid or unreadable configuration."""


class VideoError(TrackerError):
    """Video file missing / unreadable / no frames."""


class TrackingError(TrackerError):
    """Tracking run failed (ROI out of bounds, tracker creation failed)."""


class FFTError(TrackerError):
    """FFT analysis input error."""
