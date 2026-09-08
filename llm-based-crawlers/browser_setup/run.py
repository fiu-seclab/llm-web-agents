#!/usr/bin/env python3
"""Run the browser-configuration grid.

For each (agent, env config, instrument, trial):
  1. launch Chrome with the matching config (skipped for instrumented)
  2. attach the agent over CDP (or use its default Playwright for instrumented)
  3. record the run outcome (recording + terminal log) for manual review

Usage
-----
  python run.py --agents open-manus seeact skyvern --trials 1
  python run.py --agents browser-use --configs chrome_full --instruments turnstile --trials 1
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from chrome_launcher import (
    CHROME_CONFIGS,
    launch_chrome,
    stop_chrome,
)


ROOT = Path(__file__).resolve().parent
CRAWLERS = ROOT.parent

AGENTS = {
    "browser-use": {
        "cwd": CRAWLERS / "browser-use-app",
        "python": CRAWLERS / "browser-use-app" / ".venv" / "bin" / "python",
        "script": CRAWLERS / "browser-use-app" / "main.py",
        "artifacts_subdir": "browser-use",
        "timeout": 60,
    },
    "open-manus": {
        "cwd": CRAWLERS / "open-manus-app" / "OpenManus",
        "python": CRAWLERS / "open-manus-app" / "OpenManus" / ".venv" / "bin" / "python",
        "script": CRAWLERS / "open-manus-app" / "OpenManus" / "main.py",
        "artifacts_subdir": "open-manus",
        "timeout": 60,
    },
    "seeact": {
        "cwd": CRAWLERS / "seeact-app",
        "python": CRAWLERS / "seeact-app" / ".venv" / "bin" / "python",
        "script": CRAWLERS / "seeact-app" / "main.py",
        "artifacts_subdir": "seeact",
        "timeout": 60,
    },
    "skyvern": {
        "cwd": CRAWLERS / "skyvern-app",
        "python": CRAWLERS / "skyvern-app" / ".venv" / "bin" / "python",
        "script": CRAWLERS / "skyvern-app" / "main.py",
        "artifacts_subdir": "skyvern",
        "timeout": 60,
    },
}

ENV_CONFIGS = ("instrumented",) + CHROME_CONFIGS
INSTRUMENTS = {
    "v2-invis": "https://v2-invis.example.test/",
    "turnstile": "https://t.example.test/",
    "turnstile-invis": "https://t-invis.example.test/",
    "v3f": "https://v3f.example.test/",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_openai_key() -> str:
    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key

    env_path = CRAWLERS / "browser-use-app" / ".env"
    if not env_path.exists():
        raise SystemExit("OPENAI_API_KEY not set and browser-use-app/.env missing")
    text = env_path.read_text(encoding="utf-8")
    match = re.search(r"(?m)^\s*OPENAI_API_KEY\s*=\s*(.+?)\s*$", text)
    if not match:
        raise SystemExit("OPENAI_API_KEY not found in browser-use-app/.env")
    return match.group(1).strip().strip('"').strip("'")


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def latest_result_json(result_dir: Path, started_utc: str) -> dict | None:
    if not result_dir.exists():
        return None
    candidates = sorted(
        result_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        stamp = payload.get("timestamp_utc") or ""
        if stamp >= started_utc:
            payload["_result_path"] = str(path)
            return payload
    return None


def _token_brief(usage) -> str:
    if not isinstance(usage, dict) or not usage.get("available"):
        return "n/a"
    total = usage.get("total_tokens")
    if total is None:
        return "n/a"
    return str(total)


def _reap_stray_chrome() -> None:
    """Kill leftover throwaway Chrome from a previous timed-out cell."""
    try:
        subprocess.run(
            ["pkill", "-f", "browser-setup-chrome-"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def run_one(
    *,
    agent_name: str,
    env_config: str,
    instrument: str,
    trial: int,
    exp_root: Path,
    api_key: str,
    dry_run: bool = False,
    chrome_bin: str | None = None,
    full_profile: Path | None = None,
) -> dict:
    agent = AGENTS[agent_name]
    url = INSTRUMENTS[instrument]
    artifacts_dir = exp_root / agent["artifacts_subdir"] / env_config / instrument
    for sub in ("result", "recordings", "terminal_logs"):
        (artifacts_dir / sub).mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["OPENAI_API_KEY"] = api_key
    env.setdefault("DISPLAY", ":1")
    env["EXPERIMENT_ARTIFACTS_DIR"] = str(artifacts_dir)
    env["EXPERIMENT_TRIAL"] = str(trial)
    env["EXPERIMENT_AGENT"] = agent_name
    env["ENV_CONFIG"] = env_config
    env["INSTRUMENT"] = instrument
    env.pop("TARGET_URLS", None)

    started = datetime.now(timezone.utc).isoformat()
    record = {
        "agent": agent_name,
        "env_config": env_config,
        "instrument": instrument,
        "target_url": url,
        "trial": trial,
        "started_utc": started,
        "artifacts_dir": str(artifacts_dir),
    }

    print(
        f"\n=== [{agent_name}] {env_config} / {instrument} / trial {trial} ===\n"
        f"url: {url}\nartifacts: {artifacts_dir}",
        flush=True,
    )

    if dry_run:
        record.update({"dry_run": True, "returncode": 0, "elapsed_seconds": 0.0})
        return record

    t0 = time.perf_counter()
    job_limit = int(os.getenv("JOB_SECONDS", "60"))
    chrome = None
    if env_config != "instrumented":
        try:
            chrome = launch_chrome(
                env_config,
                chrome_bin=chrome_bin,
                user_data_dir=full_profile if env_config == "chrome_full" else None,
                log_dir=artifacts_dir / "terminal_logs",
            )
        except (SystemExit, TimeoutError) as exc:
            record.update({
                "returncode": 1,
                "failed": True,
                "error": str(exc),
                "elapsed_seconds": 0.0,
            })
            print(
                f"=== done [{agent_name}] {env_config}/{instrument} trial {trial} "
                f"rc=1 failed (chrome launch) ===",
                flush=True,
            )
            return record
        env["BROWSER_USE_CDP_URL"] = chrome.cdp_url
        record["cdp_url"] = chrome.cdp_url
        record["chrome_pid"] = chrome.pid
        record["user_data_dir"] = chrome.user_data_dir

    cmd = [str(agent["python"]), str(agent["script"]), "--url", url]
    record["command"] = cmd
    spent = time.perf_counter() - t0
    agent_timeout = max(5, job_limit - spent)
    env["POST_NAV_WAIT_SECONDS"] = os.getenv("POST_NAV_WAIT_SECONDS", "0")
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(agent["cwd"]),
            env=env,
            start_new_session=True,
        )
        record["returncode"] = proc.wait(timeout=agent_timeout)
    except subprocess.TimeoutExpired:
        record["returncode"] = 124
        record["error"] = f"agent timed out after {agent_timeout:.0f}s"
        record["timed_out"] = True
        if proc is not None:
            for sig, wait_s in ((signal.SIGTERM, 8), (signal.SIGKILL, 2)):
                try:
                    os.killpg(proc.pid, sig)
                except (ProcessLookupError, PermissionError, OSError):
                    try:
                        proc.kill()
                    except OSError:
                        pass
                    break
                try:
                    proc.wait(timeout=wait_s)
                    break
                except subprocess.TimeoutExpired:
                    continue
    finally:
        if chrome is not None:
            stop_chrome(chrome)
        _reap_stray_chrome()

    record["elapsed_seconds"] = round(time.perf_counter() - t0, 3)
    record["finished_utc"] = datetime.now(timezone.utc).isoformat()

    result_payload = latest_result_json(artifacts_dir / "result", started)
    if result_payload:
        record["result_path"] = result_payload.get("_result_path")
        record["submission_success"] = result_payload.get("submission_success")
        record["bypass_success"] = result_payload.get("bypass_success")
        record["timed_out"] = result_payload.get("timed_out") or record.get("timed_out")
        record["token_usage"] = result_payload.get("token_usage")

    if record.get("returncode", 1) != 0 or record.get("timed_out"):
        record["failed"] = True

    print(
        f"=== done [{agent_name}] {env_config}/{instrument} trial {trial} "
        f"rc={record.get('returncode')} "
        f"elapsed={record['elapsed_seconds']:.1f}s "
        f"tokens={_token_brief(record.get('token_usage'))} ===",
        flush=True,
    )
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exp-root", default="", help="Continue into an existing run dir")
    parser.add_argument(
        "--configs",
        nargs="+",
        default=list(ENV_CONFIGS),
        choices=list(ENV_CONFIGS),
    )
    parser.add_argument(
        "--instruments",
        nargs="+",
        default=list(INSTRUMENTS.keys()),
        choices=list(INSTRUMENTS.keys()),
    )
    parser.add_argument(
        "--agents",
        nargs="+",
        default=["browser-use"],
        choices=list(AGENTS.keys()),
    )
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--chrome-bin", default="")
    parser.add_argument(
        "--full-profile",
        default="",
        help="user-data-dir for chrome_full (default: browser_setup/profiles/chrome-full-research)",
    )
    parser.add_argument(
        "--start-from",
        default="",
        help="Resume key agent|config|instrument|trial, e.g. open-manus|chrome_incognito|v2-invis|1",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run only the first config/instrument/trial then exit",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    for agent_name in args.agents:
        python_bin = AGENTS[agent_name]["python"]
        if not python_bin.exists():
            raise SystemExit(f"Missing {agent_name} venv python: {python_bin}")

    api_key = load_openai_key()
    if args.exp_root:
        exp_root = Path(args.exp_root).resolve()
    else:
        exp_root = CRAWLERS / "experiment_runs" / f"browser_setup_{utc_now()}"
    exp_root.mkdir(parents=True, exist_ok=True)

    master_log = exp_root / "master_run_log.jsonl"
    token_log = exp_root / "token_usage.jsonl"
    status_path = exp_root / "status.json"
    print(f"Experiment root: {exp_root}", flush=True)

    jobs = []
    for agent_name in args.agents:
        for env_config in args.configs:
            for instrument in args.instruments:
                for trial in range(1, args.trials + 1):
                    jobs.append((agent_name, env_config, instrument, trial))

    if args.start_from:
        parts = args.start_from.split("|")
        try:
            if len(parts) == 4:
                start_key = (parts[0], parts[1], parts[2], int(parts[3]))
            elif len(parts) == 3:
                start_key = (args.agents[0], parts[0], parts[1], int(parts[2]))
            else:
                raise ValueError("expected agent|config|instrument|trial")
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
            raise SystemExit(f"--start-from not found: {args.start_from}")
        jobs = filtered

    if args.smoke:
        jobs = jobs[:1]

    status = {
        "experiment_root": str(exp_root),
        "agents": list(args.agents),
        "total_jobs": len(jobs),
        "completed": 0,
        "failed": 0,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": "browser_setup",
    }
    status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    failures = 0
    full_profile = Path(args.full_profile).expanduser() if args.full_profile else None
    for idx, (agent_name, env_config, instrument, trial) in enumerate(jobs, start=1):
        print(f"\n----- job {idx}/{len(jobs)} -----", flush=True)
        record = run_one(
            agent_name=agent_name,
            env_config=env_config,
            instrument=instrument,
            trial=trial,
            exp_root=exp_root,
            api_key=api_key,
            dry_run=args.dry_run,
            chrome_bin=args.chrome_bin or None,
            full_profile=full_profile,
        )
        append_jsonl(master_log, record)
        append_jsonl(
            token_log,
            {
                "agent": agent_name,
                "env_config": env_config,
                "instrument": instrument,
                "trial": trial,
                "timed_out": record.get("timed_out"),
                "elapsed_seconds": record.get("elapsed_seconds"),
                "token_usage": record.get("token_usage"),
            },
        )
        if record.get("returncode", 1) != 0 or record.get("failed"):
            failures += 1
        status["failed"] = failures
        status["completed"] = idx
        status["last_job"] = {
            "agent": agent_name,
            "env_config": env_config,
            "instrument": instrument,
            "trial": trial,
            "returncode": record.get("returncode"),
            "tokens": _token_brief(record.get("token_usage")),
        }
        status["updated_utc"] = datetime.now(timezone.utc).isoformat()
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    status["finished_utc"] = datetime.now(timezone.utc).isoformat()
    status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")

    print(
        f"\nFinished browser-setup grid. jobs={len(jobs)} failures={failures}\n"
        f"Results under: {exp_root}",
        flush=True,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
