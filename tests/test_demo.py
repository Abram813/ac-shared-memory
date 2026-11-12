from __future__ import annotations

import csv
from pathlib import Path

import pytest

from accapture.demo import (
    BRAKING_ZONES,
    DEMO_LAP,
    LAP_DISTANCE_M,
    DemoSource,
    build_demo_lap,
)
from accapture.recorder import Recorder, RecorderOptions


def test_demo_lap_is_deterministic_and_has_five_braking_zones() -> None:
    first = build_demo_lap()
    second = build_demo_lap()
    assert first == second
    assert first.distance_m[0] == 0.0
    assert first.distance_m[-1] >= LAP_DISTANCE_M
    assert first.elapsed_s[0] == 0.0
    assert all(b > a for a, b in zip(first.elapsed_s, first.elapsed_s[1:]))
    assert all(speed > 0 for speed in first.speed_kmh)

    onsets = 0
    previous = 0.0
    for brake in first.brake:
        if brake >= 0.05 and previous < 0.05:
            onsets += 1
        previous = brake
    assert onsets == len(BRAKING_ZONES) == 5


def test_demo_source_emits_laps_and_finishes() -> None:
    source = DemoSource(laps=2)
    samples = []
    while True:
        sample = source.poll()
        if sample is None:
            break
        samples.append(sample)
    assert source.finished
    assert samples
    assert samples[0].graphics.completed_laps == 0
    assert samples[-1].graphics.completed_laps == 2
    assert samples[-1].graphics.distance_traveled_m == 0.0
    assert {sample.graphics.completed_laps for sample in samples} == {0, 1, 2}


def test_demo_source_rejects_zero_laps() -> None:
    with pytest.raises(ValueError):
        DemoSource(laps=0)


def test_recorder_writes_demo_lap(tmp_path: Path) -> None:
    source = DemoSource(laps=1)
    recorder = Recorder(
        tmp_path / "demo.csv",
        RecorderOptions(laps=1, min_samples=1),
        reporter=lambda _message: None,
        sleep=lambda _seconds: None,
    )
    result = recorder.run(source)
    assert result.laps_completed == 1
    assert result.partial_laps == 0
    assert result.rows_written > 100
    with (tmp_path / "demo.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert {row["lap_number"] for row in rows} == {"1"}
    assert rows[0]["distance_m"] == "0.000"
