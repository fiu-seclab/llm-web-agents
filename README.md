# From Puzzles to Profiles: Evaluating Solver Services and LLM Browser Agents Against Modern Bot Defenses

This repository contains the experiment configurations, agent wrappers, and
reported results for the paper above.

The experiments cover seven commercial Captcha-solving services and eight
LLM-based browser agents (cloud, self-hosted, AI-browser, and
browser-extension deployments) against hCaptcha, reCaptcha v2, reCaptcha v3,
and Cloudflare Turnstile, in both their challenge-based and non-interactive
configurations.

## Repository Layout

| Path | Contents |
|---|---|
| `third-party-services/` | Node.js pipeline that submits tasks to each solver service and verifies the returned tokens against the vendor's verification endpoint. |
| `llm-based-crawlers/` | Wrappers for the self-hosted agents (`browser-use-app`, `seeact-app`, `open-manus-app`, `skyvern-app`) and the screening runner `run_screening_experiments.py`. |
| `llm-based-crawlers/browser_setup/` | Browser-configuration grid: one agent held fixed across instrumented, Chrome incognito, Chrome cold-profile, and Chrome full-profile launches. |
| `paper-tables/` | The results reported in the paper's tables and figures, as CSV. See `paper-tables/README.md`. |

The cloud agents, AI browsers, and extension agent are third-party products
and have no code here:
[BrowserOS](https://github.com/browseros-ai/BrowserOS),
[NanoBrowser](https://github.com/nanobrowser/nanobrowser), and
[Comet](https://www.perplexity.ai/comet) (no public source).

## What Is Not Included

To reduce misuse risk while coordinated disclosure is in progress, this
snapshot excludes:

- Chrome profiles, cookies, and other session state
- profile-transfer and target-specific automation recipes
- live site keys and the testbed's real hostnames
- screen recordings and per-trial logs, which cannot be released without
  deanonymizing the submission

Default target hosts are placeholders (`*.example.test`). Point them at a
testbed you own or have permission to test.

## Quick Start

### 1. Configure

```bash
git clone <anonymous-repo-url>
cd llm-web-agents
```

Create these locally and do not commit them:

- `third-party-services/constants.js`, copied from
  `third-party-services/constants.js.example`
- `OPENAI_API_KEY` in the environment or in each agent's `.env` file

### 2. Solver-service evaluation

```bash
cd third-party-services
npm install
node index.js
```

Results are written to `third-party-services/database.db` (gitignored). The
solver and Captcha pairs that run are set by the mappings in `index.js`.

### 3. Agent evaluation

```bash
cd llm-based-crawlers/browser-use-app
uv sync
export OPENAI_API_KEY="..."
uv run python main.py --url https://v3f.example.test/
```

The other wrappers follow the same pattern: `seeact-app`,
`open-manus-app/OpenManus`, and `skyvern-app` (Skyvern is installed from PyPI).

To run several trials per agent and defense:

```bash
cd llm-based-crawlers
python run_screening_experiments.py --trials 1 --smoke
```

### 4. Browser-configuration grid

```bash
cd llm-based-crawlers/browser_setup
python run.py --smoke
```

See `llm-based-crawlers/browser_setup/README.md` for how each Chrome
configuration is launched.

## Safety and Ethics

This repository is intended for defensive security research and measurement.

- Do not run experiments against systems you do not own or have explicit
  permission to test.
- Follow responsible disclosure practices for real-world deployment issues.
  The reCaptcha findings were reported to Google before publication.
