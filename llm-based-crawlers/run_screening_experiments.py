#!/usr/bin/env python3
"""Screening-phase runner: 5 trials per agent–captcha pair.

Protocol matches the paper protocol:
each agent–defense configuration is evaluated with five attempts while
recording screen capture and structured agent results.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_URLS = [
    "https://h-easy.example.test/",
    "https://h-hard.example.test/",
    "https://v2.example.test/",
    "https://v2-invis.example.test/",
    "https://v3f.example.test/",
    "https://t.example.test/",
    "https://t-invis.example.test/",
]

AGENTS = {
    "browser-use": {
        "cwd": ROOT / "browser-use-app",
        "python": ROOT / "browser-use-app" / ".venv" / "bin" / "python",
        "script": ROOT / "browser-use-app" / "main.py",
        "artifacts_subdir": "browser-use",
    },
    "open-manus": {
        "cwd": ROOT / "open-manus-app" / "OpenManus",
        "python": ROOT / "open-manus-app" / "OpenManus" / ".venv" / "bin" / "python",
        "script": ROOT / "open-manus-app" / "OpenManus" / "main.py",
        "artifacts_subdir": "open-manus",
    },
    "seeact": {
        "cwd": ROOT / "seeact-app",
        "python": ROOT / "seeact-app" / ".venv" / "bin" / "python",
        "script": ROOT / "seeact-app" / "main.py",
        "artifacts_subdir": "seeact",
    },
    "skyvern": {
        "cwd": ROOT / "skyvern-app",
        "python": ROOT / "skyvern-app" / ".venv" / "bin" / "python",
        "script": ROOT / "skyvern-app" / "main.py",
        "artifacts_subdir": "skyvern",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_openai_key() -> str:
    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key

    env_path = ROOT / "browser-use-app" / ".env"
    if not env_path.exists():
        raise SystemExit("OPENAI_API_KEY not set and browser-use-app/.env missing")

    text = env_path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^\s*OPENAI_API_KEY\s*=\s*(.+?)\s*$", text)
    if not match:
        raise SystemExit("OPENAI_API_KEY not found in browser-use-app/.env")
    return match.group(1).strip().strip('"').strip("'")


def configure_open_manus_api_key(api_key: str) -> None:
    config_path = ROOT / "open-manus-app" / "OpenManus" / "config" / "config.toml"
    if not config_path.exists():
        raise SystemExit(f"Missing OpenManus config: {config_path}")
    text = config_path.read_text(encoding="utf-8")
    if re.search(r'(?m)^api_key\s*=\s*".*"\s*$', text):
        text = re.sub(r'(?m)^api_key\s*=\s*".*"\s*$', f'api_key = "{api_key}"', text)
    else:
        text = text.replace("[llm] # OPENAI", f'[llm] # OPENAI\napi_key = "{api_key}"')
        if 'api_key =' not in text:
            text += f'\napi_key = "{api_key}"\n'
    config_path.write_text(text, encoding="utf-8")


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def run_one(
    agent_name: str,
    url: str,
    trial: int,
    exp_root: Path,
    api_key: str,
    dry_run: bool = False,
) -> dict:
    agent = AGENTS[agent_name]
    artifacts_dir = exp_root / agent["artifacts_subdir"]
    for sub in ("result", "recordings", "terminal_logs", "agent_traces"):
        (artifacts_dir / sub).mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["OPENAI_API_KEY"] = api_key
    env["DISPLAY"] = env.get("DISPLAY") or ":1"
    env["EXPERIMENT_ARTIFACTS_DIR"] = str(artifacts_dir)
    env["EXPERIMENT_TRIAL"] = str(trial)
    env["EXPERIMENT_AGENT"] = agent_name
    # Avoid dotenv TARGET_URLS list syntax confusing agents; always use --url.
    env.pop("TARGET_URLS", None)

    cmd = [str(agent["python"]), str(agent["script"]), "--url", url]
    started = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    record = {
        "agent": agent_name,
        "target_url": url,
        "trial": trial,
        "started_utc": started,
        "artifacts_dir": str(artifacts_dir),
        "command": cmd,
    }

    print(
        f"\n=== [{agent_name}] trial {trial}/5 :: {url} ===\n"
        f"artifacts: {artifacts_dir}",
        flush=True,
    )

    if dry_run:
        record.update(
            {
                "dry_run": True,
                "returncode": 0,
                "elapsed_seconds": 0.0,
                "finished_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        return record

    completed = subprocess.run(
        cmd,
        cwd=str(agent["cwd"]),
        env=env,
        check=False,
    )
    elapsed = time.perf_counter() - t0
    record.update(
        {
            "returncode": completed.returncode,
            "elapsed_seconds": round(elapsed, 3),
            "finished_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    print(
        f"=== done [{agent_name}] trial {trial} rc={completed.returncode} "
        f"elapsed={elapsed:.1f}s ===",
        flush=True,
    )
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exp-root",
        type=str,
        default="",
        help="Existing experiment_runs/screening_* directory to continue into",
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        default=list(AGENTS.keys()),
        choices=list(AGENTS.keys()),
    )
    parser.add_argument("--urls", nargs="+", default=DEFAULT_URLS)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument(
        "--start-from",
        type=str,
        default="",
        help="Resume key agent|url|trial (1-based trial), e.g. seeact|https://v2.../|3",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run only the first agent/url/trial then exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = load_openai_key()
    configure_open_manus_api_key(api_key)

    if args.exp_root:
        exp_root = Path(args.exp_root).resolve()
    else:
        stamp = utc_now()
        exp_root = ROOT / "experiment_runs" / f"screening_{stamp}"
    exp_root.mkdir(parents=True, exist_ok=True)

    master_log = exp_root / "master_run_log.jsonl"
    status_path = exp_root / "status.json"
    print(f"Experiment root: {exp_root}", flush=True)

    jobs = []
    for agent_name in args.agents:
        for url in args.urls:
            for trial in range(1, args.trials + 1):
                jobs.append((agent_name, url, trial))

    if args.start_from:
        try:
            a, u, t = args.start_from.split("|", 2)
            start_key = (a, u, int(t))
        except Exception as exc:
            raise SystemExit(f"Invalid --start-from: {exc}") from exc
        filtered = []
        seen = False
        for job in jobs:
            if job == start_key:
                seen = True
            if seen:
                filtered.append(job)
        if not seen:
            raise SystemExit(f"--start-from not found in job list: {args.start_from}")
        jobs = filtered

    if args.smoke:
        jobs = jobs[:1]

    status = {
        "experiment_root": str(exp_root),
        "total_jobs": len(jobs),
        "completed": 0,
        "failed": 0,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": "screening_5_per_pair",
    }
    status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    failures = 0
    for idx, (agent_name, url, trial) in enumerate(jobs, start=1):
        print(f"\n----- job {idx}/{len(jobs)} -----", flush=True)
        record = run_one(
            agent_name=agent_name,
            url=url,
            trial=trial,
            exp_root=exp_root,
            api_key=api_key,
            dry_run=args.dry_run,
        )
        append_jsonl(master_log, record)
        if record.get("returncode", 1) != 0:
            failures += 1
            status["failed"] = failures
        status["completed"] = idx
        status["last_job"] = {
            "agent": agent_name,
            "url": url,
            "trial": trial,
            "returncode": record.get("returncode"),
        }
        status["updated_utc"] = datetime.now(timezone.utc).isoformat()
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    status["finished_utc"] = datetime.now(timezone.utc).isoformat()
    status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(
        f"\nFinished screening run. jobs={len(jobs)} failures={failures}\n"
        f"Results under: {exp_root}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
