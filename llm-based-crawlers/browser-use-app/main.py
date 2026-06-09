import asyncio
import argparse
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

from browser_use import Agent, Browser
from browser_use.llm import ChatOllama, ChatOpenAI

AGENT_RUN_TIMEOUT_SECONDS = 600

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

TARGET_URLS = os.getenv("TARGET_URLS", "")

def _build_prompt(url):
    return f"""
Navigate to {url}?agent=browser-use
Fill out the form with the following information:
-----
username: admin, password: =m&8e@g90NAv
-----
Submit the form by clicking the login button.
"""

def _configure_human_actions():
    # HLISA-style defaults: human-like cadence with bounded randomness.
    # These are applied only when not already set in the environment.
    defaults = {
        "BROWSER_USE_HUMANIZE": "true",
        "BROWSER_USE_HUMAN_MOUSE_STEPS_MIN": "5",
        "BROWSER_USE_HUMAN_MOUSE_STEPS_MAX": "12",
        "BROWSER_USE_HUMAN_MOUSE_STEP_DELAY_MIN": "0.010",
        "BROWSER_USE_HUMAN_MOUSE_STEP_DELAY_MAX": "0.035",
        "BROWSER_USE_HUMAN_CLICK_HOLD_MIN": "0.080",
        "BROWSER_USE_HUMAN_CLICK_HOLD_MAX": "0.180",
        "BROWSER_USE_HUMAN_TYPE_DELAY_MIN": "0.050",
        "BROWSER_USE_HUMAN_TYPE_DELAY_MAX": "0.180",
        "BROWSER_USE_HUMAN_NEWLINE_DELAY_MIN": "0.080",
        "BROWSER_USE_HUMAN_NEWLINE_DELAY_MAX": "0.220",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)

    print(
        "Human-like actions enabled with profile:",
        {
            "enabled": os.getenv("BROWSER_USE_HUMANIZE"),
            "mouse_steps": (
                os.getenv("BROWSER_USE_HUMAN_MOUSE_STEPS_MIN"),
                os.getenv("BROWSER_USE_HUMAN_MOUSE_STEPS_MAX"),
            ),
            "type_delay": (
                os.getenv("BROWSER_USE_HUMAN_TYPE_DELAY_MIN"),
                os.getenv("BROWSER_USE_HUMAN_TYPE_DELAY_MAX"),
            ),
        },
    )


