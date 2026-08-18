"""Run the NEMOS stress suite and summarise what happened.

Each stress script is executed as its own process, so a crash, a SALOME hang or
a killed solver takes down only that one run. Output is streamed to the console
and also written to <stress root>/logs/<name>.log.

Usage
    python Templates/run_all_stress.py                 # the standard suite
    python Templates/run_all_stress.py --quick         # only the fast ones
    python Templates/run_all_stress.py 01 04           # only those scripts
    python Templates/run_all_stress.py --list
    python Templates/run_all_stress.py --timeout 7200  # per-script, seconds

The suite is ordered cheapest first and stops nothing on failure: a broken
stress 02 should not hide what stress 04 would have told you. Use --stop-first
if you would rather bail out early.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stress_lib import stress_root  # noqa: E402

HERE = Path(__file__).resolve().parent

#: (key, filename, minutes as a rough order of magnitude, quick?)
SUITE = [
    ("01", "stress_01_baseline.py",   "~10 min", True),
    ("06", "stress_06_resume.py",     "~15 min", True),
    ("04", "stress_04_corridor.py",   "~30 min", False),
    ("02", "stress_02_crowd.py",      "~60 min", False),
    ("05", "stress_05_sweep.py",      "~60 min", False),
    ("03", "stress_03_refinement.py", "hours",   False),
]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("keys", nargs="*", help="script keys to run, e.g. 01 04")
    parser.add_argument("--quick", action="store_true",
                        help="only the short scripts (01, 06)")
    parser.add_argument("--list", action="store_true", help="list the suite and exit")
    parser.add_argument("--stop-first", action="store_true",
                        help="stop at the first failing script")
    parser.add_argument("--timeout", type=int, default=None,
                        help="per-script timeout in seconds (default: none)")
    return parser.parse_args()


def selected(args):
    if args.keys:
        wanted = set(args.keys)
        chosen = [row for row in SUITE if row[0] in wanted]
        unknown = wanted - {row[0] for row in SUITE}
        if unknown:
            raise SystemExit(f"Unknown script key(s): {', '.join(sorted(unknown))}. "
                             f"Known: {', '.join(row[0] for row in SUITE)}.")
        return chosen
    if args.quick:
        return [row for row in SUITE if row[3]]
    return list(SUITE)


def main() -> int:
    args = parse_args()

    if args.list:
        print("key  script                       cost      quick")
        for key, name, cost, quick in SUITE:
            print(f" {key}   {name:<28} {cost:<9} {'yes' if quick else 'no'}")
        return 0

    suite = selected(args)
    root = stress_root()
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 78)
    print(f"NEMOS stress suite - {len(suite)} script(s)")
    print(f"Output root: {root}")
    print(f"Logs       : {log_dir}")
    print("=" * 78)

    results = []
    for key, name, cost, _quick in suite:
        script = HERE / name
        if not script.exists():
            print(f"\n[skip] {name} not found")
            results.append((key, name, "MISSING", 0.0))
            continue

        print(f"\n{'=' * 78}\n>>> {key}  {name}   (expected {cost})\n{'=' * 78}",
              flush=True)
        started = time.time()
        captured: list[str] = []
        status = "OK"
        try:
            process = subprocess.Popen(
                [sys.executable, str(script)],
                cwd=str(HERE),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            # Stream and capture at once: a stress run can take an hour and
            # watching it in silence is useless.
            for line in process.stdout:
                print(line, end="", flush=True)
                captured.append(line)
            process.wait(timeout=args.timeout)
            if process.returncode != 0:
                status = f"FAILED (exit {process.returncode})"
        except subprocess.TimeoutExpired:
            process.kill()
            status = f"TIMEOUT (>{args.timeout}s)"
        except KeyboardInterrupt:
            process.kill()
            status = "INTERRUPTED"
            elapsed = time.time() - started
            results.append((key, name, status, elapsed))
            (log_dir / f"{script.stem}.log").write_text("".join(captured),
                                                        encoding="utf-8")
            break
        except Exception as exc:  # noqa: BLE001
            status = f"HARNESS ERROR ({type(exc).__name__}: {exc})"

        elapsed = time.time() - started
        (log_dir / f"{script.stem}.log").write_text("".join(captured), encoding="utf-8")
        results.append((key, name, status, elapsed))
        print(f"\n<<< {key} {status} in {elapsed / 60:.1f} min", flush=True)

        if args.stop_first and status != "OK":
            print("\nStopping: --stop-first was given and this script failed.")
            break

    print("\n" + "=" * 78)
    print("STRESS SUITE SUMMARY")
    print("=" * 78)
    print(f"{'key':<5}{'script':<30}{'minutes':>9}   status")
    for key, name, status, elapsed in results:
        print(f"{key:<5}{name:<30}{elapsed / 60:>9.1f}   {status}")
    print("=" * 78)

    failed = [r for r in results if r[2] != "OK"]
    if failed:
        print(f"{len(failed)} of {len(results)} script(s) did not pass. "
              f"Logs are in {log_dir}")
        return 1
    print(f"All {len(results)} script(s) passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
