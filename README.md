# Covert Clicks and Intelligent Crawls

This repository contains the experimental artifacts and code used in our research on modern anti-bot defenses against autonomous web agents.

The project evaluates how commercial Captcha-solving services and LLM-based browser agents perform against challenge-based and non-interactive bot defenses, including:

- hCaptcha (easy and hard)
- reCaptcha v2 (checkbox and invisible)
- reCaptcha v3 (score-based, non-interactive)
- Cloudflare Turnstile (managed and invisible/non-interactive)

## Research Scope

The study investigates three core questions:

1. How effective are third-party solver services across deployed defenses?
2. How effective are off-the-shelf LLM browser agents in default configurations?
3. Can targeted browser-authenticity and interaction-layer modifications bypass non-interactive systems (especially reCaptcha v3)?

High-level findings reflected in this codebase:

- Challenge-based systems are often bypassed reliably and cheaply via commercial solver APIs.
- Off-the-shelf browser agents commonly fail on non-interactive defenses due to environment trust signals, not task-reasoning limits.
- With authenticity-preserving execution and human-like interaction modules, bypass rates for reCaptcha v3 can increase substantially.

## Repository Layout

- `third-party-services/`  
  Node.js pipeline for evaluating commercial solver services and verifying returned tokens against vendor verification endpoints.

- `llm-based-crawlers/`  
  Agent implementations and integrations used in experiments (including `browser-use-app`, `seeact-app`, and `open-manus-app` variants).

- `artifacts/`  
  Collected outputs and experiment artifacts. Recordings are available for the experiments but are not included in this repository because they cannot be deanonymized while preserving anonymized submission requirements.

## Quick Start

### 1) Clone and configure

```bash
git clone <your-fork-or-repo-url>
cd llm-web-agents
```

Create and populate secrets/config files as needed (for example, solver API keys and Captcha verification secrets):

- `third-party-services/constants.js` (copy from `third-party-services/constants.js.example`)
- Agent-specific API_KEYS environment variables

### 2) Third-party solver evaluation

```bash
cd third-party-services
npm install
node index.js
```

Notes:

- The pipeline stores results in `third-party-services/database.db`.
- Solver x Captcha combinations are constrained by the mappings in `index.js`.
- Tokens are validated via provider verification APIs where configured.

### 3) LLM-agent evaluation

Each agent folder has its own setup requirements. Typical flow:

```bash
cd llm-based-crawlers/browser-use-app
uv sync
export OPENAI_API_KEY="..."
uv run python main.py
```

Likewise for:

- `llm-based-crawlers/seeact-app`
- `llm-based-crawlers/open-manus-app/OpenManus` (uses its own upstream-style setup)
- Skyvern was evaluated using a cloned copy of the official repository and executed with Docker, following the setup recommended by the Skyvern team: [https://github.com/Skyvern-AI/skyvern](https://github.com/Skyvern-AI/skyvern)
- BrowserOS repository: [https://github.com/browseros-ai/BrowserOS](https://github.com/browseros-ai/BrowserOS)
- NanoBrowser repository: [https://github.com/nanobrowser/nanobrowser](https://github.com/nanobrowser/nanobrowser)
- Comet: no official public source repository was used in this study; official product page: [https://www.perplexity.ai/comet](https://www.perplexity.ai/comet).

Outputs are usually written under each agent directory (`result/`, `recordings/`, and logs, depending on the app).



## Safety and Ethics

This repository is intended for defensive security research and measurement.

- Do not run experiments against systems you do not own or have explicit permission to test.
- Follow responsible disclosure practices for real-world deployment issues.