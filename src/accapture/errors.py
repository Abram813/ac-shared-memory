"""Exceptions raised by accapture."""

from __future__ import annotations


class AccaptureError(RuntimeError):
    """Base class for expected, user-facing errors."""


class UnsupportedPlatform(AccaptureError):
    """A Windows-only operation was attempted on another platform."""


class SharedMemoryUnavailable(AccaptureError):
    """A game shared-memory mapping could not be opened or read."""


class GameClosed(AccaptureError):
    """The game stopped updating or closed while recording."""


class DecodeError(AccaptureError):
    """A shared-memory packet was too short or malformed."""


class RaceCoachNotFound(AccaptureError):
    """The RaceCoach command could not be found or started."""
