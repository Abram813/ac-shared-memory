from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

from accapture.feedback import (
    build_feedback_command,
    resolve_racecoach,
    run_feedback,
)
from accapture.errors import RaceCoachNotFound


def test_resolve_racecoach_python_script(tmp_path: Path) -> None:
    script = tmp_path / "stub racecoach.py"
    script.write_text("print('stub')\n", encoding="utf-8")
    command = resolve_racecoach(str(script))
    assert command == [sys.executable, str(script)]


def test_build_feedback_command_has_analysis_arguments(tmp_path: Path) -> None:
    command = build_feedback_command(
        tmp_path / "reference lap.csv",
        tmp_path / "session lap.csv",
        racecoach="racecoach",
        json_output=True,
    )
    assert command[0] == "racecoach"
    assert command[1:3] == ["analyze", "--reference"]
    assert command[-1] == "--json"
    assert "--practice" in command


def test_run_feedback_invokes_a_stub_racecoach(tmp_path: Path) -> None:
    reference = tmp_path / "reference lap.csv"
    session = tmp_path / "session lap.csv"
    reference.write_text("reference\n", encoding="utf-8")
    session.write_text("session\n", encoding="utf-8")
    stub = tmp_path / "stub racecoach.py"
    stub.write_text(
        "import sys\nprint('STUB ' + ' '.join(sys.argv[1:]))\n", encoding="utf-8"
    )
    completed = run_feedback(
        reference, session, racecoach=str(stub), capture_output=True
    )
    assert completed.returncode == 0
    assert "analyze" in completed.stdout
    assert "--reference" in completed.stdout
    assert str(reference) in completed.stdout
    assert str(session) in completed.stdout


def test_run_feedback_requires_existing_files(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        run_feedback(tmp_path / "missing reference.csv", tmp_path / "missing session.csv")


def test_run_feedback_reports_missing_executable(tmp_path: Path) -> None:
    reference = tmp_path / "reference.csv"
    session = tmp_path / "session.csv"
    reference.write_text("reference\n", encoding="utf-8")
    session.write_text("session\n", encoding="utf-8")
    with pytest.raises(RaceCoachNotFound):
        run_feedback(
            reference,
            session,
            racecoach=str(tmp_path / "does-not-exist"),
            capture_output=True,
        )
