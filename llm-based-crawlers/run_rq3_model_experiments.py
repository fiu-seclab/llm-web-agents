#!/usr/bin/env python3
"""Run the RQ3 model/input-mode matrix on the full Chrome profile."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
GRID_RUNNER = ROOT / "browser_setup" / "run.py"
NOVITA_BASE_URL = "https://api.novita.ai/openai"

CONDITIONS = {
    "gpt-5.6-luna-vision": {
        "model": "gpt-5.6-luna",
        "provider": "openai",
        "vision": True,
    },
    "gpt-5.4-mini-vision": {
        "model": "gpt-5.4-mini",
        "provider": "openai",
        "vision": True,
    },
    "gpt-4o-mini-vision": {
        "model": "gpt-4o-mini",
        "provider": "openai",
        "vision": True,
    },
    "glm-5.3-flash-vision": {
        "model": "zai-org/glm-5.3-flash",
        "provider": "novita",
        "vision": True,
    },
    "deepseek-v4.1-flash-dom": {
        "model": "deepseek/deepseek-v4.1-flash",
        "provider": "novita",
        "vision": False,
    },
    "gpt-5.6-luna-dom": {
        "model": "gpt-5.6-luna",
        "provider": "openai",
        "vision": False,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value:
        return value
    for path in (
        ROOT / "skyvern-app" / ".env",
        ROOT / "browser-use-app" / ".env",
    ):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        match = re.search(rf"(?m)^\s*{re.escape(name)}\s*=\s*(.+?)\s*$", text)
        if match:
            return match.group(1).strip().strip('"').strip("'")
    raise SystemExit(f"{name} is not set in the environment or either app .env")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--conditions",
        nargs="+",
        choices=list(CONDITIONS),
        default=list(CONDITIONS),
    )
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--smoke", action="store_true", help="Run one trial per cell")
    parser.add_argument(
        "--agents",
        nargs="+",
        choices=("skyvern", "browser-use"),
        default=["skyvern", "browser-use"],
    )
    parser.add_argument("--exp-root", default="")
    parser.add_argument("--job-seconds", type=int, default=180)
    parser.add_argument("--full-profile", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trials = 1 if args.smoke else args.trials
    exp_root = (
        Path(args.exp_root).expanduser().resolve()
        if args.exp_root
        else ROOT / "experiment_runs" / f"rq3_models_{utc_now()}"
    )
    exp_root.mkdir(parents=True, exist_ok=True)

    openai_key = load_secret("OPENAI_API_KEY")
    novita_key = load_secret("NOVITA_API_KEY")
    manifest = {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "trials_per_agent_cell": trials,
        "agents": args.agents,
        "conditions": {name: CONDITIONS[name] for name in args.conditions},
        "cells": [],
    }
    manifest_path = exp_root / "manifest.json"
    failures = 0

    for name in args.conditions:
        config = CONDITIONS[name]
        cell_root = exp_root / name
        env = os.environ.copy()
        env["OPENAI_API_KEY"] = (
            novita_key if config["provider"] == "novita" else openai_key
        )
        if config["provider"] == "novita":
            env["OPENAI_BASE_URL"] = NOVITA_BASE_URL
        else:
            env.pop("OPENAI_BASE_URL", None)
        env["OPENAI_MODEL"] = config["model"]
        env["SKYVERN_MODEL"] = config["model"]
        env["LLM_KEY"] = (
            "OPENAI_GPT5_6_LUNA"
            if config["model"] == "gpt-5.6-luna"
            else "OPENAI_GPT4O"
        )
        env["AGENT_USE_VISION"] = "true" if config["vision"] else "false"
        env["JOB_SECONDS"] = str(args.job_seconds)

        cmd = [
            sys.executable,
            str(GRID_RUNNER),
            "--exp-root",
            str(cell_root),
            "--agents",
            *args.agents,
            "--configs",
            "chrome_full",
            "--instruments",
            "v3f",
            "--trials",
            str(trials),
        ]
        if args.full_profile:
            cmd.extend(["--full-profile", args.full_profile])

        print(
            f"\n===== {name}: model={config['model']} "
            f"mode={'vision+dom' if config['vision'] else 'dom-only'} =====",
            flush=True,
        )
        completed = subprocess.run(cmd, cwd=str(GRID_RUNNER.parent), env=env)
        cell = {
            "condition": name,
            **config,
            "input_mode": "vision+dom" if config["vision"] else "dom-only",
            "trials_per_agent": trials,
            "returncode": completed.returncode,
            "artifacts": str(cell_root),
        }
        manifest["cells"].append(cell)
        if completed.returncode:
            failures += 1
        manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["failed_conditions"] = failures
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"\nRQ3 matrix finished: {exp_root} failures={failures}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
