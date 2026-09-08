#!/usr/bin/env python3
"""Summarize environment-grid results and emit LaTeX rows.

A cell is Y if the majority of finished trials are an admission
(silent_admit for v2-invis, admitted for Turnstile); otherwise N.
Unknown / crashed trials are reported separately and do not vote.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CRAWLERS = ROOT.parent

ENV_CONFIGS = ("instrumented", "chrome_incognito", "chrome_cold", "chrome_full")
INSTRUMENTS = ("v2-invis", "turnstile", "turnstile-invis", "v3f")
AGENT_LATEX = {
    "browser-use": "Browser-Use",
    "open-manus": "OpenManus",
    "seeact": "SeeAct",
    "skyvern": "Skyvern",
    "nanobrowser": "NanoBrowser",
}
ADMIT = {
    "v2-invis": {"silent_admit"},
    "turnstile": {"admitted"},
    "turnstile-invis": {"admitted"},
    "v3f": {"admitted"},
}
REJECT = {
    "v2-invis": {"grid_raised"},
    "turnstile": {"rejected"},
    "turnstile-invis": {"rejected"},
    "v3f": {"rejected"},
}


def load_records(exp_root: Path) -> list[dict]:
    master = exp_root / "master_run_log.jsonl"
    if not master.exists():
        raise SystemExit(f"No master_run_log.jsonl under {exp_root}")
    records = []
    for line in master.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        records.append(json.loads(line))
    return records


def cell_mark(instrument: str, verdicts: list[str]) -> tuple[str, str]:
    counted = [v for v in verdicts if v and v != "unknown"]
    if not counted:
        return "", "no finished verdicts"
    admits = sum(1 for v in counted if v in ADMIT[instrument])
    rejects = sum(1 for v in counted if v in REJECT[instrument])
    n = len(counted)
    if admits > rejects:
        mark = r"\envY"
        note = f"{admits}/{n} admit"
    elif rejects > admits:
        mark = r"\envN"
        note = f"{rejects}/{n} reject"
    else:
        mark = ""
        note = f"tie admit={admits} reject={rejects} n={n}"
    return mark, note


def latex_row(agent: str, cells: dict) -> str:
    present = {key[1] for key in cells if cells[key]["n"]}
    if present == {"turnstile-invis"}:
        marks = [
            (cells[(env, "turnstile-invis")]["mark"] or "")
            for env in ENV_CONFIGS
        ]
        label = AGENT_LATEX.get(agent, agent)
        return (
            f"{label} (t-invis)\n"
            f"  & {marks[0]} & {marks[1]} & {marks[2]} & {marks[3]} \\\\"
        )
    if present == {"v3f"}:
        marks = [
            (cells[(env, "v3f")]["mark"] or "")
            for env in ENV_CONFIGS
        ]
        label = AGENT_LATEX.get(agent, agent)
        return (
            f"{label} (v3f)\n"
            f"  & {marks[0]} & {marks[1]} & {marks[2]} & {marks[3]} \\\\"
        )
    latex_cells = []
    for env_config in ENV_CONFIGS:
        v2 = cells[(env_config, "v2-invis")]["mark"]
        ts = cells[(env_config, "turnstile")]["mark"]
        latex_cells.extend([v2 or "", ts or ""])
    label = AGENT_LATEX.get(agent, agent)
    return (
        f"{label}\n"
        f"  & {latex_cells[0]} & {latex_cells[1]}\n"
        f"  & {latex_cells[2]} & {latex_cells[3]}\n"
        f"  & {latex_cells[4]} & {latex_cells[5]}\n"
        f"  & {latex_cells[6]} & {latex_cells[7]} \\\\"
    )


def summarize(exp_root: Path) -> dict:
    records = load_records(exp_root)
    by_agent: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        by_agent[rec.get("agent") or "unknown"].append(rec)

    all_cells = {}
    latex_rows = []
    print(f"Environment grid  ({exp_root})")
    for agent in sorted(by_agent):
        grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for rec in by_agent[agent]:
            grouped[(rec.get("env_config"), rec.get("instrument"))].append(rec)

        cells = {}
        print(f"\n[{agent}]")
        print(f"{'config':<20} {'instrument':<12} {'verdicts':<40} mark")
        print("-" * 90)
        for env_config in ENV_CONFIGS:
            for instrument in INSTRUMENTS:
                recs = grouped.get((env_config, instrument), [])
                verdicts = [r.get("env_verdict") or "unknown" for r in recs]
                mark, note = cell_mark(instrument, verdicts)
                counts = dict(Counter(verdicts))
                cells[(env_config, instrument)] = {
                    "mark": mark,
                    "note": note,
                    "counts": counts,
                    "n": len(recs),
                }
                print(
                    f"{env_config:<20} {instrument:<12} {str(counts):<40} "
                    f"{mark or '--'} ({note})"
                )
        row = latex_row(agent, cells)
        latex_rows.append(row)
        all_cells[agent] = {f"{k[0]}|{k[1]}": v for k, v in cells.items()}
        print("\nLaTeX row\n")
        print(row)
        print()

    out = {
        "experiment_root": str(exp_root),
        "agents": all_cells,
        "latex_rows": latex_rows,
    }
    out_path = exp_root / "grid_summary.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    (exp_root / "grid_row.tex").write_text("\n\n".join(latex_rows) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Wrote {exp_root / 'grid_row.tex'}")
    return out


def latest_exp_root() -> Path:
    runs = CRAWLERS / "experiment_runs"
    candidates = sorted(runs.glob("browser_setup_*"), reverse=True)
    if not candidates:
        raise SystemExit(f"No browser_setup_* directories under {runs}")
    return candidates[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exp-root", default="", help="experiment_runs/browser_setup_* dir")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    exp_root = Path(args.exp_root).resolve() if args.exp_root else latest_exp_root()
    summarize(exp_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
