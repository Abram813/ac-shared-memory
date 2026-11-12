"""Invoke the separate RaceCoach CLI for feedback.

accapture does not import RaceCoach.  Keeping the boundary at the command line
means the capture agent can be installed in its own environment and can point at
a RaceCoach checkout, virtual environment, or executable.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .errors import RaceCoachNotFound


def resolve_racecoach(racecoach: str | None = None) -> list[str]:
    """Return the command prefix used to launch RaceCoach."""

    if racecoach:
        path = Path(racecoach).expanduser()
        if path.suffix.lower() == ".py":
            return [sys.executable, str(path)]
        return [str(path)]
    executable = shutil.which("racecoach")
    if executable:
        return [executable]
    return [sys.executable, "-m", "racecoach"]


def build_feedback_command(
    reference: str | Path,
    session: str | Path,
    *,
    racecoach: str | None = None,
    json_output: bool = False,
) -> list[str]:
    command = resolve_racecoach(racecoach)
    command.extend(
        [
            "analyze",
            "--reference",
            str(reference),
            "--practice",
            str(session),
        ]
    )
    if json_output:
        command.append("--json")
    return command


def run_feedback(
    reference: str | Path,
    session: str | Path,
    *,
    racecoach: str | None = None,
    json_output: bool = False,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    reference_path = Path(reference)
    session_path = Path(session)
    if not reference_path.is_file():
        raise FileNotFoundError(f"Reference CSV not found: {reference_path}")
    if not session_path.is_file():
        raise FileNotFoundError(f"Session CSV not found: {session_path}")

    command = build_feedback_command(
        reference_path,
        session_path,
        racecoach=racecoach,
        json_output=json_output,
    )
    try:
        return subprocess.run(
            command,
            text=True,
            capture_output=capture_output,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RaceCoachNotFound(
            "Could not start RaceCoach. Install it in the same environment, "
            "put `racecoach` on PATH, or pass --racecoach PATH.\n"
            f"Command: {shlex.join(command)}"
        ) from exc