def _build_llm():
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY).strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

        model = os.getenv("OPENAI_MODEL", "o4-mini").strip()
        base_url = os.getenv("OPENAI_BASE_URL", "").strip()

        kwargs = {"model": model, "api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(**kwargs)

    if provider == "ollama":
        model = os.getenv("OLLAMA_MODEL", "llama3.3").strip()
        host = os.getenv("OLLAMA_HOST", "http://trustai4s.cis.fiu.edu:11444").strip()
        return ChatOllama(model=model, host=host)

    raise ValueError(
        f"Unsupported LLM_PROVIDER='{provider}'. Use 'openai' or 'ollama'."
    )


async def _get_token_usage(agent):
    if not hasattr(agent, "token_cost_service"):
        return {"available": False, "error": "Agent has no token_cost_service"}

    try:
        usage_summary = await agent.token_cost_service.get_usage_summary()
        by_model = {}
        for model, stats in usage_summary.by_model.items():
            by_model[model] = {
                "total_tokens": stats.total_tokens,
                "prompt_tokens": stats.prompt_tokens,
                "completion_tokens": stats.completion_tokens,
                "invocations": stats.invocations,
                "average_tokens_per_invocation": stats.average_tokens_per_invocation,
            }

        return {
            "available": True,
            "total_tokens": usage_summary.total_tokens,
            "total_prompt_tokens": usage_summary.total_prompt_tokens,
            "total_completion_tokens": usage_summary.total_completion_tokens,
            "total_cost": usage_summary.total_cost,
            "total_prompt_cost": usage_summary.total_prompt_cost,
            "total_completion_cost": usage_summary.total_completion_cost,
            "entry_count": usage_summary.entry_count,
            "by_model": by_model,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def _normalize_usage_object(usage):
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        try:
            return usage.model_dump()
        except Exception:
            return str(usage)
    if isinstance(usage, dict):
        return usage
    return str(usage)


def _to_jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:
            return str(value)
    if hasattr(value, "__dict__"):
        try:
            return _to_jsonable(vars(value))
        except Exception:
            return str(value)
    return str(value)


def _extract_triggered_events(history):
    if history is None:
        return []

    model_actions = []
    if hasattr(history, "model_actions"):
        try:
            model_actions = history.model_actions() or []
        except Exception:
            model_actions = []

    all_results = []
    if hasattr(history, "all_results"):
        try:
            all_results = history.all_results or []
        except Exception:
            all_results = []

    events = []
    event_count = max(len(model_actions), len(all_results))
    for i in range(event_count):
        action_raw = model_actions[i] if i < len(model_actions) else None
        result_raw = all_results[i] if i < len(all_results) else None

        action_dict = _to_jsonable(action_raw) if action_raw is not None else {}
        if not isinstance(action_dict, dict):
            action_dict = {"raw_action": action_dict}

        action_name = "unknown"
        action_payload = {}
        interacted_element = None
        for key, value in action_dict.items():
            if key == "interacted_element":
                interacted_element = value
                continue
            action_name = key
            action_payload = value
            break

        result_dict = _to_jsonable(result_raw) if result_raw is not None else {}
        if not isinstance(result_dict, dict):
            result_dict = {"raw_result": result_dict}

        events.append(
            {
                "step": i + 1,
                "action": action_name,
                "action_payload": _to_jsonable(action_payload),
                "interacted_element": _to_jsonable(interacted_element),
                "is_done": result_dict.get("is_done"),
                "success": result_dict.get("success"),
                "error": result_dict.get("error"),
                "extracted_content": result_dict.get("extracted_content"),
                "metadata": _to_jsonable(result_dict.get("metadata")),
            }
        )

    return events


def _extract_action_names(history):
    if history is None or not hasattr(history, "action_names"):
        return []
    try:
        return history.action_names() or []
    except Exception:
        return []


def _url_slug(target_url):
    parsed = urlparse(target_url)
    host = parsed.netloc or "unknown_host"
    path = parsed.path.strip("/")
    raw = host if not path else f"{host}_{path}"
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)


def _extract_final_text(history, result):
    if history is None:
        return str(result)

    final_result_attr = getattr(history, "final_result", None)
    if callable(final_result_attr):
        try:
            final_text = final_result_attr()
            if final_text:
                return str(final_text)
        except Exception:
            pass
    elif final_result_attr:
        return str(final_result_attr)

    return str(result)


def _extract_json_report(final_text):
    if not final_text:
        return None

    candidates = []
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", final_text, re.DOTALL)
    if fence_match:
        candidates.append(fence_match.group(1))

    start = final_text.find("{")
    end = final_text.rfind("}")
    if start != -1 and end != -1 and start < end:
        candidates.append(final_text[start : end + 1])

    candidates.append(final_text)

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue

    return None


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "y", "1", "pass", "passed", "success"}:
            return True
        if normalized in {"false", "no", "n", "0", "fail", "failed", "failure"}:
            return False
    return None


def _derive_run_outcomes(final_text, final_report, triggered_events):
    captcha_type = None
    bypass_success = None
    submission_success = None

    if isinstance(final_report, dict):
        captcha_type = final_report.get("captcha_type")
        bypass_success = _to_bool(final_report.get("bypass_success"))
        submission_success = _to_bool(final_report.get("submission_success"))

    lowered_text = (final_text or "").lower()
    if not captcha_type:
        for label in ["hcaptcha", "turnstile", "recaptcha v2", "recaptcha v3", "recaptcha"]:
            if label in lowered_text:
                captcha_type = label
                break

    if bypass_success is None:
        bypass_success = "score" in lowered_text and "error" not in lowered_text

    if submission_success is None:
        submission_success = any(
            event.get("is_done") is True and event.get("success") is True
            for event in triggered_events
        )

    return {
        "captcha_type": captcha_type,
        "bypass_success": bypass_success,
        "submission_success": submission_success,
    }


