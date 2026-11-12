"""Lap recorder state machine.

The recorder is deliberately independent of Windows.  It consumes decoded
``Sample`` objects, so the same state machine is tested on macOS with a fake
source and on Windows with the real shared-memory reader.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .csvio import CsvWriter, TelemetryRow
from .errors import GameClosed, SharedMemoryUnavailable
from .mapping import Sample
from .packets import AC_LIVE, AC_OFF, AC_PAUSE, AC_REPLAY


@dataclass
class RecorderOptions:
    laps: int | None = 1
    min_samples: int = 20
    stale_timeout_s: float = 5.0
    max_distance_jump_m: float = 500.0
    poll_hz: float = 50.0


@dataclass
class RecordResult:
    out_path: Path
    laps_completed: int = 0
    partial_laps: int = 0
    rows_written: int = 0
    game_closed: bool = False
    stopped_by_user: bool = False
    messages: list[str] = field(default_factory=list)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class Recorder:
    def __init__(
        self,
        out_path: str | Path,
        options: RecorderOptions | None = None,
        *,
        reporter: Callable[[str], None] = print,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.out_path = Path(out_path)
        self.options = options or RecorderOptions()
        self.reporter = reporter
        self.clock = clock
        self.sleep = sleep
        self.result = RecordResult(out_path=self.out_path)
        self._writer: CsvWriter | None = None
        self._current_lap: int | None = None
        self._current_rows: list[TelemetryRow] = []
        self._last_completed_laps = 0
        self._last_distance: float | None = None
        self._last_packet_id: int | None = None
        self._lap_start_wall: float | None = None
        self._session: int | None = None
        self._paused = False
        self._replay_paused = False
        self._stop = False
        self._last_new_sample_wall: float | None = None
        self._last_elapsed_s = 0.0

    def _say(self, message: str) -> None:
        self.result.messages.append(message)
        self.reporter(message)

    def run(self, source) -> RecordResult:
        self._writer = CsvWriter(self.out_path)
        self._say(f"Writing {self.out_path}")
        try:
            while not self._stop:
                try:
                    sample = source.poll()
                except (GameClosed, SharedMemoryUnavailable, OSError) as exc:
                    self.result.game_closed = True
                    self._say(f"Game closed: {exc}")
                    self._finish_lap(partial=True, reason="game closed")
                    break
                except StopIteration:
                    break

                if sample is None:
                    if getattr(source, "finished", False):
                        break
                    now = self.clock()
                    if (
                        self._last_new_sample_wall is not None
                        and now - self._last_new_sample_wall
                        > self.options.stale_timeout_s
                    ):
                        self.result.game_closed = True
                        self._say(
                            "Game closed or stopped updating: no new telemetry for "
                            f"{self.options.stale_timeout_s:.1f} s."
                        )
                        self._finish_lap(partial=True, reason="telemetry stopped")
                        break
                    self.sleep(1.0 / max(1.0, self.options.poll_hz))
                    continue

                self._last_new_sample_wall = self.clock()
                try:
                    self.consume(sample)
                except (GameClosed, SharedMemoryUnavailable, OSError) as exc:
                    self.result.game_closed = True
                    self._say(f"Game closed: {exc}")
                    self._finish_lap(partial=True, reason="game closed")
                    break
        except KeyboardInterrupt:
            self.result.stopped_by_user = True
            self._say("Stopped by user.")
            self._finish_lap(partial=True, reason="stopped by user")
        finally:
            self._finish_lap(partial=True, reason="recording ended")
            if self._writer is not None:
                self._writer.close()
            close = getattr(source, "close", None)
            if callable(close):
                close()
        self.result.rows_written = self._writer.rows_written if self._writer else 0
        return self.result

    def consume(self, sample: Sample) -> None:
        """Process one decoded sample.  Public for the Windows fake-game test."""

        if self._stop:
            return
        graphics = sample.graphics

        if graphics.status == AC_OFF:
            raise GameClosed("The game is off (menu or closed).")
        if graphics.status == AC_REPLAY:
            if not self._replay_paused:
                self._say("Replay is running; recording is paused.")
                self._replay_paused = True
            return
        if graphics.status == AC_PAUSE:
            if not self._paused:
                self._say("Game paused; recording paused.")
                self._paused = True
            return
        if graphics.status != AC_LIVE:
            return
        if self._paused:
            self._say("Game resumed.")
            self._paused = False
        self._replay_paused = False

        if graphics.packet_id == self._last_packet_id:
            return
        self._last_packet_id = graphics.packet_id

        distance = graphics.distance_traveled_m
        speed = sample.physics.speed_kmh
        if not math.isfinite(distance) or not math.isfinite(speed):
            return
        if distance < 0 or speed < 0:
            return

        if self._current_lap is None:
            self._start_lap(graphics.completed_laps + 1, sample)
        elif graphics.session != self._session:
            self._say("Session changed; starting a new lap.")
            self._finish_lap(partial=True, reason="session changed")
            if self._stop:
                return
            self._start_lap(graphics.completed_laps + 1, sample)
        elif graphics.completed_laps > self._last_completed_laps:
            self._finish_lap(partial=False, reason="lap completed")
            self._last_completed_laps = graphics.completed_laps
            if self._stop:
                return
            self._start_lap(graphics.completed_laps + 1, sample)
        elif (
            self._last_distance is not None
            and distance < self._last_distance - 50.0
        ):
            next_lap = (self._current_lap or 0) + 1
            self._say("Distance reset; starting a new lap.")
            self._finish_lap(partial=True, reason="distance reset")
            if self._stop:
                return
            self._start_lap(next_lap, sample)

        if self._last_distance is not None:
            if distance > self._last_distance + self.options.max_distance_jump_m:
                self._say(
                    f"Ignoring a {distance - self._last_distance:.0f} m telemetry jump "
                    f"at {distance:.0f} m."
                )
                return

        if self._current_lap is None:
            return
        if graphics.current_time_ms > 0:
            elapsed = graphics.current_time_s
        else:
            assert self._lap_start_wall is not None
            elapsed = max(0.0, sample.timestamp_s - self._lap_start_wall)
        if not math.isfinite(elapsed) or elapsed < 0 or elapsed > 24 * 3600:
            return
        if elapsed + 0.5 < self._last_elapsed_s:
            next_lap = (self._current_lap or 0) + 1
            self._say("Lap timer reset; starting a new lap.")
            self._finish_lap(partial=True, reason="lap timer reset")
            if self._stop:
                return
            self._start_lap(next_lap, sample)
            elapsed = 0.0

        row = TelemetryRow(
            lap_number=self._current_lap,
            distance_m=distance,
            elapsed_s=elapsed,
            speed_kmh=speed,
            throttle=_clamp(sample.physics.gas),
            brake=_clamp(sample.physics.brake),
        )
        self._current_rows.append(row)
        self._last_distance = distance
        self._last_elapsed_s = elapsed

    def _start_lap(self, lap_number: int, sample: Sample) -> None:
        self._current_lap = lap_number
        self._current_rows = []
        self._last_completed_laps = sample.graphics.completed_laps
        self._last_distance = None
        self._last_elapsed_s = 0.0
        self._lap_start_wall = sample.timestamp_s
        self._session = sample.graphics.session
        self._say(f"Recording lap {lap_number}...")

    def _finish_lap(self, *, partial: bool, reason: str) -> None:
        if self._current_lap is None:
            return
        lap_number = self._current_lap
        rows = self._current_rows
        self._current_lap = None
        self._current_rows = []
        self._last_distance = None
        if not rows:
            return
        if len(rows) < self.options.min_samples:
            self._say(
                f"Discarding lap {lap_number}: only {len(rows)} samples "
                f"(minimum {self.options.min_samples})."
            )
            return
        assert self._writer is not None
        written = self._writer.write_lap(lap_number, rows)
        if partial:
            self.result.partial_laps += 1
            self._say(
                f"Saved partial lap {lap_number} ({written} samples) because {reason}."
            )
        else:
            self.result.laps_completed += 1
            self._say(f"Saved lap {lap_number} ({written} samples).")
            if (
                self.options.laps is not None
                and self.result.laps_completed >= self.options.laps
            ):
                self._stop = True
                self._say(
                    f"Reached the requested {self.options.laps} completed lap(s)."
                )
