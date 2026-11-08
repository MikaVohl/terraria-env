# site: the Terraria-Lite benchmark website (local)

A static site (HTML, CSS, vanilla ES modules, JSON data) that presents the Terraria-Lite benchmark: an RL and LLM leaderboard on Terraria-Lite and on official Terraria, the RL study ("bitter lesson" PPO against RL with disclosed priors), and the environment itself.

```sh
make -C site serve      # http://localhost:8778 (builds viz/terraria.wasm and links the textures if needed)
make -C site data       # re-export data/rl.json, data/llm.json and data/tapes/ from local experiment artifacts
```

A module page cannot load from `file://`, so the site has to be served. The interactive parts need a local Terraria install for the art, exactly like `viz/` (see `viz/README.md`; pass `TEXTURES=<ExtractedTextures dir>` if it is not at the default Steam path). Without textures, tables and charts still render (without item icons); the live canvases show an error message instead.

## Pages

| Page | What it shows |
|---|---|
| `index.html` | TL;DR, key numbers, live policy in the header, mini leaderboards, Craftax-style "fast / hard / open-ended" sections with our numbers, score against cost, Craftax calibration, work in progress |
| `lite.html` | Terraria-Lite leaderboard per environment version (v9 draft, v8, v7): IQM with 95% CI, seeds x worlds, split, budget, cost, time, Crafter score, deaths, verified replay or checkpoint; score against cost and time; all per-achievement rates; progress over an episode; first-unlock heatmap; per-episode distribution |
| `terraria.html` | Official Terraria track (tModLoader): draft contract, sample leaderboard, Pareto plots, progress over game minutes, milestone heatmap, real speed measurements, RL training cost estimator |
| `rl.html` | What helped RL: findings, generic against shaped PPO with rliable statistics, a one-dimension-at-a-time ablation explorer, learning curves, score against compute |
| `environment.html` | Interface, world gallery rendered from seeds, achievements and v9 tiers, what v9 adds, human play entry point, speed table, determinism and parity |
| `failures.html` | Failure gallery: illegal LLM actions, deaths, PPO not returning to the surface, iron bars spent on extra anvils, stockpiling, wider worlds, idle tails |
| `history.html` | Every version, what changed, the result, what went wrong; best score over time; work in progress |
| `method.html` | Scores, statistics, worlds and splits, verification, cost model, Craftax calibration |
| `submit.html` | Submission kit: pinned versions, seeds, eval commands, JSON results schema, LLM harness rules, reporting rules |
| `replay.html` | Replays every audited LLM tape in the real simulator in the browser and checks the final state against the audit |

## Data

Everything the pages show lives in `data/`:

| File | Content | Real or sample |
|---|---|---|
| `rl.json` | 116 v8 PPO runs (eg15): catalogue, learning curves, final configurations with IQM and bootstrap CIs (same RNG and order as `notebooks/v8_env_results_2026_10_31.ipynb`, so the numbers match it), one-dimension comparisons, per-achievement hits, first-unlock steps, per-episode distributions | real, generated |
| `llm.json`, `tapes/` | Every audited LLM attempt on v7 (Sol smoke, Luna batch, Luna harness study) with cost, calls, tokens, illegal actions, first unlocks, native final state, and the action tapes | real, generated |
| `lite.json` | Leaderboard entries per version; real entries reference `rl.json`/`llm.json` (`ref`), the rest are `placeholder: true` | mixed |
| `terraria.json` | Official track: draft contract, milestones, entries, first-unlock minutes | sample, except the cost model source |
| `environment.json` | Speed measurements, interface facts, v9 tiers, skill clips, gallery seeds, human-play notes | real (human scores are sample) |
| `history.json` | Versions, best score over time, work in progress | real |
| `calibration.json` | Craftax published scoreboard; our reruns | published is real, ours is sample (the 1M CPU smoke run is real) |
| `costs.json` | GPU and CPU rental rates (assumptions, flagged), API prices with dates | rates are placeholders |
| `failures.json` | Failure gallery text; the charts come from `rl.json`/`llm.json` | real (one sample card) |
| `submission.schema.json` | JSON Schema for a results file | draft |

Placeholder entries carry `"placeholder": true` (or `placeholder: true` at file or section level) and render hatched, italic or hollow with a dashed outline, next to a visible "sample data" marker. To replace a placeholder, put the real numbers in the entry and delete the flag, or point its `ref` at generated data.

## Reuse of viz

`site/viz` is a committed symlink to `../viz`. The site imports `viz/js/wasm.js`, `viz/js/terraria.js` and `viz/js/render.js` directly and loads `viz/terraria.wasm`, `viz/data/policy-2147483648.bin` and `viz/textures/`. Nothing from the simulator or the renderer is duplicated: `js/sim.js` adds only a policy sampler, an episode recorder with snapshots for seeking, a camera, and a tape parser. The human baseline entry point is viz's Play chapter.

## What we took from TerrariaBench and Craftax, and why

**Craftax** ([site](https://craftaxenv.github.io/), [repository](https://github.com/MichaelTMatthews/Craftax)):

- The page shape: authors' claim in a TL;DR, then "fast", "hard" and "open-ended" sections, each argued with one figure. Ours use our own measurements (simulator and training steps per second against headless tModLoader, an achievement wall chart, and skill clips cut live from a policy episode instead of GIFs).
- Tiered achievements with weights and a headline of percent of the maximum; v9 adopts weights 1/3/5/8.
- Fixed training budgets (Craftax-1M and Craftax-1B) as separate boards; we report the step budget on every RL row and plan official 250M, 1B and 4B levels.
- The scoreboard with links to code and a note that external numbers are unverified; we go further and require a replay or checkpoint, and show verification status per row.
- A credibility check: we rerun Craftax baselines on our pipeline and compare to their scoreboard before trusting our own PPO numbers.
- The human reference point (one author's 5-hour perfect run) made concrete as a browser play mode on fixed seeds.

**TerrariaBench** ([site](https://terrariabench.com/), [spec](https://terrariabench.com/spec/), [runs](https://terrariabench.com/runs/)):

- The official-game track idea: every model in the same harness, objective scoring from a mod's checkpoint log, never from the model's own report.
- Invalid runs kept visible with the reason (direct tile control, stalled harness), separated from scored runs.
- Progress views: cumulative milestones over time as a step chart, and a first-unlock heatmap per agent and milestone. We draw both, in environment steps for Terraria-Lite and game minutes for the official track.
- Featured runs with clips and logs: our replay page plays every audited LLM tape in the real simulator.

**Research-benchmark practice** ([rliable](https://arxiv.org/abs/2108.13264), Papers with Code style leaderboards): IQM with bootstrap 95% CIs and the seed count on every RL number, probability of improvement between configurations, held-out test worlds evaluated once, all per-achievement rates and the Crafter geometric score next to the headline, and cost and wall time beside score.

## Writing rules for this site

No em dashes, no small uppercase labels above headings, no marketing copy. Every number on a page is in `data/` or cited to a report in `docs/reports/`.
