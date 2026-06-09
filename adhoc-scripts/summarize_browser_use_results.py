#!/usr/bin/env python3
import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "browser-use-app" / "result"


def _parse_timestamp(value):
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def _read_records(results_dir):
    records = []
    if not results_dir.exists():
        return records

    for path in sorted(results_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)

    for path in sorted(results_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)

    return records


def _normalize_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1", "success", "passed"}:
            return True
        if lowered in {"false", "no", "n", "0", "failure", "failed"}:
            return False
    return None


def _detect_captcha(record):
    explicit = record.get("captcha_type")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    haystack = " ".join(
        str(record.get(k, ""))
        for k in ("final_text", "result_preview", "action_names", "triggered_events")
    ).lower()
    if "hcaptcha" in haystack:
        return "hcaptcha"
    if "turnstile" in haystack:
        return "turnstile"
    if "recaptcha v2" in haystack:
        return "recaptcha v2"
    if "recaptcha v3" in haystack:
        return "recaptcha v3"
    if "recaptcha" in haystack:
        return "recaptcha"
    return "unknown"


def _extract_tokens(record):
    usage = record.get("token_usage")
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if isinstance(total, (int, float)):
            return int(total)
    return 0


def _extract_cost(record):
    usage = record.get("token_usage")
    if isinstance(usage, dict):
        total = usage.get("total_cost")
        if isinstance(total, (int, float)):
            return float(total)
    return 0.0


def _extract_visited_urls(record):
    explicit_urls = record.get("visited_urls")
    if isinstance(explicit_urls, list):
        ordered_unique = []
        seen = set()
        for item in explicit_urls:
            cleaned = str(item).rstrip(".,;:)]}>")
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            ordered_unique.append(cleaned)
        if ordered_unique:
            return ordered_unique

    text_parts = []
    for key in (
        "final_text",
        "result_preview",
        "step_result",
        "final_assistant_text",
        "triggered_events",
        "action_names",
    ):
        value = record.get(key)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            text_parts.append(json.dumps(value, ensure_ascii=True))
        else:
            text_parts.append(str(value))

    text = "\n".join(text_parts)
    matches = re.findall(r"https?://[^\s\"'<>]+", text)

    ordered_unique = []
    seen = set()
    for match in matches:
        cleaned = match.rstrip(".,;:)]}>")
        if not cleaned:
            continue
        if cleaned not in seen:
            seen.add(cleaned)
            ordered_unique.append(cleaned)

    return ordered_unique


def _build_summary(records, max_observed_chars=0):
    if not records:
        return (
            "No Browser-Use records found.\n"
            "Tip: pass --results-dir if your files are in another folder.\n"
        )

    latest_by_url = {}
    for record in records:
        url = str(record.get("target_url", "unknown"))
        if url not in latest_by_url:
            latest_by_url[url] = record
            continue
        current_ts = _parse_timestamp(str(record.get("timestamp_utc", "")))
        prev_ts = _parse_timestamp(str(latest_by_url[url].get("timestamp_utc", "")))
        if current_ts >= prev_ts:
            latest_by_url[url] = record

    ordered = sorted(latest_by_url.values(), key=lambda r: str(r.get("target_url", "")))
    captcha_counter = Counter()
    bypass_success_count = 0
    submission_success_count = 0
    timeout_count = 0
    total_runtime = 0.0
    total_tokens = 0
    total_cost = 0.0

    urls = [str(record.get("target_url", "unknown")) for record in ordered]
    lines = [
        "Browser-Use Results Summary",
        "=" * 80,
        "URLs covered:",
    ]
    for url in urls:
        lines.append("- " + url)
    lines.extend(["", "Per-URL latest results:", ""])

    for record in ordered:
        url = str(record.get("target_url", "unknown"))
        captcha = _detect_captcha(record)
        bypass = _normalize_bool(record.get("bypass_success"))
        submission = _normalize_bool(record.get("submission_success"))
        timed_out = bool(record.get("timed_out", False))
        runtime = float(record.get("run_time_seconds", 0.0) or 0.0)
        tokens = _extract_tokens(record)
        cost = _extract_cost(record)
        visited_urls = _extract_visited_urls(record)
        redirected_urls = [
            u for u in visited_urls if u.rstrip("/") != url.rstrip("/")
        ]
        observed = str(record.get("final_text") or record.get("result_preview") or "")
        observed = re.sub(r"\s+", " ", observed).strip()
        if isinstance(max_observed_chars, int) and max_observed_chars > 0:
            if len(observed) > max_observed_chars:
                observed = observed[: max_observed_chars - 3] + "..."

        lines.append("URL: " + url)
        lines.append("  captcha: " + str(captcha))
        lines.append("  bypass_success: " + str(bypass))
        lines.append("  submission_success: " + str(submission))
        lines.append("  timed_out: " + str(timed_out))
        lines.append("  runtime_s: " + format(runtime, ".3f"))
        lines.append("  tokens: " + str(tokens))
        lines.append("  cost_usd: " + format(cost, ".6f"))
        lines.append("  recording_path: " + str(record.get("recording_path") or "(not saved)"))
        if record.get("recording_error"):
            lines.append("  recording_error: " + str(record.get("recording_error")))
        lines.append(
            "  terminal_log_path: " + str(record.get("terminal_log_path") or "(not saved)")
        )
        lines.append(
            "  visited_urls: "
            + (", ".join(visited_urls) if visited_urls else "(none detected)")
        )
        lines.append(
            "  redirected_or_secondary_urls: "
            + (
                ", ".join(redirected_urls)
                if redirected_urls
                else "(none detected)"
            )
        )
        if observed:
            lines.append(f"  observed: {observed}")
        lines.append("")

        captcha_counter[captcha] += 1
        if bypass is True:
            bypass_success_count += 1
        if submission is True:
            submission_success_count += 1
        if timed_out:
            timeout_count += 1
        total_runtime += runtime
        total_tokens += tokens
        total_cost += cost

    lines.extend(
        [
            "",
            "Totals (latest run per URL):",
            f"- urls={len(ordered)}",
            f"- bypass_success={bypass_success_count}",
            f"- submission_success={submission_success_count}",
            f"- timed_out={timeout_count}",
            f"- runtime_total_s={total_runtime:.3f}",
            f"- tokens_total={total_tokens}",
            f"- cost_total_usd={total_cost:.6f}",
            f"- captcha_counts={dict(captcha_counter)}",
            "",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Summarize Browser-Use captcha run results"
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Directory containing Browser-Use JSON/JSONL result files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "summary_report.txt",
        help="Path to write summary report",
    )
    parser.add_argument(
        "--max-observed-chars",
        type=int,
        default=0,
        help="Optional max length for observed text (0 means no trimming)",
    )
    args = parser.parse_args()

    records = _read_records(args.results_dir)
    summary = _build_summary(records, max_observed_chars=args.max_observed_chars)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(summary, encoding="utf-8")
    print(f"Browser-Use summary written to: {args.output}")


if __name__ == "__main__":
    main()
