import argparse
import subprocess
import sys
from pathlib import Path


def run_many(times: int, stop_on_error: bool) -> int:
    project_dir = Path(__file__).resolve().parent
    main_script = project_dir / "main.py"

    failures = 0

    for i in range(1, times + 1):
        print(f"[{i}/{times}] Running {main_script.name}...")
        completed = subprocess.run([sys.executable, str(main_script)], cwd=project_dir)

        if completed.returncode != 0:
            failures += 1
            print(
                f"[{i}/{times}] Failed with exit code {completed.returncode}. "
                f"Total failures: {failures}"
            )
            if stop_on_error:
                print("Stopping early due to --stop-on-error.")
                return failures
        else:
            print(f"[{i}/{times}] Success")

    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run main.py repeatedly.")
    parser.add_argument(
        "-n",
        "--times",
        type=int,
        default=1000,
        help="How many times to run main.py (default: 1000).",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop immediately when one run fails.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.times <= 0:
        print("--times must be greater than 0.")
        sys.exit(2)

    failures = run_many(args.times, args.stop_on_error)
    print(f"Finished. Total failures: {failures}")
    sys.exit(1 if failures > 0 else 0)

