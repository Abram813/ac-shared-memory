"""Deterministic synthetic telemetry for `accapture record --demo`.

This is not a physics simulation.  It is a repeatable speed/brake profile with
three braking zones, used to exercise the recorder, CSV writer and feedback
plumbing on machines that do not have Assetto Corsa installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .mapping import Sample
from .packets import (
    AC_LIVE,
    AC_PRACTICE,
    GraphicsPacket,
    PhysicsPacket,
    StaticPacket,
)

LAP_DISTANCE_M = 2400.0
STEP_M = 2.0
BASE_SPEED_KMH = 240.0
BRAKING_ZONES = (
    (300.0, 400.0, 90.0),
    (700.0, 800.0, 110.0),
    (1150.0, 1250.0, 80.0),
    (1600.0, 1700.0, 100.0),
    (2050.0, 2150.0, 95.0),
)
ACCELERATION_DISTANCE_M = 150.0


def _speed_at(distance_m: float) -> float:
    for start, end, minimum in BRAKING_ZONES:
        if start <= distance_m <= end:
            fraction = (distance_m - start) / (end - start)
            return BASE_SPEED_KMH - (BASE_SPEED_KMH - minimum) * fraction
        if end < distance_m <= end + ACCELERATION_DISTANCE_M:
            fraction = (distance_m - end) / ACCELERATION_DISTANCE_M
            return minimum + (BASE_SPEED_KMH - minimum) * fraction
    return BASE_SPEED_KMH


def _brake_at(distance_m: float) -> float:
    for start, end, _minimum in BRAKING_ZONES:
        if start <= distance_m <= end:
            return 1.0
    return 0.0


def _throttle_at(distance_m: float) -> float:
    return 0.0 if _brake_at(distance_m) > 0 else 1.0


@dataclass(frozen=True)
class DemoLap:
    distance_m: list[float]
    elapsed_s: list[float]
    speed_kmh: list[float]
    throttle: list[float]
    brake: list[float]


def build_demo_lap() -> DemoLap:
    distances: list[float] = []
    elapsed: list[float] = []
    speeds: list[float] = []
    throttles: list[float] = []
    brakes: list[float] = []
    time_s = 0.0
    distance = 0.0
    while distance <= LAP_DISTANCE_M + 1e-9:
        speed = _speed_at(distance)
        distances.append(distance)
        elapsed.append(time_s)
        speeds.append(speed)
        throttles.append(_throttle_at(distance))
        brakes.append(_brake_at(distance))
        time_s += STEP_M / (speed / 3.6)
        distance += STEP_M
    return DemoLap(
        distance_m=distances,
        elapsed_s=elapsed,
        speed_kmh=speeds,
        throttle=throttles,
        brake=brakes,
    )


DEMO_LAP = build_demo_lap()
DEMO_STATIC = StaticPacket(
    sm_version="1.7",
    ac_version="1.16.4",
    number_of_sessions=1,
    num_cars=1,
    car_model="accapture demo car",
    track="accapture demo track",
    player_name="Demo",
    player_surname="Driver",
    player_nick="Demo Driver",
    sector_count=3,
    max_torque=500.0,
    max_power=700.0,
    max_rpm=8500,
)


class DemoSource:
    """A finite telemetry source that behaves like a live game."""

    def __init__(self, laps: int = 1, step_s: float = 0.02) -> None:
        if laps < 1:
            raise ValueError("laps must be at least 1")
        self.laps = laps
        self.step_s = step_s
        self.finished = False
        self._samples: list[Sample] = []
        self._index = 0
        self._build()

    def _build(self) -> None:
        packet_id = 0
        timestamp = 0.0
        for lap_index in range(self.laps):
            for distance, elapsed, speed, throttle, brake in zip(
                DEMO_LAP.distance_m,
                DEMO_LAP.elapsed_s,
                DEMO_LAP.speed_kmh,
                DEMO_LAP.throttle,
                DEMO_LAP.brake,
            ):
                packet_id += 1
                physics = PhysicsPacket(
                    packet_id=packet_id,
                    gas=throttle,
                    brake=brake,
                    fuel=40.0,
                    gear=4,
                    rpms=int(4000 + speed * 20),
                    steer_angle=0.0,
                    speed_kmh=speed,
                )
                graphics = GraphicsPacket(
                    packet_id=packet_id,
                    status=AC_LIVE,
                    session=AC_PRACTICE,
                    completed_laps=lap_index,
                    position=1,
                    current_time_ms=int(round(elapsed * 1000)),
                    last_time_ms=0,
                    best_time_ms=0,
                    session_time_left_s=600.0 - elapsed,
                    distance_traveled_m=distance,
                    is_in_pit=False,
                    current_sector_index=min(2, int(distance // 800)),
                    last_sector_time_ms=0,
                    number_of_laps=3,
                    normalized_car_position=distance / LAP_DISTANCE_M,
                )
                self._samples.append(
                    Sample(timestamp, physics, graphics, DEMO_STATIC)
                )
                timestamp += self.step_s
            # The game reports the completed-lap counter on the first update of
            # the next lap.  That is the signal the recorder uses to finalize
            # the lap that just ended.
            packet_id += 1
            graphics = GraphicsPacket(
                packet_id=packet_id,
                status=AC_LIVE,
                session=AC_PRACTICE,
                completed_laps=lap_index + 1,
                position=1,
                current_time_ms=0,
                last_time_ms=int(round(DEMO_LAP.elapsed_s[-1] * 1000)),
                best_time_ms=0,
                session_time_left_s=600.0,
                distance_traveled_m=0.0,
                is_in_pit=False,
                current_sector_index=0,
                last_sector_time_ms=0,
                number_of_laps=3,
                normalized_car_position=0.0,
            )
            physics = PhysicsPacket(
                packet_id=packet_id,
                gas=1.0,
                brake=0.0,
                fuel=40.0,
                gear=4,
                rpms=4000,
                steer_angle=0.0,
                speed_kmh=BASE_SPEED_KMH,
            )
            self._samples.append(Sample(timestamp, physics, graphics, DEMO_STATIC))
            timestamp += self.step_s

    def poll(self) -> Sample | None:
        if self._index >= len(self._samples):
            self.finished = True
            return None
        sample = self._samples[self._index]
        self._index += 1
        return sample

    def close(self) -> None:
        self.finished = True
