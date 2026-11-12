"""Read-only access to the Windows AC/ACC shared-memory mappings.

The game exposes three named file mappings:

``Local\\acpmf_physics``
    Pedals, speed, gear, RPMs, steering.
``Local\\acpmf_graphics``
    Session status, completed laps, current lap time, distance.
``Local\\acpmf_static``
    Car and track metadata.

This module uses ``OpenFileMappingW`` with ``FILE_MAP_READ`` only.  It never
creates or writes the game's mappings.  Importing the module is safe on macOS
and Linux; the Windows-only objects raise ``UnsupportedPlatform`` when used.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import Mapping

from .errors import SharedMemoryUnavailable, UnsupportedPlatform
from .packets import (
    GRAPHICS_FULL_PREFIX_SIZE,
    PHYSICS_PREFIX_SIZE,
    STATIC_MIN_SIZE,
    GraphicsPacket,
    PhysicsPacket,
    StaticPacket,
    decode_graphics,
    decode_physics,
    decode_static,
)

FILE_MAP_READ = 0x0004
FILE_MAP_WRITE = 0x0002
PAGE_READWRITE = 0x04

DEFAULT_MAPPING_NAMES: dict[str, str] = {
    "physics": r"Local\acpmf_physics",
    "graphics": r"Local\acpmf_graphics",
    "static": r"Local\acpmf_static",
}

DEFAULT_READ_SIZES: dict[str, int] = {
    "physics": PHYSICS_PREFIX_SIZE,
    "graphics": GRAPHICS_FULL_PREFIX_SIZE,
    "static": STATIC_MIN_SIZE,
}


def _kernel32():
    if sys.platform != "win32":
        raise UnsupportedPlatform(
            "AC/ACC shared memory is only available on Windows. "
            "Use `accapture record --demo` to exercise the recorder elsewhere."
        )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenFileMappingW.argtypes = [
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_wchar_p,
    ]
    kernel32.OpenFileMappingW.restype = ctypes.c_void_p
    kernel32.MapViewOfFile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_size_t,
    ]
    kernel32.MapViewOfFile.restype = ctypes.c_void_p
    kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
    kernel32.UnmapViewOfFile.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    return kernel32


class WindowsSharedMemoryPage:
    """A read-only view of one Windows named file mapping."""

    def __init__(self, name: str, size: int | None = None) -> None:
        if sys.platform != "win32":
            raise UnsupportedPlatform(
                "AC/ACC shared memory is only available on Windows."
            )
        self.name = name
        self.size = size
        self._kernel32 = _kernel32()
        self._handle: int | None = None
        self._view: int | None = None
        self._open()

    def _open(self) -> None:
        handle = self._kernel32.OpenFileMappingW(FILE_MAP_READ, False, self.name)
        if not handle:
            error = ctypes.get_last_error()
            raise SharedMemoryUnavailable(
                f"Could not open shared memory {self.name!r}: "
                f"{ctypes.FormatError(error)} (Windows error {error}). "
                "Start the game and enter a session first."
            )
        view = self._kernel32.MapViewOfFile(
            handle, FILE_MAP_READ, 0, 0, self.size or 0
        )
        if not view:
            error = ctypes.get_last_error()
            self._kernel32.CloseHandle(handle)
            raise SharedMemoryUnavailable(
                f"Could not map shared memory {self.name!r}: "
                f"{ctypes.FormatError(error)} (Windows error {error})."
            )
        self._handle = int(handle)
        self._view = int(view)

    @property
    def is_open(self) -> bool:
        return self._view is not None

    def read(self, size: int | None = None) -> bytes:
        if self._view is None:
            raise SharedMemoryUnavailable(f"Shared memory {self.name!r} is closed.")
        count = size if size is not None else (self.size or 4096)
        if count <= 0:
            raise ValueError("size must be positive")
        return ctypes.string_at(self._view, count)

    def close(self) -> None:
        if self._view is not None:
            self._kernel32.UnmapViewOfFile(self._view)
            self._view = None
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> "WindowsSharedMemoryPage":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


@dataclass(frozen=True)
class Sample:
    """One decoded game update."""

    timestamp_s: float
    physics: PhysicsPacket
    graphics: GraphicsPacket
    static: StaticPacket | None = None


class SharedMemorySource:
    """Read the three game pages and return one decoded sample per update."""

    def __init__(
        self,
        game: str = "acc",
        names: Mapping[str, str] | None = None,
        read_sizes: Mapping[str, int] | None = None,
    ) -> None:
        if sys.platform != "win32":
            raise UnsupportedPlatform(
                "AC/ACC shared memory is only available on Windows."
            )
        if game not in {"ac", "acc"}:
            raise ValueError("game must be 'ac' or 'acc'")
        self.game = game
        self.names = dict(DEFAULT_MAPPING_NAMES if names is None else names)
        self.read_sizes = dict(DEFAULT_READ_SIZES if read_sizes is None else read_sizes)
        self.finished = False
        self._last_physics_id: int | None = None
        self._last_graphics_id: int | None = None
        self._pages: dict[str, WindowsSharedMemoryPage] = {}
        try:
            for key in ("physics", "graphics", "static"):
                self._pages[key] = WindowsSharedMemoryPage(
                    self.names[key], size=self.read_sizes[key]
                )
            self.static = decode_static(self._pages["static"].read())
        except Exception:
            self.close()
            raise

    def poll(self) -> Sample | None:
        physics_data = self._pages["physics"].read(self.read_sizes["physics"])
        graphics_data = self._pages["graphics"].read(self.read_sizes["graphics"])
        physics = decode_physics(physics_data)
        graphics = decode_graphics(graphics_data)
        if (
            physics.packet_id == self._last_physics_id
            and graphics.packet_id == self._last_graphics_id
        ):
            return None
        self._last_physics_id = physics.packet_id
        self._last_graphics_id = graphics.packet_id
        import time

        return Sample(
            timestamp_s=time.monotonic(),
            physics=physics,
            graphics=graphics,
            static=self.static,
        )

    def close(self) -> None:
        for page in getattr(self, "_pages", {}).values():
            page.close()
        self._pages = {}
        self.finished = True

    def __enter__(self) -> "SharedMemorySource":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
