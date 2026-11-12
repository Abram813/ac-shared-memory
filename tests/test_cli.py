from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_help_lists_commands() -> None:
    completed = run_cli("--help")
    assert completed.returncode == 0
    for command in ("record", "feedback", "probe", "version"):
        assert command in completed.stdout


def test_no_arguments_prints_help() -> None:
    completed = run_cli()
    assert completed.returncode == 0
    assert "record" in completed.stdout


def test_version() -> None:
    completed = run_cli("version")
    assert completed.returncode == 0
    assert "accapture 0.1.0" in completed.stdout


def test_record_demo_creates_racecoach_csv(tmp_path: Path) -> None:
    out = tmp_path / "demo laps with spaces" / "session.csv"
    completed = run_cli(
        "record",
        "--demo",
        "--out",
        str(out),
        "--laps",
        "1",
    )
    assert completed.returncode == 0, completed.stderr
    assert "Recorded 1 completed lap(s)" in completed.stdout
    rows = read_rows(out)
    assert rows
    assert list(rows[0]) == [
        "lap_number",
        "distance_m",
        "elapsed_s",
        "speed_kmh",
        "throttle",
        "brake",
    ]
    assert {row["lap_number"] for row in rows} == {"1"}


def test_record_demo_two_laps(tmp_path: Path) -> None:
    out = tmp_path / "two laps.csv"
    completed = run_cli(
        "record",
        "--demo",
        "--out",
        str(out),
        "--laps",
        "2",
    )
    assert completed.returncode == 0, completed.stderr
    rows = read_rows(out)
    assert {row["lap_number"] for row in rows} == {"1", "2"}


def test_feedback_uses_stub_racecoach(tmp_path: Path) -> None:
    session = tmp_path / "session lap.csv"
    completed = run_cli("record", "--demo", "--out", str(session), "--laps", "1")
    assert completed.returncode == 0, completed.stderr
    reference = session
    stub = tmp_path / "stub racecoach.py"
    stub.write_text(
        "import sys\nprint('STUB ' + ' '.join(sys.argv[1:]))\n", encoding="utf-8"
    )
    feedback = run_cli(
        "feedback",
        "--reference",
        str(reference),
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


def test_feedback_missing_session_returns_error(tmp_path: Path) -> None:
    reference = tmp_path / "reference.csv"
    reference.write_text("reference\n", encoding="utf-8")
    completed = run_cli(
        "feedback",
        "--reference",
        str(reference),
        "--session",
        str(tmp_path / "missing.csv"),
    )
    assert completed.returncode == 2
    assert "not found" in completed.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="this asserts the non-Windows error")
def test_live_record_is_windows_only() -> None:
    completed = run_cli("record", "--out", "unused.csv")
    assert completed.returncode == 2
    assert "Windows-only" in completed.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="this asserts the non-Windows error")
def test_probe_is_windows_only() -> None:
    completed = run_cli("probe")
    assert completed.returncode == 2
    assert "Windows-only" in completed.stderr
