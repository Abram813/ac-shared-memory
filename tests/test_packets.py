from __future__ import annotations

import struct

import pytest

from accapture.errors import DecodeError
from accapture.packets import (
    AC_LIVE,
    AC_OFF,
    AC_PAUSE,
    AC_PRACTICE,
    AC_REPLAY,
    GRAPHICS_COMPLETED_LAPS,
    GRAPHICS_CURRENT_TIME_MS,
    GRAPHICS_DISTANCE_TRAVELED_M,
    GRAPHICS_MIN_SIZE,
    PHYSICS_PREFIX_SIZE,
    STATIC_MIN_SIZE,
    GraphicsPacket,
    PhysicsPacket,
    StaticPacket,
    decode_graphics,
    decode_physics,
    decode_static,
    encode_graphics,
    encode_physics,
    encode_static,
)


def graphics(**overrides) -> GraphicsPacket:
    values = dict(
        packet_id=7,
        status=AC_LIVE,
        session=AC_PRACTICE,
        completed_laps=3,
        position=4,
        current_time_ms=12_345,
        last_time_ms=98_765,
        best_time_ms=97_000,
        session_time_left_s=123.5,
        distance_traveled_m=456.25,
        is_in_pit=False,
        current_sector_index=2,
        last_sector_time_ms=31_000,
        number_of_laps=5,
        normalized_car_position=0.75,
    )
    values.update(overrides)
    return GraphicsPacket(**values)


def test_physics_prefix_is_32_bytes_and_roundtrips() -> None:
    packet = PhysicsPacket(
        packet_id=42,
        gas=0.75,
        brake=0.5,
        fuel=22.5,
        gear=5,
        rpms=7200,
        steer_angle=-0.125,
        speed_kmh=183.25,
    )
    data = encode_physics(packet)
    assert len(data) == PHYSICS_PREFIX_SIZE == 32
    assert decode_physics(data) == packet


def test_graphics_documented_offsets() -> None:
    packet = graphics()
    data = encode_graphics(packet)
    assert len(data) == 294
    assert struct.unpack_from("<i", data, GRAPHICS_COMPLETED_LAPS)[0] == 3
    assert struct.unpack_from("<i", data, GRAPHICS_CURRENT_TIME_MS)[0] == 12_345
    assert struct.unpack_from("<f", data, GRAPHICS_DISTANCE_TRAVELED_M)[0] == pytest.approx(
        456.25
    )
    # The four UTF-16 time strings occupy offsets 12..132.
    assert data[12:132] == b"\x00" * 120


def test_graphics_roundtrip_and_status_helpers() -> None:
    packet = graphics()
    decoded = decode_graphics(encode_graphics(packet))
    assert decoded == packet
    assert decoded.is_live
    assert decoded.status_name == "live"
    assert decoded.session_name == "practice"
    assert decoded.current_time_s == pytest.approx(12.345)


@pytest.mark.parametrize(
    ("status", "name", "attribute"),
    [
        (AC_OFF, "off", "is_off"),
        (AC_REPLAY, "replay", "is_replay"),
        (AC_LIVE, "live", "is_live"),
        (AC_PAUSE, "paused", "is_paused"),
    ],
)
def test_status_names(status: int, name: str, attribute: str) -> None:
    decoded = decode_graphics(encode_graphics(graphics(status=status)))
    assert decoded.status_name == name
    assert getattr(decoded, attribute)


def test_graphics_can_be_decoded_from_the_minimum_prefix() -> None:
    data = encode_graphics(graphics())[:GRAPHICS_MIN_SIZE]
    decoded = decode_graphics(data)
    assert decoded.completed_laps == 3
    assert decoded.distance_traveled_m == pytest.approx(456.25)
    assert decoded.normalized_car_position == 0.0


def test_short_packets_are_rejected() -> None:
    with pytest.raises(DecodeError, match="physics packet"):
        decode_physics(b"\x00" * 31)
    with pytest.raises(DecodeError, match="graphics packet"):
        decode_graphics(b"\x00" * (GRAPHICS_MIN_SIZE - 1))
    with pytest.raises(DecodeError, match="static packet"):
        decode_static(b"\x00" * (STATIC_MIN_SIZE - 1))


def test_static_packet_roundtrip() -> None:
    packet = StaticPacket(
        sm_version="1.7",
        ac_version="1.16.4",
        number_of_sessions=2,
        num_cars=24,
        car_model="ferrari_488_gt3",
        track="monza",
        player_name="Ada",
        player_surname="Lovelace",
        player_nick="ada",
        sector_count=3,
        max_torque=500.0,
        max_power=700.0,
        max_rpm=8500,
    )
    data = encode_static(packet)
    assert len(data) == STATIC_MIN_SIZE
    assert decode_static(data) == packet
