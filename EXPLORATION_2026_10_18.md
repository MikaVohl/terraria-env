# Exploration aids and policy inputs on v4 — October 18, 2026

Status: **complete exploratory screen + first long runs**. Main game v4, mechanics
unchanged. Numeric evidence: [EXPLORATION_2026_10_18.json](EXPLORATION_2026_10_18.json);
run artifacts: `experiments/explore-screen-20261018`, `experiments/explore-long-20261018`,
`experiments/explore-v7-20261019` (v7 follow-up).

Question: the policy plateaus at ~18/32 because the furnace's joint prerequisites
(4 wood + 20 stone + 3 torches + nearby workbench) never coincide
([crafting bottlenecks](CRAFTING_BOTTLENECKS_2026_10.md)). Which training-time
changes, without changing game rules, move progression past the furnace?

## Setup

Every arm: v4, shared-target PPO (`targets`, hidden 128), gamma .999, lambda .99,
entropy .03, 64×128 batches, fresh 16,777,216-step schedule, validation on fresh
worlds **23,000,001–23,000,128** at 4M intervals (categorical sampling, seed
54321). Reserved worlds 25,000,001–25,000,128 are unused. Arms differ only by flags:

| Arm | What changes (training only unless noted) |
| --- | --- |
| control | nothing |
| archive | 25% of training episodes restart from a Go-Explore archive of saved states (new exact `save_state`/`load_state` C API) |
| sil | self-imitation learning on best past episodes, 4 minibatches/iteration |
| archive_sil | both |
| novelty | count bonus 0.1/sqrt(n) on first entry per episode into a coarse progress cell (achievements, log-binned inventory, visible stations, depth band) |
| memory | policy input: observed-only memory of workbench/furnace/anvil positions (12 features) |
| craftable | policy input: which recipes are craftable now (Terraria's crafting menu; equals the craft entries of the legal mask) |
| potential | potential-based shaping γΦ(s′)−Φ(s), Φ = 3 × mean over recipes of held-ingredient fraction (+station visible). **Encodes recipe knowledge** (disclosed prior); policy-invariant in theory |
| aux | predictive auxiliary loss (inventory change sign per item, next unlocks), weight .5 |
| combined | archive + sil + novelty + memory |
| stage 2 | potential_hi (Φ×10), craft_potential, craft_mem_potential |

Seeds 901/902/904/905 ran on CPU (bit-identical learner), 903/906 on hybrid MPS
(learner on GPU, rollouts on CPU). Contrasts are paired within a seed, so each
seed uses one device layout for all arms. Seed 902 covers only control and
craftable after a shutdown interruption (other 902 runs were dropped, not rerun).

## Results at 16M (paired against control on the same seed)

| Arm | Seeds | Mean score /32 | Δ vs control | 95% t-interval | Furnace worlds /128 (Δ) |
| --- | ---: | ---: | ---: | --- | ---: |
| **potential** | 5 | **19.01** | **+1.41** | [+0.17, +2.66] | 23.0 (+21.4) |
| craft_potential | 3 | 18.93 | +1.78 | [−1.65, +5.20] | 17.0 (+15.7) |
| potential_hi | 3 | 18.88 | +1.73 | [−0.69, +4.16] | 29.0 (+27.7) |
| craftable | 3 | 18.53 | +0.22 | [−1.78, +2.21] | 6.0 (+4.3) |
| control | 6 | 17.73 | — | — | 1.5 |
| archive | 2 | 18.24 | −0.03 | wide | 1.0 |
| memory | 2 | 18.23 | −0.04 | wide | 1.5 |
| aux | 2 | 18.05 | −0.22 | wide | 2.5 |
| craft_mem_potential | 3 | 16.44 | −0.71 | wide (one seed surface-trapped) | 7.0 |
| archive_sil | 2 | 17.48 | −0.79 | wide | 2.5 |
| sil | 2 | 16.88 | −1.39 | wide | 0.0 |
| novelty | 2 | 10.86 | **−7.42** | [−8.37, −6.46] | 0.0 |

Intervals are per-arm and not adjusted for comparing ~11 arms; with that many
looks, potential's interval should be read as strong evidence, not proof.

## Long runs: 48M (50,331,648 steps), hybrid MPS, two seeds per arm

| Run | 8M | 16M | 24M | 32M | 40M | 48M | Furnace / copper smelt / anvil at 48M |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| control-911 | 17.10 | 18.28 | 18.90 | 19.59 | 19.57 | 19.66 | 6 / 4 / 1 |
| control-912 | 18.23 | 18.97 | 19.46 | 19.55 | 20.53 | 20.52 | 42 / 38 / 3 |
| potential-911 | 19.15 | 19.46 | 20.44 | 18.73 | 21.66 | **21.67** | **86 / 71 / 13** |
| potential-912 | 18.48 | 19.08 | 19.80 | 20.35 | 20.73 | 20.90 | 61 / 49 / 8 |

At 48M potential leads by +2.01 and +0.38 (mean +1.20). The best policy smelts all
four ores (copper 71, iron 67, silver 59, gold 41 of 128 worlds), crafts anvils in 13
and metal swords in 2. Longer training alone also starts reaching the furnace
(control-912: 42/128), so shaping mostly brings the chain earlier and makes it more
frequent; two seeds cannot separate those effects reliably.

## v7 follow-up: potential shaping vs control at 16M (four paired seeds)

v7 library rebuilt from the frozen October 17 sources plus only the snapshot C-API
additions (gameplay hash identical to the frozen v7 build), selected with
`TERRARIA_LITE_LIB`; same package, validation worlds and Φ coefficient 3.
Seeds 931/932 on hybrid MPS, 933/934 on CPU.

| Seed | Control 16M | Potential 16M | Δ | Potential workbench / furnace / copper smelt (of 128) |
| --- | ---: | ---: | ---: | --- |
| 931 | 16.74 | 18.21 | +1.47 | 126 / 5 / 3 |
| 932 | 16.42 | 18.04 | +1.62 | 127 / 8 / 5 |
| 933 | 16.32 | 18.16 | +1.84 | 126 / 10 / 8 |
| 934 | 16.71 | 18.21 | +1.50 | 128 / 4 / 4 |

Mean **+1.61/32** (95% t [+1.34, +1.87]); positive on every seed. Controls never
build a workbench (0/128 in all four, matching the October 17 study); potential
builds it in 126–128 worlds from 4–8M, plus wooden swords and first v7 furnaces
and smelts. Furnace counts peak mid-run (up to 19/128 at 12M) and fall by 16M,
so the furnace step is reached but not yet retained. v7 with potential (18.2)
roughly matches the v4 control (17.7) but remains below v4 with potential (19.0).

### v7 at 48M (two paired seeds, hybrid MPS)

| Run | 8M | 16M | 24M | 32M | 40M | 48M | Workbench / furnace / copper smelt / wooden sword at 48M |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| control-941 | 16.68 | 16.63 | 16.96 | 17.34 | 17.45 | 17.60 | 3 / 0 / 0 / 0 |
| control-942 | 16.25 | 16.17 | 16.83 | 16.87 | 16.98 | 17.44 | 4 / 0 / 0 / 0 |
| potential-941 | 16.95 | 17.63 | 18.96 | 18.79 | 18.45 | **19.05** | 128 / 7 / 4 / 110 |
| potential-942 | 17.15 | 17.54 | 18.11 | 18.89 | 18.51 | **19.05** | 127 / 13 / 10 / 101 |

Potential leads by +1.45 and +1.61 at 48M. v7 with potential (19.05) exceeds the v4
16M control mean (17.73) but stays below v4 at 48M (control 19.66/20.52, potential
21.67/20.90). Unlike v4, the gain stays
in the workbench/wooden-sword tier: furnace rates remain 0–13/128 across the whole
run and v7 controls never pass the workbench even at 48M. So v7 has a second
barrier at the furnace that v4 does not [inference: candidates are v7's multi-tile
station footprints/placement and station range, not yet diagnosed].


## Interpretation

- **Joint-prerequisite assembly was the gate, and dense progress toward it opens
  the chain.** Potential shaping is the first change that reliably gets past the
  furnace; gains come almost entirely from furnace/smelting/anvil, not earlier tiers.
  Deaths rise somewhat (+0.11 mean), consistent with more underground ore time
  [inference]. It is prior knowledge, disclosed as such, not a neutral learner.
- **Crafting-menu input (craftable) is strongly seed-dependent**: +1.14 and 15 more
  furnaces on one seed, nothing on two. Stacking it with potential did not beat
  potential alone.
- **Surface traps**: novelty at 0.1 pins every policy to the surface (benches in
  every world, never stone). Several potential-family runs also sat at ~10–11 at
  4M before escaping by 8–12M; craft_mem_potential-905 did not escape by 16M.
  [Inference] Bonuses earnable at the surface (inventory bins, wood/workbench
  progress) compete with the sparse reward for descending.
- **Self-imitation suppresses the workbench** (0–2/128 at every checkpoint vs 120+
  for control) [inference: it imitates early non-crafting episodes and locks them in].
- Archive starts, station memory and the predictive auxiliary loss are neutral at 16M.
- **Return to surface stays 0/128 everywhere**, but is mechanically reachable: a
  scripted pillar-jump ascent succeeded from 39/39 deep states in a median 54–218
  actions with stone the policies already carry. It is an exploration/credit problem.
  A minor mask over-report exists: `climb up` is legal at the top of a rope but has
  no net effect (`can_climb`, src/sim.c ~372). Not fixed (game-behaviour change).
- About 1,200 of ~2,850 actions per episode still come after the last new achievement.

## Methods notes

- An 8M checkpoint of a 16M run predicts the final score rank well (Spearman 0.90;
  4M: 0.41) but not furnace outcomes, which often appear after 8M.
- Throughput: matched-algorithm CPU (`--collect-threads 1`) is bit-identical and
  ~1.16× faster; a hybrid MPS learner (`--device mps --collect-device cpu`) runs
  ~5.7k steps/s per run with 4 concurrent, ~3.5k with 8, on top of CPU runs. An
  earlier "MPS stall" reading was a misdiagnosis (`ps` CPU time is unreliable here).
- Every default is unchanged; the default training path is verified bit-identical
  to the previous commit.

## Code added

- `src/capi.c`: `tl_state_bytes/tl_save_state/tl_load_state` (exact snapshot),
  `tl_player_x`, `tl_tile_name`; Python `TerrariaLite.save_state/load_state/position`,
  `SPEC.tile_names`; regression check `check_state_snapshots` in `v2_checks.py`.
- `python/terraria_lite/`: `cells.py`, `archive.py`, `self_imitation.py`,
  `count_novelty.py`, `potential.py`, `memory_features.py` (stations_v1,
  craftable_v1, `PolicyFeatures`), `predictive_aux.py`; `ppo_agent.Config` flags
  `archive_start_prob`, `sil_minibatches`, `novelty_coef`, `potential_coef`,
  `memory_features`, `aux_coef`, `collect_device`, `collect_threads`;
  `target_agent` `extra` input; `ppo_eval` feature-aware evaluation.
- `tools/iterate_ppo.py` flags for all of the above; `tools/explore_screen.py` launcher.

## Next candidates (not launched)

1. Potential shaping at 48M+ with more seeds, and potential plus a small surface-trap
   remedy (e.g. annealing the potential coefficient, or entropy schedule).
2. Target the unearned cheap points: return to surface (pillar ascent) and wood
   breastplate (30 wood), e.g. extending the potential to height-after-deep.
3. Retry cell novelty at ~0.01 or restricted to underground cells.
4. One-shot reserved-test evaluation of a selected policy only after selection is frozen.
