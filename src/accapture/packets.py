"""Decode the documented AC/ACC shared-memory packet prefixes.

The game writes fixed-size ``ctypes`` structures into three named file
mappings.  accapture only needs a small prefix of each structure, so it reads
and decodes the fields it uses rather than mirroring every game version's full
struct.

Offsets below come from the official Assetto Corsa shared-memory reference and
the ACC shared-memory documentation.  ``wchar_t`` is two bytes on Windows, so
the character arrays between ``session`` and ``completedLaps`` occupy 120
bytes.  The decoder deliberately skips those arrays by offset instead of using
``ctypes.c_wchar``, whose size is four bytes on macOS and Linux.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .errors import DecodeError

# AC_STATUS values, shared by AC and ACC.
AC_OFF = 0
AC_REPLAY = 1
AC_LIVE = 2
AC_PAUSE = 3

STATUS_NAMES = {
    AC_OFF: "off",
    AC_REPLAY: "replay",
    AC_LIVE: "live",
    AC_PAUSE: "paused",
}

AC_UNKNOWN = -1
AC_PRACTICE = 0
AC_QUALIFY = 1
AC_RACE = 2
AC_HOTLAP = 3
AC_TIME_ATTACK = 4
AC_DRIFT = 5
AC_DRAG = 6

SESSION_NAMES = {
    AC_UNKNOWN: "unknown",
    AC_PRACTICE: "practice",
    AC_QUALIFY: "qualify",
    AC_RACE: "race",
    AC_HOTLAP: "hotlap",
    AC_TIME_ATTACK: "time_attack",
    AC_DRIFT: "drift",
    AC_DRAG: "drag",
}

# The physics prefix is exactly 32 bytes:
#   int packetId, float gas, float brake, float fuel, int gear, int rpms,
#   float steerAngle, float speedKmh
PHYSICS_PREFIX_FORMAT = "<ifffiiff"
PHYSICS_PREFIX_SIZE = struct.calcsize(PHYSICS_PREFIX_FORMAT)

# Graphics offsets.  The four wchar_t[15] time strings sit between offset 12
# and 132; they are not needed for capture.
GRAPHICS_PACKET_ID = 0
GRAPHICS_STATUS = 4
GRAPHICS_SESSION = 8
GRAPHICS_COMPLETED_LAPS = 132
GRAPHICS_POSITION = 136
GRAPHICS_CURRENT_TIME_MS = 140
GRAPHICS_LAST_TIME_MS = 144
GRAPHICS_BEST_TIME_MS = 148
GRAPHICS_SESSION_TIME_LEFT_S = 152
GRAPHICS_DISTANCE_TRAVELED_M = 156
GRAPHICS_IS_IN_PIT = 160
GRAPHICS_CURRENT_SECTOR_INDEX = 164
GRAPHICS_LAST_SECTOR_TIME_MS = 168
GRAPHICS_NUMBER_OF_LAPS = 172
GRAPHICS_NORMALIZED_CAR_POSITION = 246
GRAPHICS_MIN_SIZE = 176
GRAPHICS_FULL_PREFIX_SIZE = 250

# Static-page offsets, only used for display/metadata.
STATIC_SM_VERSION = 0
STATIC_AC_VERSION = 30
STATIC_NUMBER_OF_SESSIONS = 60
STATIC_NUM_CARS = 64
STATIC_CAR_MODEL = 68
STATIC_TRACK = 134
STATIC_PLAYER_NAME = 200
STATIC_PLAYER_SURNAME = 266
STATIC_PLAYER_NICK = 332
STATIC_SECTOR_COUNT = 398
STATIC_MAX_TORQUE = 402
STATIC_MAX_POWER = 406
STATIC_MAX_RPM = 410
STATIC_MIN_SIZE = 414


@dataclass(frozen=True)
class PhysicsPacket:
    packet_id: int
    gas: float
    brake: float
    fuel: float
    gear: int
    rpms: int
    steer_angle: float
    speed_kmh: float

    @property
    def throttle(self) -> float:
        return self.gas

    def to_dict(self) -> dict:
        return {
            "packet_id": self.packet_id,
            "gas": self.gas,
            "brake": self.brake,
            "fuel": self.fuel,
            "gear": self.gear,
            "rpms": self.rpms,
            "steer_angle": self.steer_angle,
            "speed_kmh": self.speed_kmh,
        }


@dataclass(frozen=True)
class GraphicsPacket:
    packet_id: int
    status: int
    session: int
    completed_laps: int
    position: int
    current_time_ms: int
    last_time_ms: int
    best_time_ms: int
    session_time_left_s: float
    distance_traveled_m: float
    is_in_pit: bool
    current_sector_index: int
    last_sector_time_ms: int
    number_of_laps: int
    normalized_car_position: float

    @property
    def status_name(self) -> str:
        return STATUS_NAMES.get(self.status, f"unknown({self.status})")

    @property
    def session_name(self) -> str:
        return SESSION_NAMES.get(self.session, f"unknown({self.session})")

    @property
    def is_live(self) -> bool:
        return self.status == AC_LIVE

    @property
    def is_paused(self) -> bool:
        return self.status == AC_PAUSE

    @property
    def is_off(self) -> bool:
        return self.status == AC_OFF

    @property
    def is_replay(self) -> bool:
        return self.status == AC_REPLAY

    @property
    def current_time_s(self) -> float:
        return self.current_time_ms / 1000.0

    def to_dict(self) -> dict:
        return {
            "packet_id": self.packet_id,
            "status": self.status,
            "status_name": self.status_name,
            "session": self.session,
            "session_name": self.session_name,
            "completed_laps": self.completed_laps,
            "position": self.position,
            "current_time_ms": self.current_time_ms,
            "last_time_ms": self.last_time_ms,
            "best_time_ms": self.best_time_ms,
            "session_time_left_s": self.session_time_left_s,
            "distance_traveled_m": self.distance_traveled_m,
            "is_in_pit": self.is_in_pit,
            "current_sector_index": self.current_sector_index,
            "last_sector_time_ms": self.last_sector_time_ms,
            "number_of_laps": self.number_of_laps,
            "normalized_car_position": self.normalized_car_position,
        }


@dataclass(frozen=True)
class StaticPacket:
    sm_version: str
    ac_version: str
    number_of_sessions: int
    num_cars: int
    car_model: str
    track: str
    player_name: str
    player_surname: str
    player_nick: str
    sector_count: int
    max_torque: float
    max_power: float
    max_rpm: int

    def to_dict(self) -> dict:
        return {
            "sm_version": self.sm_version,
            "ac_version": self.ac_version,
            "number_of_sessions": self.number_of_sessions,
            "num_cars": self.num_cars,
            "car_model": self.car_model,
            "track": self.track,
            "player_name": self.player_name,
            "player_surname": self.player_surname,
            "player_nick": self.player_nick,
            "sector_count": self.sector_count,
            "max_torque": self.max_torque,
            "max_power": self.max_power,
            "max_rpm": self.max_rpm,
        }


def _require(data: bytes, size: int, label: str) -> None:
    if len(data) < size:
        raise DecodeError(
            f"{label} packet is {len(data)} bytes; at least {size} are required."
        )


def _unpack(fmt: str, data: bytes, offset: int, label: str):
    size = struct.calcsize(fmt)
    if len(data) < offset + size:
        raise DecodeError(
            f"{label} packet is too short for {fmt} at offset {offset} "
            f"({len(data)} bytes)."
        )
    return struct.unpack_from(fmt, data, offset)


def _decode_wchar(data: bytes, offset: int, count: int) -> str:
    raw = data[offset : offset + count * 2]
    if len(raw) < count * 2:
        return ""
    return raw.decode("utf-16-le", errors="replace").split("\x00", 1)[0].strip()


def _encode_wchar(text: str, count: int) -> bytes:
    raw = text.encode("utf-16-le")
    return raw[: max(0, count * 2 - 2)].ljust(count * 2, b"\x00")


def decode_physics(data: bytes) -> PhysicsPacket:
    _require(data, PHYSICS_PREFIX_SIZE, "physics")
    packet_id, gas, brake, fuel, gear, rpms, steer, speed = struct.unpack_from(
        PHYSICS_PREFIX_FORMAT, data, 0
    )
    return PhysicsPacket(
        packet_id=int(packet_id),
        gas=float(gas),
        brake=float(brake),
        fuel=float(fuel),
        gear=int(gear),
        rpms=int(rpms),
        steer_angle=float(steer),
        speed_kmh=float(speed),
    )


def decode_graphics(data: bytes) -> GraphicsPacket:
    _require(data, GRAPHICS_MIN_SIZE, "graphics")
    packet_id, status, session = _unpack("<iii", data, 0, "graphics")
    completed_laps = _unpack("<i", data, GRAPHICS_COMPLETED_LAPS, "graphics")[0]
    position = _unpack("<i", data, GRAPHICS_POSITION, "graphics")[0]
    current_time = _unpack("<i", data, GRAPHICS_CURRENT_TIME_MS, "graphics")[0]
    last_time = _unpack("<i", data, GRAPHICS_LAST_TIME_MS, "graphics")[0]
    best_time = _unpack("<i", data, GRAPHICS_BEST_TIME_MS, "graphics")[0]
    session_time_left = _unpack("<f", data, GRAPHICS_SESSION_TIME_LEFT_S, "graphics")[0]
    distance = _unpack("<f", data, GRAPHICS_DISTANCE_TRAVELED_M, "graphics")[0]
    is_in_pit = bool(_unpack("<i", data, GRAPHICS_IS_IN_PIT, "graphics")[0])
    sector_index = _unpack("<i", data, GRAPHICS_CURRENT_SECTOR_INDEX, "graphics")[0]
    last_sector_time = _unpack("<i", data, GRAPHICS_LAST_SECTOR_TIME_MS, "graphics")[0]
    number_of_laps = _unpack("<i", data, GRAPHICS_NUMBER_OF_LAPS, "graphics")[0]
    normalized = 0.0
    if len(data) >= GRAPHICS_FULL_PREFIX_SIZE:
        normalized = _unpack(
            "<f", data, GRAPHICS_NORMALIZED_CAR_POSITION, "graphics"
        )[0]
    return GraphicsPacket(
        packet_id=int(packet_id),
        status=int(status),
        session=int(session),
        completed_laps=int(completed_laps),
        position=int(position),
        current_time_ms=int(current_time),
        last_time_ms=int(last_time),
        best_time_ms=int(best_time),
        session_time_left_s=float(session_time_left),
        distance_traveled_m=float(distance),
        is_in_pit=is_in_pit,
        current_sector_index=int(sector_index),
        last_sector_time_ms=int(last_sector_time),
        number_of_laps=int(number_of_laps),
        normalized_car_position=float(normalized),
    )


def decode_static(data: bytes) -> StaticPacket:
    _require(data, STATIC_MIN_SIZE, "static")
    return StaticPacket(
        sm_version=_decode_wchar(data, STATIC_SM_VERSION, 15),
        ac_version=_decode_wchar(data, STATIC_AC_VERSION, 15),
        number_of_sessions=_unpack(
            "<i", data, STATIC_NUMBER_OF_SESSIONS, "static"
        )[0],
        num_cars=_unpack("<i", data, STATIC_NUM_CARS, "static")[0],
        car_model=_decode_wchar(data, STATIC_CAR_MODEL, 33),
        track=_decode_wchar(data, STATIC_TRACK, 33),
        player_name=_decode_wchar(data, STATIC_PLAYER_NAME, 33),
        player_surname=_decode_wchar(data, STATIC_PLAYER_SURNAME, 33),
        player_nick=_decode_wchar(data, STATIC_PLAYER_NICK, 33),
        sector_count=_unpack("<i", data, STATIC_SECTOR_COUNT, "static")[0],
        max_torque=_unpack("<f", data, STATIC_MAX_TORQUE, "static")[0],
        max_power=_unpack("<f", data, STATIC_MAX_POWER, "static")[0],
        max_rpm=_unpack("<i", data, STATIC_MAX_RPM, "static")[0],
    )


def encode_physics(packet: PhysicsPacket) -> bytes:
    """Encode the 32-byte prefix used by tests and the fake Windows game."""

    return struct.pack(
        PHYSICS_PREFIX_FORMAT,
        packet.packet_id,
        packet.gas,
        packet.brake,
        packet.fuel,
        packet.gear,
        packet.rpms,
        packet.steer_angle,
        packet.speed_kmh,
    )


def encode_graphics(packet: GraphicsPacket) -> bytes:
    """Encode a graphics page large enough for every decoded field."""

    data = bytearray(294)
    struct.pack_into("<iii", data, 0, packet.packet_id, packet.status, packet.session)
    struct.pack_into("<i", data, GRAPHICS_COMPLETED_LAPS, packet.completed_laps)
    struct.pack_into("<i", data, GRAPHICS_POSITION, packet.position)
    struct.pack_into("<i", data, GRAPHICS_CURRENT_TIME_MS, packet.current_time_ms)
    struct.pack_into("<i", data, GRAPHICS_LAST_TIME_MS, packet.last_time_ms)
    struct.pack_into("<i", data, GRAPHICS_BEST_TIME_MS, packet.best_time_ms)
    struct.pack_into(
        "<f", data, GRAPHICS_SESSION_TIME_LEFT_S, packet.session_time_left_s
    )
    struct.pack_into("<f", data, GRAPHICS_DISTANCE_TRAVELED_M, packet.distance_traveled_m)
    struct.pack_into("<i", data, GRAPHICS_IS_IN_PIT, int(packet.is_in_pit))
    struct.pack_into(
        "<i", data, GRAPHICS_CURRENT_SECTOR_INDEX, packet.current_sector_index
    )
    struct.pack_into("<i", data, GRAPHICS_LAST_SECTOR_TIME_MS, packet.last_sector_time_ms)
    struct.pack_into("<i", data, GRAPHICS_NUMBER_OF_LAPS, packet.number_of_laps)
    struct.pack_into(
        "<f", data, GRAPHICS_NORMALIZED_CAR_POSITION, packet.normalized_car_position
    )
    return bytes(data)


def encode_static(packet: StaticPacket) -> bytes:
    """Encode a static page for tests and the fake Windows game."""

    data = bytearray(STATIC_MIN_SIZE)
    data[STATIC_SM_VERSION : STATIC_SM_VERSION + 30] = _encode_wchar(packet.sm_version, 15)
    data[STATIC_AC_VERSION : STATIC_AC_VERSION + 30] = _encode_wchar(packet.ac_version, 15)
    struct.pack_into("<i", data, STATIC_NUMBER_OF_SESSIONS, packet.number_of_sessions)
    struct.pack_into("<i", data, STATIC_NUM_CARS, packet.num_cars)
    data[STATIC_CAR_MODEL : STATIC_CAR_MODEL + 66] = _encode_wchar(packet.car_model, 33)
    data[STATIC_TRACK : STATIC_TRACK + 66] = _encode_wchar(packet.track, 33)
    data[STATIC_PLAYER_NAME : STATIC_PLAYER_NAME + 66] = _encode_wchar(packet.player_name, 33)
    data[STATIC_PLAYER_SURNAME : STATIC_PLAYER_SURNAME + 66] = _encode_wchar(
        packet.player_surname, 33
    )
    data[STATIC_PLAYER_NICK : STATIC_PLAYER_NICK + 66] = _encode_wchar(packet.player_nick, 33)
    struct.pack_into("<i", data, STATIC_SECTOR_COUNT, packet.sector_count)
    struct.pack_into("<f", data, STATIC_MAX_TORQUE, packet.max_torque)
    struct.pack_into("<f", data, STATIC_MAX_POWER, packet.max_power)
    struct.pack_into("<i", data, STATIC_MAX_RPM, packet.max_rpm)
    return bytes(data)
