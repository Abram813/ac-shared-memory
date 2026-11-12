#!/usr/bin/env python3
"""End-to-end smoke test for accapture.

Runs the real CLI, writes CSVs into a directory whose name contains spaces,
checks the CSV contract, and verifies the RaceCoach subprocess boundary with a
stub.  Live shared-memory access is not available here; that path is covered by
the Windows-only fake-mapping tests and by the manual running-game procedure in
README.md.
"""

from __future__ import annotations

import csv
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "accapture", *args],
        cwd=str(cwd or ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def uv_version() -> str:
    try:
        return subprocess.check_output(["uv", "--version"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "uv not found on PATH"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="accapture smoke ") as temp:
        work = Path(temp)
        session = work / "demo laps with spaces" / "session.csv"
        completed = run_cli(
            "record", "--demo", "--out", str(session), "--laps", "1"
        )
        assert completed.returncode == 0, completed.stderr
        assert "Recorded 1 completed lap(s)" in completed.stdout
        rows = read_rows(session)
        assert rows, "demo recording produced no rows"
        assert list(rows[0]) == [
            "lap_number",
            "distance_m",
            "elapsed_s",
            "speed_kmh",
            "throttle",
            "brake",
        ]
        assert {row["lap_number"] for row in rows} == {"1"}
        assert float(rows[-1]["distance_m"]) > 2300

        two_laps = work / "two laps.csv"
        completed = run_cli(
            "record", "--demo", "--out", str(two_laps), "--laps", "2"
        )
        assert completed.returncode == 0, completed.stderr
        assert {row["lap_number"] for row in read_rows(two_laps)} == {"1", "2"}

        stub = work / "stub racecoach.py"
        stub.write_text(
            "import sys\nprint('STUB ' + ' '.join(sys.argv[1:]))\n",
            encoding="utf-8",
        )
        feedback = run_cli(
            "feedback",
            "--reference",
            str(session),
            "--session",
            str(session),
            "--racecoach",
            str(stub),
            "--json",
        )
        assert feedback.returncode == 0, feedback.stderr
        assert "STUB analyze" in feedback.stdout
        assert "--reference" in feedback.stdout
        assert "--practice" in feedback.stdout
        assert "--json" in feedback.stdout

        if sys.platform != "win32":
            probe = run_cli("probe")
            assert probe.returncode == 2, probe.stderr
            assert "Windows-only" in probe.stderr
            live = run_cli("record", "--out", str(work / "unused.csv"))
            assert live.returncode == 2, live.stderr
            assert "Windows-only" in live.stderr
        else:
            # No game is expected on a CI runner.  The command should fail
            # cleanly with a helpful mapping error rather than hang.
            probe = run_cli("probe", "--timeout", "0.5")
            assert probe.returncode in (2, 3), probe.stderr

        print("Environment")
        print(f"  OS:      {platform.platform()}")
        print(f"  Machine: {platform.machine()}")
        print(f"  Python:  {platform.python_version()}")
        print(f"  uv:      {uv_version()}")
        print(
            "SMOKE PASS: demo CSV contract, multi-lap recording, feedback "
            "subprocess, and platform error paths."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
