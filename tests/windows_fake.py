from __future__ import annotations

import ctypes
import os
import sys

from accapture.mapping import FILE_MAP_WRITE, PAGE_READWRITE


class FakeMapping:
    """Create a writable Windows file mapping for integration tests.

    This is the only place in the test suite that writes a shared-memory page;
    the production code only ever opens pages with FILE_MAP_READ.
    """

    def __init__(self, name: str, size: int) -> None:
        if sys.platform != "win32":
            raise RuntimeError("FakeMapping is Windows-only")
        self.name = name
        self.size = size
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateFileMappingW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_wchar_p,
        ]
        self.kernel32.CreateFileMappingW.restype = ctypes.c_void_p
        self.kernel32.MapViewOfFile.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_size_t,
        ]
        self.kernel32.MapViewOfFile.restype = ctypes.c_void_p
        self.kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        self.kernel32.UnmapViewOfFile.restype = ctypes.c_int
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel32.CloseHandle.restype = ctypes.c_int

        handle = self.kernel32.CreateFileMappingW(
            ctypes.c_void_p(-1),
            None,
            PAGE_READWRITE,
            0,
            size,
            name,
        )
        if not handle:
            error = ctypes.get_last_error()
            raise OSError(error, f"CreateFileMappingW failed: {ctypes.FormatError(error)}")
        self.handle = int(handle)
        view = self.kernel32.MapViewOfFile(handle, FILE_MAP_WRITE, 0, 0, size)
        if not view:
            error = ctypes.get_last_error()
            self.kernel32.CloseHandle(handle)
            raise OSError(error, f"MapViewOfFile failed: {ctypes.FormatError(error)}")
        self.view = int(view)

    def write(self, data: bytes) -> None:
        if len(data) > self.size:
            raise ValueError(f"{len(data)} bytes do not fit in {self.size}")
        ctypes.memmove(self.view, data, len(data))

    def close(self) -> None:
        if getattr(self, "view", None):
            self.kernel32.UnmapViewOfFile(self.view)
            self.view = None
        if getattr(self, "handle", None):
            self.kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self) -> "FakeMapping":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def unique_name(part: str) -> str:
    return rf"Local\accapture_test_{os.getpid()}_{part}"
