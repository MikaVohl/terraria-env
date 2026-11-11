# Combined move+use actions in v10 (`COMBO_ACTIONS`), 2026-11-10

Question (DECISIONS.md B4): v10 allows one input per 15-tick step. Does that make pillaring out
of shafts, fighting while moving and tunnelling hard enough to explain why no ported-v10
PPO policy learns to return to the surface (0/22 runs)? Option A tested here appends combined
actions that hold a movement input and do a use in the same step.

## Implementation (`variants/v10`, knob `COMBO_ACTIONS`, default 0)

15 actions appended after `use summon item` (ids 86-100; existing ids unchanged, `SPEC.n_actions`
86 -> 101 from the library):

| Movement held | Use |
|---|---|
| left / right / jump | attack |
| jump | place down (pillar) |
| left / right | mine head-, middle-, foot-level cell on that side (tunnel) |
| jump | mine up |
| left+jump / right+jump | place down-left / down-right (bridge, ledge) |
| left+jump / right+jump | none (running jump onto a ledge in one step) |

- Movement is held for the 15 ticks exactly as `left`/`right`/`jump` alone hold it
  (left/right without jump keeps a running jump going; jump re-presses).
- Attack and mine run through the standalone code at the same ticks (swing from the step start,
  mine held every tick, `TOOL_DAMAGE` tool swings included). A combo swing faces its run:
  swords have `useTurn = false` and `Player.Update` turns before `ItemCheck` in the same tick.
- Place combos hold the use button for the step: they place at the step start when the
  standalone place would, otherwise after the first tick where the target cell (relative to the
  body at that tick) takes the block; at most one block per step. This is what makes
  Terraria's one-block-per-jump pillar possible: jumping off a floor drops the block into the
  cell the feet just left, anchored on the floor. Under `BG_WALLS` placement rules (B12) a
  step-start placement cannot do this, because the cell under the feet one step after a jump
  floats 4-5 rows up with no neighbour (unless a background wall is behind it).
- Masks: attack/mine combos = their use's mask; running jumps = jump's; place combos =
  "selected item stocked" (a held place may land on any tick, as mine attempts are not
  masked on hidden cells either).
- With the knob off the preprocessed sources of all six `.c` files are token-identical to
  `4ef5afa`, so the default build is bit-identical (and the noport/v9 parity is untouched).
- Python: `SPEC` derives count and names from the library; `llm_text.py` uses
  `SPEC.action_names` generically, so the combo names ("jump + place down", ...) parse as
  named actions without changes. `variants/v10/tests/check_v10.py` asserts 86 actions and is
  meant for the default build only.

Tests: `variants/v10/tests/combo_test.c` (build line in `variants/v10/README.md`), 31/31 pass:
every combo against the standalone use (same tiles, inventory, swing, mining hits per step) and
the standalone movement (same position and velocity) from one state; left + attack hits a
zombie behind the player that attack alone misses; held place pillars one row in open air
where the standalone pair cannot; masks over 20,000 random steps (0 mismatches of 300,000);
determinism (15,000 steps, byte-identical `Env`) and save/load with a combo-heavy stream.
`selftest.c` 193/193 and `fid_test.c` 102/102 pass with the knob on and off.

## Scripted pillaring (no training; `combo_test.c`, 32 worlds, 200 dirt, <= 400 steps)

`shaft`: a 2-wide shaft dug 30 rows below the surface at the spawn of seeds 1-32 (it often
opens into caves); success = standing above the surface row. `open`: flat floor without walls,
climb 20 rows. Policies: `timed` (continue a jump, else place once airborne, else jump),
`naive` (place whenever legal, else jump), `random` (uniform over the legal ones of noop / jump /
place down, plus jump + place down with combos).

| Scene | Policy | No combos: out, mean steps, deaths | Combos: out, mean steps, deaths |
|---|---|---|---|
| shaft | timed | 11/32, 150.1, 9 | **32/32, 27.7, 0** |
| shaft | naive | 12/32, 60.2, 9 | **32/32, 22.5, 0** |
| shaft | random | 29/32, 110.2, 3 | 32/32, 40.1, 0 |
| open | timed | 0/32 | **32/32, 80.0** |
| open | naive | 0/32 | **32/32, 40.0** |
| open | random | 16/32, 345.6 | 32/32, 81.1 |

