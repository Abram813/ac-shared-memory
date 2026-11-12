# accapture

Read-only Assetto Corsa / Assetto Corsa Competizione shared-memory capture for
[RaceCoach](https://github.com/Abram813/sim-race-engineer).

`accapture` records a lap from the game's documented Windows shared-memory
pages into the same CSV format RaceCoach already understands:

```csv
lap_number,distance_m,elapsed_s,speed_kmh,throttle,brake
```

It can then hand the recorded CSV to RaceCoach and print measurable coaching
against a saved reference lap. The capture side is deliberately small and
dependency-free; the analysis stays in RaceCoach.

## Safety and scope

- The live reader only calls `OpenFileMappingW` with `FILE_MAP_READ`. It never
  creates, writes, or changes the game's mappings.
- It does not inject code, change memory, automate the car, or bypass
  anti-cheat. It reads the same telemetry that dashboards and telemetry apps
  use.
- Live capture is Windows-only because AC/ACC shared memory is a Windows API.
  The decoder, recorder, CSV writer, and demo mode run on macOS and Linux too.
- The capture agent does not import RaceCoach. It invokes the separate
  `racecoach` command, so the two repositories can live in separate virtual
  environments.

## Requirements

- Windows 10/11 for live AC/ACC capture.
- Assetto Corsa or Assetto Corsa Competizione running in a session for live
  capture.
- Python 3.10 or newer.
- [uv](https://docs.astral.sh/uv/).
- RaceCoach for feedback (optional for recording only).

## Install

From PowerShell, Command Prompt, or a shell whose path contains spaces:

```powershell
git clone https://github.com/Abram813/ac-shared-memory.git
cd ac-shared-memory
uv sync --all-groups
```

On macOS the same commands work; live capture will report that it is
Windows-only, while tests, demo recording, and feedback plumbing still work.

## Quick start without a game

Generate a deterministic two-lap demo session:

```powershell
uv run accapture record --demo --out "demo laps\session.csv" --laps 2
```

Expected output:

```text
Writing demo laps\session.csv
Recording lap 1...
Saved lap 1 (1201 samples).
Recording lap 2...
Saved lap 2 (1201 samples).
Reached the requested 2 completed lap(s).
Recorded 2 completed lap(s), 0 partial lap(s), 2402 rows.
CSV: C:\...\demo laps\session.csv
```

The demo has five braking zones and is intentionally repeatable. It is for
testing the recorder and CSV contract, not for judging a real driver.

Run RaceCoach feedback against the demo session. If RaceCoach is installed in
the same environment, omit `--racecoach`:

```powershell
uv run accapture feedback `
  --reference "C:\path\to\sim-race-engineer\examples\reference_lap.csv" `
  --session "demo laps\session.csv" `
  --racecoach "C:\path\to\sim-race-engineer\.venv\Scripts\racecoach.exe"
```

On macOS:

```bash
uv run accapture feedback \
  --reference "/path/to/sim-race-engineer/examples/reference_lap.csv" \
  --session "demo laps/session.csv" \
  --racecoach "/path/to/sim-race-engineer/.venv/bin/racecoach"
```

The feedback is ordinary RaceCoach output, including lines such as:

```text
Feedback: You started braking 12 metres earlier and took 0.18 seconds longer through this section (minimum speed 2.0 km/h lower).
```

## Live capture

Start AC or ACC, enter a session, and drive onto the track. Then check that the
mappings are readable:

```powershell
uv run accapture probe --game acc
```

Expected shape (values depend on the car and track):

```json
{
  "game": "acc",
  "physics": {
    "packet_id": 12345,
    "gas": 0.0,
    "brake": 0.42,
    "speed_kmh": 123.4
  },
  "graphics": {
    "status": 2,
    "status_name": "live",
    "completed_laps": 0,
    "distance_traveled_m": 812.5,
    "is_in_pit": false
  },
  "static": {
    "car_model": "ferrari_488_gt3_evo",
    "track": "monza"
  }
}
```

Record a reference lap:

```powershell
uv run accapture record `
  --game acc `
  --out "laps\reference lap.csv" `
  --laps 1
```

Then record a practice lap and ask RaceCoach for feedback automatically:

```powershell
uv run accapture record `
  --game acc `
  --out "laps\practice lap.csv" `
  --laps 1 `
  --reference "laps\reference lap.csv" `
  --racecoach "C:\path\to\sim-race-engineer\.venv\Scripts\racecoach.exe"
```

Use `--laps 0` to record until `Ctrl+C`. The recorder saves any in-progress lap
as a partial lap when the game closes, telemetry stops, or the user stops it.

### What happens when the game state changes

| Game state | Recorder behavior |
| --- | --- |
| Live (`status == 2`) | Samples are written to the current lap. |
| Paused (`status == 3`) | Prints `Game paused; recording paused.` once and skips samples. On resume it prints `Game resumed.` |
| Replay (`status == 1`) | Prints `Replay is running; recording is paused.` and skips samples. |
| Off/menu (`status == 0`) | Stops with a `Game closed` message. |
| Game closed or no new packets | After `--stale-timeout-s` (default 5 seconds) the current lap is saved as partial and recording stops. |
| New lap (`completedLaps` increments) | Saves the finished lap, starts the next lap, and prints `Saved lap N...` / `Recording lap N...`. |
| Distance resets | Treated as a new lap even if `completedLaps` did not update. |
| Lap timer resets | Treated as a new lap if the elapsed time jumps backward. |
| Duplicate packet IDs | Ignored, so the same telemetry frame is never written twice. |

The recorder needs at least `--min-samples` rows (default 20) before it keeps a
lap. This avoids empty or one-frame files.

## CSV contract

RaceCoach expects exactly these columns:

```csv
lap_number,distance_m,elapsed_s,speed_kmh,throttle,brake
```

- `lap_number` is 1-based.
- `distance_m` is the game's `distanceTraveled` in metres.
- `elapsed_s` is the game's `iCurrentTime` in seconds when available; otherwise
  it falls back to monotonic time since the lap started.
- `speed_kmh` is the physics page's `speedKmh`.
- `throttle` and `brake` are clamped to `0.0`–`1.0`.

Multiple laps can be written to one file; RaceCoach lets you choose the lap.
Rows are flushed after every completed lap.

## Packet decoding

The game exposes three named file mappings:

| Mapping | Purpose |
| --- | --- |
| `Local\acpmf_physics` | Pedals, speed, gear, RPM, steering |
| `Local\acpmf_graphics` | Session status, completed laps, lap time, distance |
| `Local\acpmf_static` | Car, track, player, and session metadata |

The decoder reads only the prefixes it needs. `wchar_t` is two bytes on
Windows, so the four UTF-16 time strings in the graphics page occupy 120 bytes;
the decoder skips them by offset instead of using `ctypes.c_wchar` (which is
four bytes on macOS/Linux).

### Physics prefix: 32 bytes

Format: `<ifffiiff`

| Offset | Type | Field |
| --- | --- | --- |
| 0 | int32 | `packetId` |
| 4 | float32 | `gas` |
| 8 | float32 | `brake` |
| 12 | float32 | `fuel` |
| 16 | int32 | `gear` |
| 20 | int32 | `rpms` |
| 24 | float32 | `steerAngle` |
| 28 | float32 | `speedKmh` |

### Graphics prefix

| Offset | Type | Field |
| --- | --- | --- |
| 0 | int32 | `packetId` |
| 4 | int32 | `status` |
| 8 | int32 | `session` |
| 12 | wchar_t[15] | `currentTime` |
| 42 | wchar_t[15] | `lastTime` |
| 72 | wchar_t[15] | `bestTime` |
| 102 | wchar_t[15] | `split` |
| 132 | int32 | `completedLaps` |
| 136 | int32 | `position` |
| 140 | int32 | `iCurrentTime` (ms) |
| 144 | int32 | `iLastTime` (ms) |
| 148 | int32 | `iBestTime` (ms) |
| 152 | float32 | `sessionTimeLeft` |
| 156 | float32 | `distanceTraveled` |
| 160 | int32 | `isInPit` |
| 164 | int32 | `currentSectorIndex` |
| 168 | int32 | `lastSectorTime` |
| 172 | int32 | `numberOfLaps` |
| 176 | wchar_t[33] | `tyreCompound` |
| 242 | float32 | `replayTimeMultiplier` |
| 246 | float32 | `normalizedCarPosition` |
| 250 | float32[3] | `carCoordinates` |

The decoder requires 176 bytes and reads `normalizedCarPosition` only when the
page contains at least 250 bytes. Status values are `0 = off`, `1 = replay`,
`2 = live`, `3 = paused`. Session values are `-1 = unknown`, `0 = practice`,
`1 = qualify`, `2 = race`, `3 = hotlap`, `4 = time attack`, `5 = drift`,
`6 = drag`.

### Static prefix

| Offset | Type | Field |
| --- | --- | --- |
| 0 | wchar_t[15] | `smVersion` |
| 30 | wchar_t[15] | `acVersion` |
| 60 | int32 | `numberOfSessions` |
| 64 | int32 | `numCars` |
| 68 | wchar_t[33] | `carModel` |
| 134 | wchar_t[33] | `track` |
| 200 | wchar_t[33] | `playerName` |
| 266 | wchar_t[33] | `playerSurname` |
| 332 | wchar_t[33] | `playerNick` |
| 398 | int32 | `sectorCount` |
| 402 | float32 | `maxTorque` |
| 406 | float32 | `maxPower` |
| 410 | int32 | `maxRpm` |

## Tests

Install dev dependencies once:

```powershell
uv sync --all-groups
```

Run the offline suite:

```powershell
uv run pytest -q
```

Run the CLI smoke test, which writes into a path containing spaces:

```powershell
uv run python scripts/smoke.py
```

The test suite is offline. `tests/conftest.py` blocks non-loopback sockets and
DNS; loopback is allowed only so the fake-mapping and subprocess tests can use
local resources. You can make the intent explicit:

```powershell
$env:ACCAPTURE_OFFLINE = "1"
uv run pytest -q
```

### Packet-decoding tests vs. running-game tests

These are deliberately separate:

- **Packet-decoding tests** (`tests/test_packets.py`, `tests/test_demo.py`,
  `tests/test_recorder.py`, `tests/test_feedback.py`, `tests/test_cli.py`)
  use encoded bytes and synthetic samples. They need no game.
- **Fake-game Windows tests** (`tests/test_mapping.py`) create real Windows
  file mappings with `CreateFileMappingW`, write encoded packets, and verify
  that the read-only production reader, decoder, and recorder work together.
  These tests skip on macOS.
- **Running-game testing** is a manual procedure below. It has not been
  performed in this repository's development environment because that
  environment is macOS and does not have AC/ACC installed.

### Verified environments

| Environment | OS / architecture | Python | uv | Result |
| --- | --- | --- | --- | --- |
| Local development | macOS 26.6.2, arm64 (Apple M1 Pro) | 3.14.2 | 0.13.7 | 43 passed, 4 skipped; smoke passed; demo feedback passed |
| GitHub Actions `windows-x64` | Windows Server 2025, x86_64 (AMD64) | 3.12.10 | 0.13.7 | 44 passed, 3 skipped (Windows fake mappings ran); smoke passed |
| GitHub Actions `macos-arm64` | macOS 15.8.2, arm64 (Apple Silicon) | 3.12.10 | 0.13.7 | 43 passed, 4 skipped (Windows mappings skipped); smoke passed |
| GitHub Actions `macos-x64` | macOS 15.7.9, x86_64 (Intel) | 3.12.10 | 0.13.7 | 43 passed, 4 skipped (Windows mappings skipped); smoke passed |

CI run: [43295343728](https://github.com/Abram813/ac-shared-memory/actions/runs/43295343728), commit `4d1beac`. The environment artifacts show the executable path inside `fresh clone/accapture`, confirming the path-with-spaces run. Verified Mac architectures: Apple Silicon arm64 and Intel x86_64.

The CI jobs clone the repository into a directory whose name contains spaces
(`fresh clone/accapture`), then run `uv sync --all-groups`, the offline tests,
and `scripts/smoke.py`. Each job uploads an `environment.txt` artifact with the
actual OS, CPU architecture, Python version, and uv version.

## Running-game test procedure (not performed here)

Use a Windows machine with AC or ACC installed. This is the only way to verify
the live mapping path against a real game.

1. Start the game and enter a practice or hotlap session. Drive one clean
   reference lap.
2. In PowerShell, run:

   ```powershell
   uv run accapture probe --game acc
   ```

   Expected: exit code `0` and JSON whose `graphics.status_name` is `"live"`,
   `graphics.distance_traveled_m` changes as the car moves, and
   `physics.speed_kmh` is plausible for the car.
3. Record a reference lap:

   ```powershell
   uv run accapture record --game acc --out "laps\reference lap.csv" --laps 1
   ```

   Expected: `Recording lap 1...`, then `Saved lap 1 (... samples).`, then
   `Recorded 1 completed lap(s)`. The CSV must contain the six contract columns
   and a `lap_number` of `1`.
4. Record a practice lap with feedback:

   ```powershell
   uv run accapture record `
     --game acc `
     --out "laps\practice lap.csv" `
     --laps 1 `
     --reference "laps\reference lap.csv" `
     --racecoach "C:\path\to\sim-race-engineer\.venv\Scripts\racecoach.exe"
   ```

   Expected: the recorder writes the practice CSV, prints
   `Running RaceCoach feedback...`, and RaceCoach prints one feedback line per
   completed braking zone.
5. Pause test: while recording, pause the game. Expected:
   `Game paused; recording paused.` Unpause and expect `Game resumed.` The
   pause interval must not inflate `elapsed_s`; the lap timer comes from the
   game, not wall-clock time.
6. New-lap test: record with `--laps 2` and cross the finish line. Expected:
   `Saved lap 1 (... samples).` followed by `Recording lap 2...`. The CSV must
   contain rows with `lap_number` `1` and `2`.
7. Game-closed test: start a recording, drive for a few seconds, then close the
   game. Expected: a `Game closed` message, a `Saved partial lap ...` message,
   and a non-empty CSV. If the game is closed before any samples, the command
   exits with code `4` and explains that no rows were written.
8. If the game is not running when `record` starts, expected: it prints
   `Waiting for ACC shared memory...` and retries until `--wait-s` (default 60
   seconds) expires, then exits with code `3` and tells you to start the game.

Record the actual OS, CPU architecture, Python version, and uv version in the
handover report. Do not describe packet-decoding tests as running-game tests.

## Troubleshooting

- `Could not open shared memory`: start the game and enter a session; the
  mappings do not exist at the main menu or before the game launches.
- `Windows-only`: live capture and `probe` require Windows. Use
  `record --demo` elsewhere.
- `Could not start RaceCoach`: install RaceCoach in the same environment, put
  `racecoach` on `PATH`, or pass `--racecoach` with the full path to the
  executable (or to a `.py` file).
- Partial lap saved: the game closed, telemetry stopped, or the recording was
  stopped before the lap completed. RaceCoach can still analyze the available
  distance range and will flag gaps or skipped sections.
- No rows: the car may have been stationary, the game may have been paused, or
  the session may have ended before the minimum sample count was reached.

## Two-minute VS Code walkthrough

1. Open the `ac-shared-memory` folder in VS Code.
2. Open the integrated terminal and run `uv sync --all-groups`. This creates
   `.venv` and installs pytest.
3. Run `uv run pytest -q`. You should see the packet, recorder, CLI, feedback,
   and offline tests pass. On macOS, the four Windows fake-mapping tests are
   skipped; on Windows they run against real mappings.
4. Run `uv run python scripts/smoke.py`. It writes `demo laps/session.csv`,
   records two laps, checks the six-column CSV contract, and invokes a stub
   RaceCoach through the subprocess boundary.
5. Open `demo laps/session.csv` in VS Code and confirm the columns are
   `lap_number,distance_m,elapsed_s,speed_kmh,throttle,brake`.
6. Open `src/accapture/recorder.py` and follow `Recorder.consume`: pause/replay
   handling, completed-lap detection, distance resets, duplicate packet IDs,
   and partial-lap saving are all in that one state machine.
7. Open `src/accapture/packets.py` and show the graphics offsets: 132 for
   `completedLaps`, 140 for `iCurrentTime`, and 156 for `distanceTraveled`.
8. Run the feedback command from the Quick start section with the RaceCoach
   reference CSV. The terminal prints one measurable message per completed
   braking zone.
9. On Windows with the game running, run
   `uv run accapture probe --game acc`, then
   `uv run accapture record --game acc --out "laps\practice lap.csv" --laps 1 --reference "laps\reference lap.csv"`.
   That is the complete capture-to-coaching loop.

## License

MIT. See [LICENSE](LICENSE).
