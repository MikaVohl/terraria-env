# site: the Terraria-Lite benchmark website (local)

A static site (HTML, CSS, vanilla ES modules, JSON data) that presents the Terraria-Lite benchmark: an RL and LLM leaderboard on Terraria-Lite and on official Terraria, the RL study ("bitter lesson" PPO against RL with disclosed priors), and the environment itself.

```sh
make -C site serve      # http://localhost:8778 (builds viz/terraria.wasm and links the textures if needed)
make -C site data       # re-export data/rl.json, data/llm.json and data/tapes/ from local experiment artifacts
make -C site official   # re-export data/terrariabench.json (TerrariaBench compact records + Omarchy over ssh)
make -C site videos     # copy, trim and encode the official-Terraria run videos into media/ (gitignored) and data/videos.json
```

Run these commands from the canonical Omarchy checkout
`/home/mika/Projects/terraria-lite` (logical path), backed by
`/mnt/storage/data/projects/terraria-lite` (physical storage). The official
export and video tools read `~/Projects/terraria-lite/TerrariaBench/runs` on
`mika@omarchy`; the older standalone `~/Projects/TerrariaBench` remains a
historical raw-run archive, not the active source tree. Archived reports and
run manifests keep their original location strings.

The official-Terraria videos are not committed. `tools/fetch_videos.py` copies each listed run's `desktop.mp4` (and `recording.json` when present) and records from Omarchy (`ssh mika@omarchy`), places the recording on the wall clock (recording.json `video_start_unix`, or the birth time of the MP4 for older recordings; refined for paused runs by fitting the logged freeze intervals in `clock.jsonl` to the still stretches ffmpeg's `freezedetect` finds), keeps the evaluation window, cuts every model-call freeze from paused runs, checks the kept length against the played game time and encodes 960x960 H.264 with faststart. Older recordings are the 1100x1100 desktop: the game window is cropped out, 10 frames/s, no audio. Recordings since 2026-11-11 are the game window itself at 30 frames/s with the game's audio: no crop, 30 frames/s, and the audio is cut with the same frames (rows carry `fps` and `audio`). `--adhoc CAMPAIGN/RUN` processes any run without touching `videos.json`. Without the files the video players show how to fetch them.

A module page cannot load from `file://`, so the site has to be served. The interactive parts need a local Terraria install for the art, exactly like `viz/` (see `viz/README.md`; pass `TEXTURES=<ExtractedTextures dir>` if it is not at the default Steam path). Without textures, tables and charts still render (without item icons); the live canvases show an error message instead.

On Linux, set the local extracted-art directory explicitly, for example
`make -C site serve TEXTURES="$HOME/.local/share/Steam/steamapps/common/Terraria/ExtractedTextures"`.
The browser's build uses Linux LLVM/LLD from `PATH`; macOS retains the Homebrew
defaults. `LLVM=<clang directory>` and `LLD=<wasm-ld directory>` override them
(see `viz/README.md`). The website's versioned environment pages describe
historical and experimental profiles; its live browser still builds the
default v8 core, not v9/v10.

## Pages

| Page | What it shows |
|---|---|
| `index.html` | TL;DR, key numbers, live policy in the header, mini leaderboards, Craftax-style "fast / hard / open-ended" sections with our numbers, score against cost, Craftax calibration, work in progress |
| `lite.html` | Terraria-Lite leaderboard per environment version (v10, v9, v8, v7): IQM or mean with 95% CI or seed range, seeds x worlds, split, budget, cost, time, Crafter score, deaths, verified replay or checkpoint; v10 port ablations; score against cost and time; all per-achievement rates; progress over an episode; first-unlock heatmap; per-episode distribution |
| `terraria.html` | Official Terraria track (tModLoader, profile default-v2, interim): leaderboards for real time and paused, Opus against Opus planner + Jev executor, milestone timelines and first-unlock heatmap, run videos, every run with notes, comparison with earlier profiles and terrariabench.com, harness card (prompt and tool schema), real speed measurements, RL training cost estimator, planned rows (sample) |
| `rl.html` | What helped RL: findings, generic against shaped PPO with rliable statistics, a one-dimension-at-a-time ablation explorer, learning curves, score against compute |
| `environment.html` | Interface, world gallery rendered from seeds, achievements and v9 tiers, what v9 adds, human play entry point, speed table, determinism and parity |
| `failures.html` | Failure gallery: illegal LLM actions, deaths, PPO not returning to the surface, iron bars spent on extra anvils, stockpiling, wider worlds, idle tails; official Terraria: false "placed" claims, real-time death loops, Save & Exit, Haiku wrap-up streaks, runs that do not count (with videos) |
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
| `lite.json` | Leaderboard entries per version (v10, v9, v8, v7) and the v10 port ablations; v7/v8 real entries reference `rl.json`/`llm.json` (`ref`), v9/v10 real entries carry their numbers inline with a `source` (eg15 run summaries, `docs/reports/LLM_V9_CAMPAIGN_2026_11_08.md`); the rest are `placeholder: true` | mixed (sample: v8 BC arm, v8 LLM A/B, humans, random, v9 oracle) |
| `terraria.json` | Official track, hand-written part: planned RL and human rows, RL cost model source | planned rows are sample |
| `terrariabench.json` | Official track results: default-v2 runs (interim), default-v1, camp-v2 and reference runs, terrariabench.com summary, catalogs, harness card, quotes | real, generated (`tools/export_terrariabench.py`) |
| `videos.json` | Run videos: raw and trimmed durations, freezes cut, fitted offset and recall | real, generated (`tools/fetch_videos.py`) |
| `environment.json` | Speed measurements, interface facts, v9 tiers, skill clips, gallery seeds, human-play notes | real (human scores are sample) |
| `history.json` | Versions, best score over time, work in progress | real |
| `calibration.json` | Craftax published scoreboard; our 1B reruns (PPO, PPO-RNN, PPO with our settings, 3 seeds each) and the 1M CPU smoke run | real |
| `costs.json` | GPU and CPU rental rates (assumptions, flagged), API prices with dates | rates are placeholders |
| `failures.json` | Failure gallery text; the charts come from `rl.json`/`llm.json`/`terrariabench.json`, videos from `videos.json` | real |
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
