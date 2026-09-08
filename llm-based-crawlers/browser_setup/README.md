# Browser environment grid

Hold one agent fixed and vary only the browser, matching the paper's
environment-layer decomposition.

| config | what is launched | how the agent attaches |
|---|---|---|
| `instrumented` | nothing; the agent's bundled Chromium | default runtime |
| `chrome_incognito` | real `google-chrome --incognito` | CDP |
| `chrome_cold` | real Chrome Guest (`--guest`), throwaway `--user-data-dir` | CDP |
| `chrome_full` | real Chrome signed into a persistent consumer Google account | CDP |

Instruments (placeholder hosts — replace with a testbed you operate):

- invisible reCaptcha v2 (`https://v2-invis.example.test/`)
- Turnstile (`https://t.example.test/`)
- invisible Turnstile (`https://t-invis.example.test/`)
- reCaptcha v3 (`https://v3f.example.test/`)

Override hosts by editing `INSTRUMENTS` in `run.py` or passing `--urls`
to the screening runner.

The agent fills the login form and **stops**. It does not solve an image grid.
Outcomes are determined by manually reviewing each run's recording and
terminal log (see `result/`, `recordings/`, `terminal_logs/` under the
experiment root):

- v2-invis: silent admit vs grid raised
- Turnstile / v3: admitted vs rejected

## One-time: persistent profile for `chrome_full`

Use a copy of a Chrome user-data directory that already contains a consumer
Google account the operator uses as an ordinary personal account. Do not
publish that directory.

```bash
cd llm-based-crawlers/browser_setup
python3 chrome_launcher.py --prepare-full-profile
```

That writes `profiles/chrome-full-research/` (gitignored). Override with
`CHROME_FULL_PROFILE` or `--full-profile`. Set
`CHROME_PROFILE_DIRECTORY` to the person directory inside that copy
(default `Default`). Do not point it at a profile Chrome currently has open.

`seed_manifest.json` lists public sites that can be used to age a throwaway
research profile. Cookies and user-data directories are not included here.

## Run the grid

```bash
python run.py --smoke
python run.py --configs chrome_incognito chrome_cold chrome_full --trials 1
python run.py --trials 5
```

## Results

Each run writes a result JSON, a screen recording, and a terminal log under
`<exp-root>/<agent>/<config>/<instrument>/`, where `<exp-root>` defaults to
`../experiment_runs/browser_setup_YYYYMMDDTHHMMSSZ`. Outcomes are determined
by reviewing those recordings/logs manually rather than by an automated
verdict script.
