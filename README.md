# From Puzzles to Profiles: A Cross-Stack Study of Solver Services and LLM Browser Agents Against Bot Management Systems

This repository contains the experimental configuration and supporting code
used in our research on modern anti-bot defenses against autonomous web agents.

The project evaluates how commercial Captcha-solving services and LLM-based
browser agents perform against challenge-based and non-interactive bot
defenses, including:

- hCaptcha (easy and hard)
- reCaptcha v2 (checkbox and invisible)
- reCaptcha v3 (score-based, non-interactive)
- Cloudflare Turnstile (managed and invisible/non-interactive)

To reduce misuse risk, this snapshot excludes exploit-ready target recipes,
live site keys, Chrome profiles, and screen recordings.

## Research Scope

The study investigates three core questions:

1. How effective are third-party solver services across deployed defenses?
2. How effective are off-the-shelf LLM browser agents in default configurations?
3. Can targeted browser-authenticity and interaction-layer modifications bypass
   non-interactive systems (especially reCaptcha v3)?

## Repository Layout

- `third-party-services/`
  Node.js pipeline for evaluating commercial solver services and verifying
  returned tokens against vendor verification endpoints.
- `llm-based-crawlers/`
  Agent wrappers used in the experiments (`browser-use-app`, `seeact-app`,
  `open-manus-app`, `skyvern-app`) plus the screening runner and the
  browser-configuration grid (`browser_setup/`).

Default target hosts in the runners are placeholders (`*.example.test`).
Point them at a testbed you own or have permission to test.

Recordings and browser profiles are not included: they cannot be released
without deanonymizing the submission.

## Quick Start

### 1) Configure

```bash
git clone <anonymous-repo-url>
cd llm-web-agents
```

Create and populate secrets/config files locally (do not commit them):

- `third-party-services/constants.js` (copy from `third-party-services/constants.js.example`)
- Agent-specific `OPENAI_API_KEY` / `.env` files

### 2) Third-party solver evaluation

```bash
cd third-party-services
npm install
node index.js
```

- Results are stored in `third-party-services/database.db` (gitignored).
- Solver × Captcha combinations are constrained by the mappings in `index.js`.
- Tokens are validated via provider verification APIs where configured.

### 3) LLM-agent evaluation

```bash
cd llm-based-crawlers/browser-use-app
uv sync
export OPENAI_API_KEY="..."
uv run python main.py --url https://v3f.example.test/
```

Likewise for:

- `llm-based-crawlers/seeact-app`
- `llm-based-crawlers/open-manus-app/OpenManus`
- `llm-based-crawlers/skyvern-app` (wrapper; Skyvern is installed from PyPI)
- BrowserOS: https://github.com/browseros-ai/BrowserOS
- NanoBrowser: https://github.com/nanobrowser/nanobrowser
- Comet: no official public source repository was used; product page:
  https://www.perplexity.ai/comet

Screening (several trials per agent–defense pair):

```bash
cd llm-based-crawlers
python run_screening_experiments.py --trials 1 --smoke
```

Browser-environment grid:

```bash
cd llm-based-crawlers/browser_setup
python run.py --smoke
```

See `llm-based-crawlers/browser_setup/README.md` for the Chrome
incognito / guest / persistent-profile configurations.

## Safety and Ethics

This repository is intended for defensive security research and measurement.

- Do not run experiments against systems you do not own or have explicit
  permission to test.
- Follow responsible disclosure practices for real-world deployment issues.
