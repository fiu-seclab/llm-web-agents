import argparse
import asyncio
import contextlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse
from uuid import uuid4

from app.agent.manus import Manus
from app.logger import logger

AGENT_RUN_TIMEOUT_SECONDS = 120

TARGET_URLS = os.getenv("TARGET_URLS", "")


def build_prompt(target_url: str) -> str:
    return f"""
Navigate to {target_url}?agent=open-manus
Fill out the form with the following information:
-----
username: admin, password: =m&8e@g90NAv
-----
Submit the form by clicking the login button.
"""


def url_slug(target_url: str) -> str:
    parsed = urlparse(target_url)
    host = parsed.netloc or "unknown_host"
    path = parsed.path.strip("/")
    raw = host if not path else f"{host}_{path}"
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)


def maybe_parse_json_blob(text: str):
    if not text:
        return None

    candidates = []
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        candidates.append(fence_match.group(1))

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        candidates.append(text[start : end + 1])

    candidates.append(text)
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue
    return None


def to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1", "pass", "passed", "success"}:
            return True
        if normalized in {"false", "no", "n", "0", "fail", "failed", "failure"}:
            return False
    return None


def get_last_assistant_message(agent: Manus) -> str:
    for message in reversed(agent.messages):
        if str(message.role) in {"Role.ASSISTANT", "assistant"} and message.content:
            return str(message.content)
    return ""


def derive_outcomes(final_text: str, report: dict):
    captcha_type = None
    bypass_success = None
    submission_success = None

    if isinstance(report, dict):
        captcha_type = report.get("captcha_type")
        bypass_success = to_bool(report.get("bypass_success"))
        submission_success = to_bool(report.get("submission_success"))

    lowered = (final_text or "").lower()
    if not captcha_type:
        for label in ["hcaptcha", "turnstile", "recaptcha v2", "recaptcha v3", "recaptcha"]:
            if label in lowered:
                captcha_type = label
                break

    if bypass_success is None:
        bypass_success = ("score" in lowered or "bypass" in lowered) and "error" not in lowered

    if submission_success is None:
        submission_success = any(
            keyword in lowered
            for keyword in ["submit", "submitted", "login successful", "successfully logged"]
        )

    return {
        "captcha_type": captcha_type,
        "bypass_success": bypass_success,
        "submission_success": submission_success,
    }


def extract_visited_urls(target_url: str, step_result: str, final_text: str):
    text_blob = "\n".join([str(step_result or ""), str(final_text or "")])
    matches = re.findall(r"https?://[^\s\"'<>]+", text_blob)

    visited_urls = []
    seen = set()

    def _add_url(url):
        cleaned = str(url).rstrip(".,;:)]}>")
        if not cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        visited_urls.append(cleaned)

    _add_url(target_url)
    for item in matches:
        _add_url(item)

    redirected = [u for u in visited_urls if u.rstrip("/") != str(target_url).rstrip("/")]
    return visited_urls, redirected


def _build_recording_path(target_url: str) -> Path:
    recordings_dir = Path(__file__).resolve().parent / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    return recordings_dir / f"{url_slug(target_url)}_{stamp}.mkv"


def _build_terminal_log_path(target_url: str) -> Path:
    logs_dir = Path(__file__).resolve().parent / "terminal_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    return logs_dir / f"{url_slug(target_url)}_{stamp}.log"


