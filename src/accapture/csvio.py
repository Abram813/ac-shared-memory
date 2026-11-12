"""CSV output compatible with RaceCoach."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

CSV_HEADER = [
    "lap_number",
    "distance_m",
    "elapsed_s",
    "speed_kmh",
    "throttle",
    "brake",
]


@dataclass(frozen=True)
class TelemetryRow:
    lap_number: int
    distance_m: float
    elapsed_s: float
    speed_kmh: float
    throttle: float
    brake: float

    def as_csv_row(self) -> list[str]:
        return [
            str(int(self.lap_number)),
            f"{self.distance_m:.3f}",
            f"{self.elapsed_s:.3f}",
            f"{self.speed_kmh:.3f}",
            f"{self.throttle:.3f}",
            f"{self.brake:.3f}",
        ]


class CsvWriter:
    """Write a RaceCoach CSV, flushing after every lap."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("w", encoding="utf-8", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(CSV_HEADER)
        self._file.flush()
        self.rows_written = 0

    def write_lap(self, lap_number: int, rows: list[TelemetryRow]) -> int:
        written = 0
        for row in rows:
            if row.lap_number != lap_number:
                raise ValueError(
                    f"row lap_number {row.lap_number} does not match lap {lap_number}"
                )
            self._writer.writerow(row.as_csv_row())
            written += 1
        self._file.flush()
        self.rows_written += written
        return written

    def close(self) -> None:
        if not self._file.closed:
            self._file.flush()
            self._file.close()

    def __enter__(self) -> "CsvWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