def _extract_visited_urls(target_url, final_text, triggered_events, result):
    text_chunks = [str(target_url or ""), str(final_text or ""), str(result or "")]
    if triggered_events:
        try:
            text_chunks.append(json.dumps(triggered_events, ensure_ascii=True))
        except Exception:
            text_chunks.append(str(triggered_events))

    text_blob = "\n".join(text_chunks)
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

    redirected_urls = [
        u for u in visited_urls if u.rstrip("/") != str(target_url).rstrip("/")
    ]
    return visited_urls, redirected_urls


def _build_recording_path(target_url):
    recordings_dir = Path(__file__).resolve().parent / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    return recordings_dir / f"{_url_slug(target_url)}_{stamp}.mkv"


def _build_terminal_log_path(target_url):
    logs_dir = Path(__file__).resolve().parent / "terminal_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    return logs_dir / f"{_url_slug(target_url)}_{stamp}.log"


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
def _capture_terminal_logs(target_url):
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


def _run_with_full_terminal_capture(target_url, terminal_log_path):
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


def _parse_args():
    parser = argparse.ArgumentParser(description="Run browser-use captcha agent")
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
    return parser.parse_args()


def _detect_capture_region(display):
    env_size = os.getenv("SCREEN_RECORD_SIZE", "").strip()
    env_offset = os.getenv("SCREEN_RECORD_OFFSET", "").strip()
    if env_size:
        return env_size, (env_offset or "0,0"), "env"

    capture_mode = os.getenv("SCREEN_RECORD_CAPTURE_MODE", "single").strip().lower()

    # Default: single display (prefer primary monitor).
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

    # Full virtual desktop mode.
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

    # Fallback: xrandr current virtual screen size.
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


def _start_screen_recording(recording_path):
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
        "-loglevel",
        "error",
        "-video_size",
        screen_size,
        "-f",
        "x11grab",
        "-i",
        input_source,
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        str(recording_path),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print(
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


def _save_run_cost(
    target_url,
    result,
    action_names,
    triggered_events,
    token_usage,
    history_usage,
    run_time_seconds,
    final_text,
    final_report,
    run_outcomes,
    visited_urls,
    redirected_urls,
    recording_path,
    recording_error,
    terminal_log_path,
    timed_out=False,
    error=None,
):
    result_dir = Path(__file__).resolve().parent / "result"
    result_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "run_id": str(uuid4()),
        "target_url": target_url,
        "action_names": action_names,
        "triggered_events": triggered_events,
        "token_usage": token_usage,
        "history_usage": _normalize_usage_object(history_usage),
        "final_report_raw": _to_jsonable(final_report),
        "final_text": final_text,
        "captcha_type": run_outcomes.get("captcha_type"),
        "bypass_success": run_outcomes.get("bypass_success"),
        "submission_success": run_outcomes.get("submission_success"),
        "visited_urls": visited_urls,
        "redirected_or_secondary_urls": redirected_urls,
        "recording_path": recording_path,
        "recording_error": recording_error,
        "terminal_log_path": terminal_log_path,
        "cost_found": bool(token_usage.get("total_cost")),
        "run_time_seconds": round(run_time_seconds, 6),
        "timed_out": timed_out,
        "error": error,
        "result_preview": str(result),
    }

    output_path = result_dir / f"{_url_slug(target_url)}.jsonl"
    with output_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")

    print(f"Saved run cost record to: {output_path}")
    return payload, output_path


async def _close_browser(browser):
    close_method = getattr(browser, "close", None)
    if not callable(close_method):
        return

    try:
        maybe_awaitable = close_method()
        if asyncio.iscoroutine(maybe_awaitable):
            await maybe_awaitable
    except Exception:
        pass


