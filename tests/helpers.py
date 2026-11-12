from __future__ import annotations

from accapture.demo import DEMO_STATIC
from accapture.mapping import Sample
from accapture.packets import (
    AC_LIVE,
    AC_PRACTICE,
    GraphicsPacket,
    PhysicsPacket,
)


def make_sample(
    *,
    packet_id: int = 1,
    distance: float = 0.0,
    elapsed_ms: int = 0,
    speed: float = 100.0,
    gas: float = 1.0,
    brake: float = 0.0,
    completed_laps: int = 0,
    status: int = AC_LIVE,
    session: int = AC_PRACTICE,
    timestamp: float = 0.0,
    session_time_left: float = 600.0,
    is_in_pit: bool = False,
    number_of_laps: int = 3,
) -> Sample:
    physics = PhysicsPacket(
        packet_id=packet_id,
        gas=gas,
        brake=brake,
        fuel=40.0,
        gear=4,
        rpms=6000,
        steer_angle=0.0,
        speed_kmh=speed,
    )
    graphics = GraphicsPacket(
        packet_id=packet_id,
        status=status,
        session=session,
        completed_laps=completed_laps,
        position=1,
        current_time_ms=elapsed_ms,
        last_time_ms=0,
        best_time_ms=0,
        session_time_left_s=session_time_left,
        distance_traveled_m=distance,
        is_in_pit=is_in_pit,
        current_sector_index=0,
        last_sector_time_ms=0,
        number_of_laps=number_of_laps,
        normalized_car_position=0.0,
    )
    return Sample(timestamp, physics, graphics, DEMO_STATIC)


class ListSource:
    def __init__(self, samples: list[Sample]) -> None:
        self.samples = list(samples)
        self.index = 0
        self.finished = False
        self.closed = False

    def poll(self) -> Sample | None:
        if self.index >= len(self.samples):
            self.finished = True
            return None
        sample = self.samples[self.index]
        self.index += 1
        return sample

    def close(self) -> None:
        self.closed = True


class RaisingSource:
    def __init__(self, samples: list[Sample], exception: Exception) -> None:
        self.samples = list(samples)
        self.exception = exception
        self.index = 0
        self.finished = False
        self.closed = False

    def poll(self) -> Sample | None:
        if self.index < len(self.samples):
            sample = self.samples[self.index]
            self.index += 1
            return sample
        raise self.exception

    def close(self) -> None:
        self.closed = True