The same check on the pre-wall rules (`339dbe9`, where blocks needed no neighbour, and with
step-start-only place combos) gave 32/32 in 16.0 steps for both arms (timed), so pillaring was
mechanically easy for every earlier v10 policy, including the 0/22 B4 runs. Since `BG_WALLS`
(B12) it is not: without combos a climb succeeds only through lucky step timing, and in open
caves essentially never.

## PPO A/B at `4ef5afa` (eg18 GPUs 4-7, 192M steps, about 11-15 min per run)

`build-v10` (`-DINV_LOG=1`) vs `build-v10-combo` (`-DINV_LOG=1 -DCOMBO_ACTIONS=1`), arms
`v10_gen_g9999` / `v10_shaped_g9999`, seeds 4101-4104, 201,326,592 steps each, final validation
128 episodes (seeds 23000001+), `tools/policy_diagnostics.py` on the final checkpoint. Queues:
`tools/queue_20261110_v10combo.json`, `tools/queue_20261110_v10combo2.json`; results on eg18
under `~/Projects/RL-combo/experiments/combo-ab{,2}`. No run hit the 20-minute watchdog.

| Arm | Weighted score % (4 seeds) | Mean | Death rate (mean) | Anvil | Night deaths | Time surface / underground / caverns |
|---|---|---|---|---|---|---|
| gen, no combos | 29.46, 30.55, 30.04, 29.81 | **29.97** | 0.545 | 132/512 | 121 | 0.15 / 0.15 / 0.70 |
| gen, combos | 28.35, 28.53, 27.13, 26.83 | 27.71 | 0.756 | 56/512 | 167 | 0.22 / 0.26 / 0.52 |
| shaped, no combos | 30.23, 29.88, 28.09, 30.04 | **29.56** | 0.549 | 138/512 | 116 | 0.15 / 0.16 / 0.69 |
| shaped, combos | 28.45, 28.42, 28.81, 28.21 | 28.47 | 0.694 | 65/512 | 146 | 0.19 / 0.27 / 0.54 |

- Return to surface: 0 in all 16 runs (both arms; at 192M the no-combo arm does not show it
  either, so this budget cannot answer B4 directly). Lens 2/512 and Demon Eye kills 3/512 with
  combos (one shaped seed and one generic seed), 0/512 without: too rare to read.
- Combos cost 2.3 pp (generic) and 1.1 pp (shaped) of weighted score at equal steps, lower in
  7 of 8 seed pairs, with 15-21 pp more deaths, more night deaths and half the anvil rate.
- Combo usage: 21.7-23.8% of all sampled actions, spread almost evenly (0.6-2.5% each, running
  jumps / attack combos / place combos highest, mining combos lowest) and the same in every
  seed: the policy has not specialised them by 192M; they mostly dilute exploration.
- Combo policies spend more time near the surface and less in the caverns (0.52-0.54 vs
  0.69-0.70 of steps), consistent with easier climbing but also with less purposeful digging.
- Training throughput: generic 295-314k vs 298-321k steps/s, shaped 229-235k vs 232-247k
  (8 runs sharing 4 GPUs; within the run-to-run spread, about -1 to -3%). Raw simulation with
  random legal actions: 0.64M vs 0.60M steps/s (different action mixes, not a cost).

## Recommendation

**Drop A as a default** (keep the knob off; the code stays as an ablation). At the testable
budget the 15 extra actions are a net cost and are not yet used purposefully; nothing here
shows them unlocking the return to surface.

The scripted result is the useful finding: since `BG_WALLS`, step-start placement makes
pillaring nearly impossible in open caves, which is a new and concrete obstacle to returning to
the surface (it cannot explain the older B4 failures, which predate the wall rules). The
narrowest fix is not more actions but the held-place semantics alone: let the standalone
`place` actions place at the first tick in the step where the cell takes the block (as
Terraria's held use does), and re-test pillaring and a 1B PPO run. A factored action space
(movement x use, two heads) is the principled version of A if simultaneous inputs are still
wanted; it should be judged at 1B, where the return to surface appears in no-port builds.
