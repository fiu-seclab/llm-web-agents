# From Puzzles to Profiles: Evaluating Solver Services and LLM Browser Agents Against Modern Bot Defenses

This repository contains the experiment configurations, agent wrappers, and
reported results for the paper above.

The study measures two classes of automated attacker against four widely
deployed Captcha and non-interactive verification systems:

- **Attackers:** seven commercial Captcha-solving services, and eight LLM-based
  browser agents across cloud, self-hosted, AI-browser, and browser-extension
  deployments.
- **Defenses:** hCaptcha (easy and hard), reCaptcha v2 (checkbox and
  invisible), reCaptcha v3 (score-based), and Cloudflare Turnstile (managed and
  invisible).

## Research Questions

1. **RQ1. Off-the-shelf effectiveness.** Where do current solver services and
   browser agents fail at the verification gate?
2. **RQ2. Isolating the environment signals.** Which control-path, browser, or
   profile property decides admission at non-interactive defenses?
3. **RQ3. Operational cost and longevity.** What operational costs and
   session-decay limits remain once that trust is replicated?

## Key Findings

- Solver services defeat the challenge-based defenses they support (58–100%
  success), but average 23% on reCaptcha v3.
- Off-the-shelf agents fail at the browser and session layer rather than at
  reasoning. Turnstile mainly checks browser authenticity and how input events
  are generated. Invisible reCaptcha v2 and reCaptcha v3 admit agents only from
  a Chrome profile signed into an established consumer Google account.
- With that profile supplied, reCaptcha v3 assigns the same high score
  regardless of which LLM drives the agent, or whether an LLM is used at all.
  The LLM's value is adapting to new sites without per-site scripting.

## Repository Layout

| Path | Contents |
|---|---|
| `third-party-services/` | Node.js pipeline that submits tasks to each solver service and verifies the returned tokens against the vendor's verification endpoint. |
| `llm-based-crawlers/` | Wrappers for the self-hosted agents (`browser-use-app`, `seeact-app`, `open-manus-app`, `skyvern-app`) and the screening runner `run_screening_experiments.py`. |
| `llm-based-crawlers/browser_setup/` | The RQ2 browser-configuration grid: one agent held fixed across instrumented, Chrome incognito, Chrome cold-profile, and Chrome full-profile launches. |
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

### 2. Solver-service evaluation (RQ1)

```bash
cd third-party-services
npm install
node index.js
```

Results are written to `third-party-services/database.db` (gitignored). The
solver and Captcha pairs that run are set by the mappings in `index.js`.

### 3. Agent evaluation (RQ1)

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

### 4. Browser-configuration grid (RQ2)

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
