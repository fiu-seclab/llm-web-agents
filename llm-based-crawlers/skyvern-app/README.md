# Skyvern local pipeline

Experiment wrapper around the official [Skyvern](https://github.com/Skyvern-AI/skyvern)
repository. It matches the browser-use / SeeAct / OpenManus contract: `--url`,
artifact directories, screen recording, and CDP attach.

Install Skyvern from PyPI (`skyvern[local]`) via `uv sync`. A local clone of
upstream is not required for this wrapper.

## Setup

```bash
cd llm-based-crawlers/skyvern-app
uv sync
uv run playwright install chromium
cp .env.example .env
# set OPENAI_API_KEY in .env
```

## Usage

```bash
export OPENAI_API_KEY="..."
uv run python main.py --url https://v3f.example.test/
```

Screening runner:

```bash
cd llm-based-crawlers
python run_screening_experiments.py --agents skyvern --trials 1 --smoke
```

Browser-setup grid (attaches to launched Chrome over CDP):

```bash
cd llm-based-crawlers/browser_setup
python run.py --agents skyvern --configs chrome_full --instruments v3f --trials 1
```

Point `--url` / `TARGET_URLS` at a testbed you operate. Default hosts in this
repository are placeholders (`*.example.test`).

## Artifacts

When `EXPERIMENT_ARTIFACTS_DIR` is set (screening / grid), results go there.
Otherwise they are written next to this app:

- `result/` — per-run JSON plus a URL-level JSONL
- `recordings/` — ffmpeg X11 capture
- `terminal_logs/` — full terminal capture via `script`

## Environment

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Required |
| `LLM_KEY` | Skyvern model key (default `OPENAI_GPT4O`) |
| `SKYVERN_MODEL` | LiteLLM model name (default `gpt-4o`) |
| `SKYVERN_RUN_TIMEOUT_SECONDS` | Screening timeout (default `600`; grid runs use 60s) |
| `EXPERIMENT_ARTIFACTS_DIR` | Artifact root from the experiment runners |
| `BROWSER_USE_CDP_URL` | Attach to an existing Chrome |
| `ENV_CONFIG` / `INSTRUMENT` | Browser configuration and defense labels |

Set `SKYVERN_TELEMETRY=false` to disable Skyvern usage telemetry (already in `.env.example`).

## Upstream

- Repository: https://github.com/Skyvern-AI/skyvern