async def _run_for_url(target_url, llm, terminal_log_path=None, use_stream_tee=True):
    async def _runner(log_path):
        browser = Browser()
        agent = Agent(
            task=_build_prompt(target_url),
            browser=browser,
            llm=llm,
            calculate_cost=True,
        )

        run_start = perf_counter()
        timed_out = False
        error = None
        recording_file = _build_recording_path(target_url)
        recording_proc, recording_error = _start_screen_recording(recording_file)
        if recording_proc is not None:
            print(f"Recording started: {recording_file}")
        else:
            print(f"Recording unavailable for {target_url}: {recording_error}")

        try:
            history = await asyncio.wait_for(agent.run(), timeout=AGENT_RUN_TIMEOUT_SECONDS)
            result = history
        except asyncio.TimeoutError:
            timed_out = True
            history = None
            result = (
                f"Agent run timed out after {AGENT_RUN_TIMEOUT_SECONDS} seconds "
                "before completion."
            )
            error = "TimeoutError"
        finally:
            _stop_screen_recording(recording_proc)
            await _close_browser(browser)

        run_time_seconds = perf_counter() - run_start
        token_usage = await _get_token_usage(agent)
        history_usage = getattr(history, "usage", None) if history is not None else None
        action_names = _extract_action_names(history)
        triggered_events = _extract_triggered_events(history)
        final_text = _extract_final_text(history, result)
        final_report = _extract_json_report(final_text)
        run_outcomes = _derive_run_outcomes(final_text, final_report, triggered_events)
        visited_urls, redirected_urls = _extract_visited_urls(
            target_url=target_url,
            final_text=final_text,
            triggered_events=triggered_events,
            result=result,
        )

        payload, output_path = _save_run_cost(
            target_url=target_url,
            result=result,
            action_names=action_names,
            triggered_events=triggered_events,
            token_usage=token_usage,
            history_usage=history_usage,
            run_time_seconds=run_time_seconds,
            final_text=final_text,
            final_report=final_report,
            run_outcomes=run_outcomes,
            visited_urls=visited_urls,
            redirected_urls=redirected_urls,
            recording_path=str(recording_file) if recording_proc is not None else None,
            recording_error=recording_error,
            terminal_log_path=str(log_path) if log_path is not None else None,
            timed_out=timed_out,
            error=error,
        )

        print(f"URL: {target_url}")
        print(f"Actions captured: {len(action_names)}")
        print(f"Triggered events: {len(triggered_events)}")
        print(f"Captcha type: {run_outcomes.get('captcha_type')}")
        print(f"Bypass success: {run_outcomes.get('bypass_success')}")
        print(f"Submission success: {run_outcomes.get('submission_success')}")
        print(f"Visited URLs: {visited_urls}")
        print(f"Usage summary: {token_usage}")
        print(f"Saved to: {output_path}")
        print(f"Terminal log saved to: {log_path}")

        return payload

    if use_stream_tee:
        with _capture_terminal_logs(target_url) as auto_log_path:
            return await _runner(auto_log_path)
    if terminal_log_path:
        return await _runner(Path(terminal_log_path))
    return await _runner(None)


async def main():
    # _configure_human_actions()
    args = _parse_args()
    target_urls = [args.url] if args.url else TARGET_URLS

    if not args.internal_full_terminal_capture:
        failures = []
        for target_url in target_urls:
            terminal_log_path = _build_terminal_log_path(target_url)
            print(f"\n=== Running agent for {target_url} ===")
            code, err = _run_with_full_terminal_capture(target_url, terminal_log_path)
            if code != 0:
                failures.append((target_url, code, err))
                print(f"Terminal capture sub-run failed for {target_url}: code={code} err={err}")
        if failures:
            print(f"Completed with {len(failures)} sub-run failures.")
        return

    llm = _build_llm()
    all_payloads = []

    for target_url in target_urls:
        print(f"\n=== Running agent for {target_url} ===")
        payload = await _run_for_url(
            target_url,
            llm,
            terminal_log_path=args.terminal_log_path,
            use_stream_tee=False,
        )
        all_payloads.append(payload)

    print("\n=== Run summary ===")
    for payload in all_payloads:
        print(
            f"{payload['target_url']} | captcha={payload.get('captcha_type')} | "
            f"bypass={payload.get('bypass_success')} | "
            f"submission={payload.get('submission_success')} | "
            f"timed_out={payload.get('timed_out')}"
        )

asyncio.run(main())
