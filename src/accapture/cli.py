"""Command line interface for accapture."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .demo import DemoSource
from .errors import AccaptureError, RaceCoachNotFound, SharedMemoryUnavailable, UnsupportedPlatform
from .feedback import run_feedback
from .mapping import SharedMemorySource
from .recorder import Recorder, RecorderOptions


def _record_laps(value: str) -> int | None:
    try:
        laps = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--laps must be an integer") from exc
    if laps < 0:
        raise argparse.ArgumentTypeError("--laps cannot be negative")
    return None if laps == 0 else laps


def _open_live_source(args) -> SharedMemorySource | None:
    deadline = time.monotonic() + args.wait_s
    while True:
        try:
            return SharedMemorySource(game=args.game)
        except UnsupportedPlatform as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return None
        except SharedMemoryUnavailable as exc:
            if time.monotonic() >= deadline:
                print(f"Error: {exc}", file=sys.stderr)
                print(
                    "Start Assetto Corsa or Assetto Corsa Competizione, enter a "
                    "session, then run the command again.",
                    file=sys.stderr,
                )
                return None
            print(f"Waiting for {args.game.upper()} shared memory... ({exc})")
            time.sleep(1.0)


def cmd_record(args) -> int:
    laps = args.laps
    if args.demo:
        if laps is None:
            laps = 1
        source = DemoSource(laps=laps)
        options = RecorderOptions(
            laps=laps,
            min_samples=args.min_samples,
            stale_timeout_s=args.stale_timeout_s,
            poll_hz=args.poll_hz,
        )
        sleep = lambda _seconds: None
    else:
        if sys.platform != "win32":
            print(
                "Error: live AC/ACC shared-memory capture is Windows-only. "
                "Use `accapture record --demo --out PATH` on this platform.",
                file=sys.stderr,
            )
            return 2
        source = _open_live_source(args)
        if source is None:
            return 3
        options = RecorderOptions(
            laps=laps,
            min_samples=args.min_samples,
            stale_timeout_s=args.stale_timeout_s,
            poll_hz=args.poll_hz,
        )
        sleep = time.sleep

    recorder = Recorder(args.out, options, sleep=sleep)
    try:
        result = recorder.run(source)
    except KeyboardInterrupt:
        # Recorder.run normally catches this; this is a last-resort guard for
        # Ctrl+C while opening the CSV file or source.
        print("Stopped by user.", file=sys.stderr)
        return 130
    except AccaptureError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 4

    print(
        f"Recorded {result.laps_completed} completed lap(s), "
        f"{result.partial_laps} partial lap(s), {result.rows_written} rows."
    )
    print(f"CSV: {result.out_path.resolve()}")
    if result.game_closed:
        print("The game closed or stopped updating; any in-progress lap was saved as partial.")
    if result.rows_written == 0:
        print(
            "No telemetry rows were written. Check that the game was in a live "
            "session and that the car was moving.",
            file=sys.stderr,
        )
        return 4
    if args.reference:
        print("Running RaceCoach feedback...")
        try:
            completed = run_feedback(
                args.reference,
                result.out_path,
                racecoach=args.racecoach,
                json_output=args.json,
            )
        except (FileNotFoundError, RaceCoachNotFound) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 5
        return int(completed.returncode)
    return 0


def cmd_feedback(args) -> int:
    try:
        completed = run_feedback(
            args.reference,
            args.session,
            racecoach=args.racecoach,
            json_output=args.json,
        )
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except RaceCoachNotFound as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return int(completed.returncode)


def cmd_probe(args) -> int:
    if sys.platform != "win32":
        print(
            "Error: AC/ACC shared memory is Windows-only. This command has "
            "nothing to read on this platform.",
            file=sys.stderr,
        )
        return 2
    try:
        source = SharedMemorySource(game=args.game)
    except (SharedMemoryUnavailable, UnsupportedPlatform) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 3

    try:
        sample = None
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            sample = source.poll()
            if sample is not None:
                break
            time.sleep(1.0 / max(1.0, args.poll_hz))
        if sample is None:
            print("Error: no new telemetry arrived before the timeout.", file=sys.stderr)
            return 3
        payload = {
            "game": args.game,
            "physics": sample.physics.to_dict(),
            "graphics": sample.graphics.to_dict(),
            "static": sample.static.to_dict() if sample.static else None,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    finally:
        source.close()


def cmd_version(_args) -> int:
    print(f"accapture {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="accapture",
        description="Read-only AC/ACC shared-memory lap capture for RaceCoach",
    )
    parser.add_argument("--version", action="version", version=f"accapture {__version__}")
    sub = parser.add_subparsers(dest="command")

    record = sub.add_parser("record", help="Record live telemetry to a RaceCoach CSV")
    record.add_argument("--game", choices=("ac", "acc"), default="acc")
    record.add_argument("--out", required=True, help="Output CSV path")
    record.add_argument(
        "--laps",
        type=_record_laps,
        default=1,
        help="Completed laps to record; 0 records until Ctrl+C (default: 1)",
    )
    record.add_argument(
        "--reference",
        help="Optional RaceCoach reference CSV; run feedback after recording",
    )
    record.add_argument(
        "--racecoach",
        help="Path to the RaceCoach executable (or a .py file); default: PATH or python -m racecoach",
    )
    record.add_argument(
        "--json",
        action="store_true",
        help="Pass --json to RaceCoach when --reference is used",
    )
    record.add_argument(
        "--demo",
        action="store_true",
        help="Record deterministic synthetic laps instead of the Windows shared memory",
    )
    record.add_argument(
        "--wait-s",
        type=float,
        default=60.0,
        help="Seconds to wait for the game's mappings to appear (default: 60)",
    )
    record.add_argument(
        "--stale-timeout-s",
        type=float,
        default=5.0,
        help="Treat no new telemetry for this long as the game closing (default: 5)",
    )
    record.add_argument(
        "--poll-hz",
        type=float,
        default=50.0,
        help="Polling rate for live capture (default: 50)",
    )
    record.add_argument(
        "--min-samples",
        type=int,
        default=20,
        help="Discard a lap with fewer samples than this (default: 20)",
    )
    record.set_defaults(func=cmd_record)

    feedback = sub.add_parser(
        "feedback", help="Run RaceCoach analysis on a recorded session"
    )
    feedback.add_argument("--reference", required=True, help="Reference lap CSV")
    feedback.add_argument("--session", required=True, help="Recorded session CSV")
    feedback.add_argument(
        "--racecoach",
        help="Path to the RaceCoach executable (or a .py file); default: PATH or python -m racecoach",
    )
    feedback.add_argument(
        "--json", action="store_true", help="Pass --json to RaceCoach"
    )
    feedback.set_defaults(func=cmd_feedback)

    probe = sub.add_parser(
        "probe", help="Print one decoded shared-memory update (Windows only)"
    )
    probe.add_argument("--game", choices=("ac", "acc"), default="acc")
    probe.add_argument("--timeout", type=float, default=10.0)
    probe.add_argument("--poll-hz", type=float, default=50.0)
    probe.set_defaults(func=cmd_probe)

    version = sub.add_parser("version", help="Print the version")
    version.set_defaults(func=cmd_version)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
