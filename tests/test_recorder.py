from __future__ import annotations

import csv
from pathlib import Path

import pytest

from accapture.csvio import CSV_HEADER
from accapture.errors import GameClosed
from accapture.packets import AC_OFF
from accapture.recorder import Recorder, RecorderOptions

from .helpers import ListSource, RaisingSource, make_sample


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def make_lap_samples(
    *,
    lap: int = 0,
    count: int = 5,
    start_packet: int = 1,
) -> list:
    samples = []
    for index in range(count):
        samples.append(
            make_sample(
                packet_id=start_packet + index,
                distance=index * 10.0,
                elapsed_ms=index * 1000,
                speed=100.0 + index,
                completed_laps=lap,
                timestamp=index * 0.02,
            )
        )
    return samples


def test_records_one_completed_lap(tmp_path: Path) -> None:
    samples = make_lap_samples(count=5)
    samples.append(
        make_sample(
            packet_id=99,
            distance=0.0,
            elapsed_ms=0,
            speed=240.0,
            completed_laps=1,
            timestamp=0.2,
        )
    )
    source = ListSource(samples)
    messages: list[str] = []
    recorder = Recorder(
        tmp_path / "session.csv",
        RecorderOptions(laps=1, min_samples=1),
        reporter=messages.append,
        sleep=lambda _seconds: None,
    )
    result = recorder.run(source)

    assert result.laps_completed == 1
    assert result.partial_laps == 0
    assert result.rows_written == 5
    assert source.closed
    rows = read_csv(tmp_path / "session.csv")
    assert list(rows[0]) == CSV_HEADER
    assert len(rows) == 5
    assert {row["lap_number"] for row in rows} == {"1"}
    assert rows[0]["distance_m"] == "0.000"
    assert rows[-1]["distance_m"] == "40.000"
    assert rows[-1]["elapsed_s"] == "4.000"
    assert any("Recording lap 1" in message for message in messages)
    assert any("Saved lap 1" in message for message in messages)


def test_records_two_laps_and_stops(tmp_path: Path) -> None:
    samples = make_lap_samples(lap=0, count=3, start_packet=1)
    samples.append(
        make_sample(
            packet_id=10,
            distance=0.0,
            elapsed_ms=0,
            completed_laps=1,
            timestamp=0.06,
        )
    )
    samples.extend(make_lap_samples(lap=1, count=3, start_packet=11))
    samples.append(
        make_sample(
            packet_id=20,
            distance=0.0,
            elapsed_ms=0,
            completed_laps=2,
            timestamp=0.12,
        )
    )
    source = ListSource(samples)
    recorder = Recorder(
        tmp_path / "two laps.csv",
        RecorderOptions(laps=2, min_samples=1),
        reporter=lambda _message: None,
        sleep=lambda _seconds: None,
    )
    result = recorder.run(source)

    assert result.laps_completed == 2
    assert result.partial_laps == 0
    rows = read_csv(tmp_path / "two laps.csv")
    assert {row["lap_number"] for row in rows} == {"1", "2"}
    # The first sample of lap 2 is the completed-lap notification (distance 0),
    # followed by the three samples of lap 2.
    assert len([row for row in rows if row["lap_number"] == "2"]) == 4


def test_pause_is_skipped_and_elapsed_time_is_not_inflated(tmp_path: Path) -> None:
    samples = [
        make_sample(packet_id=1, distance=0, elapsed_ms=0, completed_laps=0),
        make_sample(packet_id=2, distance=10, elapsed_ms=500, completed_laps=0),
        make_sample(packet_id=3, distance=10, elapsed_ms=500, completed_laps=0, status=3),
        make_sample(packet_id=4, distance=20, elapsed_ms=1000, completed_laps=0),
        make_sample(packet_id=5, distance=0, elapsed_ms=0, completed_laps=1),
    ]
    source = ListSource(samples)
    messages: list[str] = []
    recorder = Recorder(
        tmp_path / "paused.csv",
        RecorderOptions(laps=1, min_samples=1),
        reporter=messages.append,
        sleep=lambda _seconds: None,
    )
    result = recorder.run(source)

    rows = read_csv(tmp_path / "paused.csv")
    assert len(rows) == 3
    assert [row["elapsed_s"] for row in rows] == ["0.000", "0.500", "1.000"]
    assert any("Game paused" in message for message in messages)
    assert any("Game resumed" in message for message in messages)
    assert result.laps_completed == 1


def test_distance_reset_starts_a_new_lap(tmp_path: Path) -> None:
    samples = [
        make_sample(packet_id=1, distance=0, elapsed_ms=0, completed_laps=0),
        make_sample(packet_id=2, distance=100, elapsed_ms=500, completed_laps=0),
        make_sample(packet_id=3, distance=200, elapsed_ms=1000, completed_laps=0),
        make_sample(packet_id=4, distance=0, elapsed_ms=0, completed_laps=0),
        make_sample(packet_id=5, distance=0, elapsed_ms=0, completed_laps=1),
    ]
    source = ListSource(samples)
    messages: list[str] = []
    recorder = Recorder(
        tmp_path / "reset.csv",
        RecorderOptions(laps=1, min_samples=1),
        reporter=messages.append,
        sleep=lambda _seconds: None,
    )
    result = recorder.run(source)

    assert result.laps_completed == 1
    assert result.partial_laps == 1
    rows = read_csv(tmp_path / "reset.csv")
    assert {row["lap_number"] for row in rows} == {"1", "2"}
    assert any("Distance reset" in message for message in messages)


