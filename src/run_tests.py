import subprocess
import sys
from pathlib import Path


def run_script(script_path: Path, cwd: Path) -> int:
    command = [sys.executable, str(script_path)]
    print(f"\n=== Running {script_path.name} ===")

    result = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )

    log_dir = cwd / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{script_path.stem}.log"
    log_file.write_text(
        "".join(
            [
                f"Command: {' '.join(command)}\n",
                f"Exit code: {result.returncode}\n\n",
                "--- STDOUT ---\n",
                result.stdout or "",
                "\n--- STDERR ---\n",
                result.stderr or "",
            ]
        ),
        encoding="utf-8",
    )

    if result.returncode != 0:
        print(f"[FAIL] {script_path.name} (see {log_file})")
    else:
        print(f"[OK] {script_path.name}")

    return result.returncode


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"

    scripts = [
        src_dir / "user_script_base.py",
        src_dir / "user_script_classroom.py",
        src_dir / "user_script_H.py",
    ]

    missing = [str(path) for path in scripts if not path.exists()]
    if missing:
        print("Missing scripts:")
        for path in missing:
            print(f"- {path}")
        return 2

    exit_code = 0
    for script in scripts:
        result = run_script(script, repo_root)
        if result != 0:
            exit_code = result
            break

    if exit_code == 0:
        print("\nAll smoke tests passed.")
    else:
        print("\nSmoke tests failed.")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
