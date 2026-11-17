# Paper tables

Machine-readable copies of the results reported in the paper. Each file reproduces one table or figure at the cell level the paper reports.

| File | Paper |
|---|---|
| `solver_performance.csv` | RQ1 per-service solver performance (appendix table). The RQ1 solver summary table aggregates these rows. |
| `agent_bypass.csv` | RQ1 off-the-shelf agent bypass@20 figure. Comet declined every trial under its safety policy, so its cells are empty. |
| `environment_grid.csv` | RQ2 verification outcomes across agent, defense, and browser configuration. |
| `llm_backends.csv` | RQ3 reCaptcha v3 execution time and token usage across six model--input conditions on Skyvern and Browser-Use (20 attempts per configuration). |

In `environment_grid.csv`, `admitted` means 18–20 of 20 trials admitted, with any remaining trials failing from agent workflow errors rather than verifier rejection. `rejected` means 0 of 20 admitted.

Per-trial logs, screen recordings, Chrome profiles, session state, and the profile-ablation and cross-machine runs are not included.