def test_duplicate_packet_id_is_ignored(tmp_path: Path) -> None:
    samples = [
        make_sample(packet_id=1, distance=0, elapsed_ms=0, completed_laps=0),
        make_sample(packet_id=1, distance=50, elapsed_ms=1000, completed_laps=0),
        make_sample(packet_id=2, distance=0, elapsed_ms=0, completed_laps=1),
    ]
    source = ListSource(samples)
    recorder = Recorder(
        tmp_path / "duplicate.csv",
        RecorderOptions(laps=1, min_samples=1),
        reporter=lambda _message: None,
        sleep=lambda _seconds: None,
    )
    result = recorder.run(source)
    rows = read_csv(tmp_path / "duplicate.csv")
    assert len(rows) == 1
    assert rows[0]["distance_m"] == "0.000"
    assert result.laps_completed == 1


def test_game_closed_saves_a_partial_lap(tmp_path: Path) -> None:
    samples = make_lap_samples(count=3)
    source = RaisingSource(samples, GameClosed("test game closed"))
    messages: list[str] = []
    recorder = Recorder(
        tmp_path / "closed.csv",
        RecorderOptions(laps=1, min_samples=1),
        reporter=messages.append,
        sleep=lambda _seconds: None,
    )
    result = recorder.run(source)

    assert result.game_closed
    assert result.laps_completed == 0
    assert result.partial_laps == 1
    assert result.rows_written == 3
    assert any("Game closed" in message for message in messages)
    assert any("Saved partial lap 1" in message for message in messages)


def test_game_off_status_is_reported_as_closed(tmp_path: Path) -> None:
    source = ListSource(
        [make_sample(packet_id=1, status=AC_OFF, completed_laps=0)]
    )
    messages: list[str] = []
    recorder = Recorder(
        tmp_path / "off.csv",
        RecorderOptions(laps=1, min_samples=1),
        reporter=messages.append,
        sleep=lambda _seconds: None,
    )
    result = recorder.run(source)
    assert result.game_closed
    assert any("Game closed" in message for message in messages)
    assert read_csv(tmp_path / "off.csv") == []


def test_stale_telemetry_is_treated_as_game_closed(tmp_path: Path) -> None:
    class NoneAfterSource:
        def __init__(self, sample) -> None:
            self.sample = sample
            self.first = True
            self.finished = False

        def poll(self):
            if self.first:
                self.first = False
                return self.sample
            return None

        def close(self) -> None:
            self.finished = True

    clock_values = iter([0.0, 0.0, 10.0])
    source = NoneAfterSource(make_sample(packet_id=1, distance=0, completed_laps=0))
    messages: list[str] = []
    recorder = Recorder(
        tmp_path / "stale.csv",
        RecorderOptions(laps=1, min_samples=1, stale_timeout_s=5.0),
        reporter=messages.append,
        clock=lambda: next(clock_values),
        sleep=lambda _seconds: None,
    )
    result = recorder.run(source)
    assert result.game_closed
    assert result.partial_laps == 1
    assert any("stopped updating" in message for message in messages)


def test_lap_with_too_few_samples_is_discarded(tmp_path: Path) -> None:
    samples = make_lap_samples(count=2)
    samples.append(
        make_sample(packet_id=9, completed_laps=1, distance=0, elapsed_ms=0)
    )
    source = ListSource(samples)
    messages: list[str] = []
    recorder = Recorder(
        tmp_path / "short.csv",
        RecorderOptions(laps=1, min_samples=5),
        reporter=messages.append,
        sleep=lambda _seconds: None,
    )
    result = recorder.run(source)
    assert result.laps_completed == 0
    assert result.rows_written == 0
    assert any("Discarding lap 1" in message for message in messages)
    assert read_csv(tmp_path / "short.csv") == []


def test_lap_timer_reset_starts_a_new_lap(tmp_path: Path) -> None:
    samples = [
        make_sample(packet_id=1, distance=0, elapsed_ms=10_000, completed_laps=0),
        make_sample(packet_id=2, distance=100, elapsed_ms=11_000, completed_laps=0),
        make_sample(packet_id=3, distance=110, elapsed_ms=0, completed_laps=0),
        make_sample(packet_id=4, distance=0, elapsed_ms=0, completed_laps=1),
    ]
    source = ListSource(samples)
    messages: list[str] = []
    recorder = Recorder(
        tmp_path / "timer-reset.csv",
        RecorderOptions(laps=1, min_samples=1),
        reporter=messages.append,
        sleep=lambda _seconds: None,
    )
    result = recorder.run(source)
    assert result.partial_laps == 1
    assert result.laps_completed == 1
    assert any("Lap timer reset" in message for message in messages)


def test_clamps_pedal_values(tmp_path: Path) -> None:
    source = ListSource(
        [
            make_sample(
                packet_id=1,
                distance=0,
                elapsed_ms=0,
                gas=1.5,
                brake=-0.2,
                completed_laps=0,
            ),
            make_sample(packet_id=2, distance=0, elapsed_ms=0, completed_laps=1),
        ]
    )
    recorder = Recorder(
        tmp_path / "clamped.csv",
        RecorderOptions(laps=1, min_samples=1),
        reporter=lambda _message: None,
        sleep=lambda _seconds: None,
    )
    recorder.run(source)
    rows = read_csv(tmp_path / "clamped.csv")
    assert rows[0]["throttle"] == "1.000"
    assert rows[0]["brake"] == "0.000"
