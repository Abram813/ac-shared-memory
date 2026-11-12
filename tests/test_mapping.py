from __future__ import annotations

import sys
from pathlib import Path

import pytest

from accapture.errors import SharedMemoryUnavailable, UnsupportedPlatform
from accapture.mapping import (
    DEFAULT_READ_SIZES,
    SharedMemorySource,
    WindowsSharedMemoryPage,
)
from accapture.packets import encode_graphics, encode_physics, encode_static

from .helpers import make_sample

pytestmark = pytest.mark.windows


@pytest.mark.skipif(sys.platform == "win32", reason="this asserts the non-Windows error")
def test_shared_memory_is_windows_only() -> None:
    with pytest.raises(UnsupportedPlatform):
        WindowsSharedMemoryPage(r"Local\accapture_missing")
    with pytest.raises(UnsupportedPlatform):
        SharedMemorySource()


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows mappings")
def test_reads_a_fake_mapping() -> None:
    from .windows_fake import FakeMapping, unique_name

    name = unique_name("read")
    payload = b"hello shared memory"
    with FakeMapping(name, 64) as mapping:
        mapping.write(payload)
        with WindowsSharedMemoryPage(name, size=len(payload)) as page:
            assert page.read(len(payload)) == payload


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows mappings")
def test_missing_mapping_is_reported() -> None:
    from .windows_fake import unique_name

    with pytest.raises(SharedMemoryUnavailable, match="Could not open"):
        WindowsSharedMemoryPage(unique_name("missing"))


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows mappings")
def test_source_decodes_all_three_pages() -> None:
    from .windows_fake import FakeMapping, unique_name

    names = {
        "physics": unique_name("physics"),
        "graphics": unique_name("graphics"),
        "static": unique_name("static"),
    }
    sample = make_sample(packet_id=11, distance=321.5, elapsed_ms=12_000, speed=155.0)
    with FakeMapping(names["physics"], 32) as physics, FakeMapping(
        names["graphics"], 294
    ) as graphics, FakeMapping(names["static"], 414) as static:
        physics.write(encode_physics(sample.physics))
        graphics.write(encode_graphics(sample.graphics))
        static.write(encode_static(sample.static))
        with SharedMemorySource(
            names=names, read_sizes=DEFAULT_READ_SIZES
        ) as source:
            decoded = source.poll()
            assert decoded is not None
            assert decoded.physics.speed_kmh == pytest.approx(155.0)
            assert decoded.graphics.distance_traveled_m == pytest.approx(321.5)
            assert decoded.static.car_model == "accapture demo car"
            # The same packet ids are treated as a duplicate update.
            assert source.poll() is None


@pytest.mark.skipif(sys.platform != "win32", reason="requires Windows mappings")
def test_fake_game_feeds_the_recorder(tmp_path: Path) -> None:
    from .windows_fake import FakeMapping, unique_name

    names = {
        "physics": unique_name("rec_physics"),
        "graphics": unique_name("rec_graphics"),
        "static": unique_name("rec_static"),
    }
    samples = [
        make_sample(packet_id=1, distance=0, elapsed_ms=0, completed_laps=0),
        make_sample(packet_id=2, distance=10, elapsed_ms=500, completed_laps=0),
        make_sample(packet_id=3, distance=20, elapsed_ms=1000, completed_laps=0),
        make_sample(packet_id=4, distance=0, elapsed_ms=0, completed_laps=1),
    ]

    class FakeGameSource:
        def __init__(self, reader: SharedMemorySource, writes) -> None:
            self.reader = reader
            self.writes = list(writes)
            self.index = 0
            self.finished = False

        def poll(self):
            if self.index >= len(self.writes):
                self.finished = True
                return None
            sample = self.writes[self.index]
            self.index += 1
            self.writes_pages(sample)
            return self.reader.poll()

        def writes_pages(self, sample) -> None:
            physics_page.write(encode_physics(sample.physics))
            graphics_page.write(encode_graphics(sample.graphics))
            static_page.write(encode_static(sample.static))

        def close(self) -> None:
            self.reader.close()

    with FakeMapping(names["physics"], 32) as physics_page, FakeMapping(
        names["graphics"], 294
    ) as graphics_page, FakeMapping(names["static"], 414) as static_page:
        reader = SharedMemorySource(names=names, read_sizes=DEFAULT_READ_SIZES)
        source = FakeGameSource(reader, samples)
        from accapture.recorder import Recorder, RecorderOptions

        result = Recorder(
            tmp_path / "fake game.csv",
            RecorderOptions(laps=1, min_samples=1),
            reporter=lambda _message: None,
            sleep=lambda _seconds: None,
        ).run(source)
        assert result.laps_completed == 1
        assert result.rows_written == 3