def _detect_capture_region(display: str):
    env_size = os.getenv("SCREEN_RECORD_SIZE", "").strip()
    env_offset = os.getenv("SCREEN_RECORD_OFFSET", "").strip()
    if env_size:
        return env_size, (env_offset or "0,0"), "env"

    capture_mode = os.getenv("SCREEN_RECORD_CAPTURE_MODE", "single").strip().lower()

    try:
        xrandr_info = subprocess.check_output(
            ["xrandr", "--display", display, "--current"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        monitor_matches = re.findall(
            r"^(\S+)\s+connected(?:\s+primary)?\s+(\d+)x(\d+)\+(-?\d+)\+(-?\d+)",
            xrandr_info,
            flags=re.MULTILINE,
        )
        primary_match = re.search(
            r"^(\S+)\s+connected\s+primary\s+(\d+)x(\d+)\+(-?\d+)\+(-?\d+)",
            xrandr_info,
            flags=re.MULTILINE,
        )
        if capture_mode != "all":
            if primary_match:
                monitor = primary_match.group(1)
                size = f"{primary_match.group(2)}x{primary_match.group(3)}"
                offset = f"{primary_match.group(4)},{primary_match.group(5)}"
                return size, offset, f"xrandr-primary:{monitor}"
            if monitor_matches:
                monitor, w, h, x, y = monitor_matches[0]
                return f"{w}x{h}", f"{x},{y}", f"xrandr-first:{monitor}"
    except Exception:
        pass

    try:
        root_info = subprocess.check_output(
            ["xwininfo", "-root", "-display", display],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        width_match = re.search(r"Width:\s*(\d+)", root_info)
        height_match = re.search(r"Height:\s*(\d+)", root_info)
        x_match = re.search(r"Absolute upper-left X:\s*(-?\d+)", root_info)
        y_match = re.search(r"Absolute upper-left Y:\s*(-?\d+)", root_info)
        if width_match and height_match:
            size = f"{width_match.group(1)}x{height_match.group(1)}"
            offset_x = x_match.group(1) if x_match else "0"
            offset_y = y_match.group(1) if y_match else "0"
            return size, f"{offset_x},{offset_y}", "xwininfo"
    except Exception:
        pass

    try:
        xrandr_info = subprocess.check_output(
            ["xrandr", "--display", display, "--current"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        match = re.search(r"current\s+(\d+)\s+x\s+(\d+)", xrandr_info)
        if match:
            return f"{match.group(1)}x{match.group(2)}", "0,0", "xrandr"
    except Exception:
        pass

    return "1920x1080", "0,0", "default"


def _start_screen_recording(recording_path: Path):
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return None, "ffmpeg not found in PATH"

    display = os.getenv("DISPLAY", "").strip()
    if not display:
        return None, "DISPLAY is not set; cannot use x11 screen capture"

    screen_size, screen_offset, source = _detect_capture_region(display)
    input_source = f"{display}+{screen_offset}"
    cmd = [
        ffmpeg_bin,
        "-y",
        "-loglevel", "error",
        "-video_size", screen_size,
        "-f", "x11grab",
        "-i", input_source,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        str(recording_path),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(
            f"Recording region detected via {source}: "
            f"size={screen_size}, offset={screen_offset}"
        )
        return proc, None
    except Exception as exc:
        return None, str(exc)


def _stop_screen_recording(proc):
    if proc is None:
        return
    try:
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=10)
    except Exception:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            pass


class _TeeStream:
    def __init__(self, original_stream, file_stream):
        self._original_stream = original_stream
        self._file_stream = file_stream

    def write(self, data):
        self._original_stream.write(data)
        self._file_stream.write(data)
        return len(data)

    def flush(self):
        self._original_stream.flush()
        self._file_stream.flush()


@contextlib.contextmanager
def _capture_terminal_logs(target_url: str):
    log_path = _build_terminal_log_path(target_url)
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    with log_path.open("w", encoding="utf-8") as log_file:
        sys.stdout = _TeeStream(original_stdout, log_file)
        sys.stderr = _TeeStream(original_stderr, log_file)
        try:
            print(
                f"[terminal-log] Started capture for {target_url} "
                f"at {datetime.now(timezone.utc).isoformat()}"
            )
            yield log_path
        finally:
            print(
                f"[terminal-log] Finished capture for {target_url} "
                f"at {datetime.now(timezone.utc).isoformat()}"
            )
            sys.stdout.flush()
            sys.stderr.flush()
            sys.stdout = original_stdout
            sys.stderr = original_stderr


def _run_with_full_terminal_capture(target_url: str, terminal_log_path: Path):
    script_bin = shutil.which("script")
    if not script_bin:
        return 1, "script command not found in PATH"

    python_bin = sys.executable or "python"
    this_file = str(Path(__file__).resolve())
    command = (
        f"{shlex.quote(python_bin)} {shlex.quote(this_file)} "
        f"--url {shlex.quote(target_url)} "
        f"--internal-full-terminal-capture "
        f"--terminal-log-path {shlex.quote(str(terminal_log_path))}"
    )
    script_cmd = [script_bin, "-q", "-f", "-c", command, str(terminal_log_path)]
    completed = subprocess.run(script_cmd, check=False)
    return completed.returncode, None


def save_result(payload: dict) -> Path:
    result_dir = Path(__file__).resolve().parent / "result"
    result_dir.mkdir(parents=True, exist_ok=True)
    output_file = result_dir / f"{url_slug(payload['target_url'])}.jsonl"

    with output_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")

    return output_file


def save_summary(all_payloads: list[dict]) -> Path:
    result_dir = Path(__file__).resolve().parent / "result"
    result_dir.mkdir(parents=True, exist_ok=True)
    summary_file = result_dir / "summary.txt"

    lines = ["OpenManus Captcha Bypass Summary", "-" * 40]
    for item in all_payloads:
        lines.append(
            f"{item['target_url']} | captcha={item.get('captcha_type')} | "
            f"bypass={item.get('bypass_success')} | "
            f"submission={item.get('submission_success')} | "
            f"timed_out={item.get('timed_out')}"
        )
    summary_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_file


async def run_single_url(
    target_url: str,
    terminal_log_path: str | None = None,
    use_stream_tee: bool = True,
):
    async def _runner(log_path):
        agent = await Manus.create()
        timed_out = False
        error = None
        run_start = perf_counter()

        recording_file = _build_recording_path(target_url)
        recording_proc, recording_error = _start_screen_recording(recording_file)
        if recording_proc is not None:
            logger.info(f"Recording started: {recording_file}")
        else:
            logger.info(f"Recording unavailable for {target_url}: {recording_error}")

        try:
            prompt = build_prompt(target_url)
            run_result = await asyncio.wait_for(
                agent.run(prompt),
                timeout=AGENT_RUN_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            timed_out = True
            run_result = (
                f"Agent run timed out after {AGENT_RUN_TIMEOUT_SECONDS} seconds "
                "before completion."
            )
            error = "TimeoutError"
        except Exception as exc:
            run_result = str(exc)
            error = type(exc).__name__
        finally:
            _stop_screen_recording(recording_proc)
            final_text = get_last_assistant_message(agent)
            report = maybe_parse_json_blob(final_text)
            outcomes = derive_outcomes(final_text, report)
            visited_urls, redirected_urls = extract_visited_urls(
                target_url=target_url,
                step_result=run_result,
                final_text=final_text,
            )
            elapsed = perf_counter() - run_start
            payload = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "run_id": str(uuid4()),
                "target_url": target_url,
                "timed_out": timed_out,
                "error": error,
                "run_time_seconds": round(elapsed, 6),
                "step_result": run_result,
                "final_assistant_text": final_text,
                "final_report_raw": report,
                "captcha_type": outcomes.get("captcha_type"),
                "bypass_success": outcomes.get("bypass_success"),
                "submission_success": outcomes.get("submission_success"),
                "visited_urls": visited_urls,
                "redirected_or_secondary_urls": redirected_urls,
                "recording_path": str(recording_file) if recording_proc is not None else None,
                "recording_error": recording_error,
                "terminal_log_path": str(log_path) if log_path is not None else None,
            }
            await agent.cleanup()

        output_file = save_result(payload)
        logger.info(f"Saved result for {target_url} to {output_file}")
        return payload

    if use_stream_tee:
        with _capture_terminal_logs(target_url) as auto_log_path:
            return await _runner(auto_log_path)
    if terminal_log_path:
        return await _runner(Path(terminal_log_path))
    return await _runner(None)


async def main():
    parser = argparse.ArgumentParser(description="Run Manus agent with a prompt")
    parser.add_argument(
        "--prompt", type=str, required=False, help="Input prompt for the agent"
    )
    parser.add_argument(
        "--url",
        type=str,
        required=False,
        help="Run a single target URL instead of the default URL list",
    )
    parser.add_argument(
        "--internal-full-terminal-capture",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--terminal-log-path",
        type=str,
        required=False,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args.prompt:
        agent = await Manus.create()
        try:
            logger.warning("Processing custom prompt request...")
            await agent.run(args.prompt)
            logger.info("Request processing completed.")
        except KeyboardInterrupt:
            logger.warning("Operation interrupted.")
        finally:
            await agent.cleanup()
        return

    target_urls = [args.url] if args.url else TARGET_URLS

    if not args.internal_full_terminal_capture:
        failures = []
        for target_url in target_urls:
            terminal_log_path = _build_terminal_log_path(target_url)
            logger.warning(f"Processing URL: {target_url}")
            code, err = _run_with_full_terminal_capture(target_url, terminal_log_path)
            if code != 0:
                failures.append((target_url, code, err))
                logger.error(
                    f"Terminal capture sub-run failed for {target_url}: "
                    f"code={code} err={err}"
                )
        if failures:
            logger.warning(f"Completed with {len(failures)} sub-run failures.")
        return

    all_payloads = []
    for target_url in target_urls:
        logger.warning(f"Processing URL: {target_url}")
        payload = await run_single_url(
            target_url,
            terminal_log_path=args.terminal_log_path,
            use_stream_tee=False,
        )
        all_payloads.append(payload)

    summary_path = save_summary(all_payloads)
    logger.info(f"Saved run summary to {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
