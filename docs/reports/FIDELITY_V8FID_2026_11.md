# v8fid: real-Terraria behaviour ports on v8 (2026-11)

**Question.** How do simulator speed and learnability change when Terraria-Lite's
simplified dynamics are replaced by behaviour ports of the real game?

**Base.** v8 `build-v8-o3t2-inv` (`ORE_PCT=300 TREE_HEIGHT_PCT=200 INV_LOG=1`).

**Variant.** `variants/v8fid/`, a copy of v8 with five independent compile-time knobs, all
off by default. The knobs, their constants and the rescaling are documented in
`variants/v8fid/README.md`.

## Method

- **Sources of real behaviour.** Decompiled tModLoader 2026.08 / Terraria 1.4.4 classes
  `NPC`, `Player`, `Collision`, `Item`, `WorldGen`, `HitTile` and `Projectile`. They were
  produced with ilspycmd on `omarchy` (`~/tml-bench/decomp`) and stay there. Constants that
  live in non-decompiled classes are taken from terraria.wiki.gg: the 4% base crit chance
  and the axe-power table, which the decompiled axe formula confirms.
- **What was ported.** State machines, constants and formulas, rewritten in C. Every port
  names its decompiled method in a comment. No game code or files are in the repository.
- **Time scale.** The ticked knobs (mobs, combat, physics, mining) run 4 real 60 Hz ticks
  per agent action, with the action's input held for those ticks. A 3000-step episode is
  200 s of game time.
- **Units.** Positions and velocities are Q16.16 fixed-point pixels. All arithmetic is
  integer, so runs are deterministic and `save_state` is still a byte copy of `Env`.

## The knobs (summary; details and constants in the variant README)

| Knob | Real-game basis | Rescaling / deviations |
|---|---|---|
| `FID_MOBS` | `NPC.AI_001_Slimes` (type 1): hop timer, hops of −6/+2 and −8/+3 px/tick, gaps of 120/120/200 grounded ticks passive or half when aggressive. `NPC.AI` aiStyle 14, type 49: chase at 0.1/0.04 px/tick², capped at 4/1.5, bouncing, line-of-sight wander. `UpdateNPC` gravity 0.3, cap 10. `TileCollision`. Stats from `SetDefaults`: 25/16 life, 7/13 damage, 2/2 defense, knockBackResist 1/0.8, 24x18 / 22x18 px. | 4 ticks per action. v8 spawn rule and despawn radius kept. Always day, since v8 has no night. `worldSurface` stand-in is the row under `SURFACE_MAX`. No liquids, slime-held items or slime rain. |
| `FID_COMBAT` | Swing hitbox from `ItemCheck_GetMeleeHitbox` and `ItemCheck_ApplyUseStyle` (useStyle 1). `ItemCheck_MeleeHitNPCs`: NPC immunity = itemAnimation, attackCD, CanHit. Shortsword stab from `AI_161_RapierStabs`. `NPC.HitModifiers` / `StrikeNPC`: DamageVar ±15%, defense·0.5, crit ×2, knockback branches. `Player.Hurt`: 40-tick i-frames, knockback (4.5, −3.5). Weapon useAnimation and knockBack from `Item.SetDefaults`. | Uses the dedicated server's 32x32 item frame; the client uses texture sizes. Stab direction is horizontal and its line is approximated by a box. Real NPC damage (bat 13) is used whenever `FID_MOBS` or `FID_COMBAT` is on. Without `FID_PHYSICS`, player knockback is 5 cells, one per action (measured from the physics port); without `FID_MOBS`, NPC knockback is a one-cell shove. |
| `FID_PHYSICS` | `Player.HorizontalMovement` (0.08 acceleration, 0.2 slowdown, max 3). `JumpMovement` (5.01 px/tick for 15 held ticks; Cloud in a Bottle 11). Gravity 0.4, maximum fall speed 10. `Collision.StepUp`/`StepDown`. `DryCollision` with the 20x42 hitbox. Platform drop-through. The real fall check. | Each action holds left, right, jump, down or up for 4 ticks. A held jump continues through left/right (running jumps). The observation adds sub-tile x/y and velocity x/y. Rope climbing is a simplified `pulley` port with no side switching or swinging. No slopes or liquids. |
| `FID_MINING` | `Player.GetPickaxeDamage`: dirt 2x, tileNoFail and rope one hit, otherwise pick power. `HitTile` AddDamage/Prune with the 100 threshold and decay. `KillTile(fail)` turns grass into dirt. Copper/iron/gold picks: 35/15, 40/13, 55/17 (power/useTime). Copper Axe on trunks: 8 per hit, useTime 21. | 8 hit slots instead of 500. Trunks use the real starting Copper Axe, because the agent has no item switching. The observation adds the dug tile's damage. |
| `FID_TREES` | `WorldGen.GrowTree` heights `Next(5,17)` with `EmptyTileCheck`. `KillTile_GetTreeDrops`: 1 wood per tree tile, +1 if `Next(100) < axe` (7) or 1/3. Branches 2/10 per side with no repeats; 1-2 roots. | Branches and roots are sampled at felling, because the grid keeps single-column trunks. Canopy leaves kept from v8. Acorns not modelled. |

### Ports that are not fully faithful

Everything else listed above is ported as decompiled. The following are approximations,
each forced by the grid world or the action interface:

- **Rope climbing** (`FID_PHYSICS`). Simplified `pulley`: grab, vertical acceleration,
  damping and exit are ported. Side switching, rope-to-rope moves and the camera snapping
  logic are not.
- **Combined inputs** (`FID_PHYSICS`). One action is one held input set, so the agent cannot
  run while mining or swinging. Real players can. Running jumps are the one combination
  supported.
- **Sword hitbox size** (`FID_COMBAT`). The server's 32x32 frame is used instead of per-sword
  texture sizes. The real client uses textures, typically 32-40 px.
- **Shortsword stab shape** (`FID_COMBAT`). The stab's AABB-vs-line test is replaced by an
  axis-aligned box. The two agree for the horizontal stabs used here, within ±5 px at the
  ends.
- **NPC spawning** (`FID_MOBS`). v8's spawn and despawn rules are kept; real NPC spawning is
  a separate system.
- **Branches and roots** (`FID_TREES`). Not placed as tiles; sampled at felling.

## Gate 1: parity (all knobs off)

`build-v8fid-off` against `build-v8-o3t2-inv`, both built now with the same `capi.c` and
`LIGHT_WINDOW=1`:

- **`tools/v8_probe.py`** (384 worlds plus a 16,000-step rollout): identical. Hash
  `1e02428301ccd759`, same ore and log counts.
- **`tools/v8fid_probe.py`**: identical.
  - The world hash covers save_state plus the first observation for 384 seeds:
    `642f3d5813783726`.
  - The rollout covers 8 lanes × 25,000 uniform-legal steps (200,000 steps), hashing every
    observation, reward, end flag and mask, plus the full state every 1000 steps:
    `b8f163b4f1e2f556`.
  - State size is the same: 51,040 bytes.

Evidence: `experiments/fidelity-v8fid-20261107/{v8_probe_v8,v8_probe_off}.json`, `probe.txt`.

## Gate 2: determinism and save/load with each knob on

`tools/v8fid_probe.py` runs the 200,000-step rollout twice in one process and compares
hashes. It also snapshots at steps 1, 137, 777 and 2400, continues 500 steps, restores the
snapshot into a fresh env (over an unrelated world) and replays the same actions.
`save(load(x)) == x` is checked too.

| build | status len | deterministic | save/load |
|---|---|---|---|
| off | 521 | yes | 0 failures |
| mobs | 521 | yes | 0 failures |
| combat | 521 | yes | 0 failures |
| physics | 525 | yes | 0 failures |
| mining | 522 | yes | 0 failures |
| trees | 521 | yes | 0 failures |
| mobcombat | 521 | yes | 0 failures |
| all | 526 | yes | 0 failures |

## Gate 3: fixture tests

`sh tools/v8fid_test.sh` builds one binary per knob set (mobs, combat, physics, mining,
trees, mobcombat, all). It checks each port against values recomputed from the real
constants. **136/136 checks pass**; the log is `experiments/fidelity-v8fid-20261107/fixtures.txt`.
Key measurements:

| check | measured | real basis |
|---|---|---|
| full jump (held) | 97.9 px = 6.12 tiles | 98.07 px (JumpMovement, gravity 0.4) |
| one-action hop | 42.6 px = 2.66 tiles | 42.75 px |
| run speed | max 3.04, steady 2.91 px/tick; ≥2.9 after 40 ticks | maxRunSpeed 3, acceleration 0.08 |
| max fall speed / 30-tile fall | 10.00 px/tick / 50 hp | 10 / (30−25)·10 |
| step up / blocked | 1-tile step climbed; 2-tile wall blocks | StepUp |
| 42 px hitbox | 2-high tunnel blocks, 3-high passes; 1-wide hole holds, 2-wide drops | 20x42 |
| slime hop gaps | 120, 120, 200 passive; 60, 60, 100 aggressive | AI_001 |
| slime hop heights | 57.0 / 102.7 px | vy −6 / −8, gravity 0.3 |
| bat speed | max \|vx\| 4.00, \|vy\| 1.50 | aiStyle 14 |
| player i-frames | 5 hits in 200 ticks, every 40 | immuneTime 40 |
| damage variance (7, defense 0) | P(6,7,8) = .263 / .481 / .256 | 8/31, 15/31, 8/31 |
| NPC immunity | 1 hit per swing | NPC.immune = itemAnimation |
| broadsword reach | foot level 0 to +48 px, overhead hit | 32x32 frame, useStyle 1 |
| shortsword reach | 45 px past the centre | 2.1·14 + 12.6 + 5 = 47 |
| crit rate / NPC damage | 3.7-3.8% / 7-9 (copper broadsword) | 4% / round(9·0.85..1.15) − 1 |
| NPC knockback | slime vx 5.5, vy −4.12; bat 3.2 | StrikeNPC, knockBackResist 0.8 |
| hits per tile (copper pick) | dirt 2, grass 2, stone and ores 3, torch 1 | 35 power, dirt 2x |
| hits per tile (gold pick) | dirt 1, stone 2 | 55 power |
| hits per tree | 13 (253 ticks = 64 actions) | axe 7 → 8 per hit |
| hit decay | 35 → 17 after 20 other hits | HitTile.Prune |
| tree heights | 400 worlds, 3020 trees, 5-16 uniform (χ² 4.7, 11 df) | Next(5,17) |
| wood per tree | 20.1 (trunk mean 10.4) | 1.38 per tree tile, plus branches and roots |

Log supply per world (`tools/v8_probe.py`, 128 validation worlds):

| | median | min | max |
|---|---|---|---|
| v8 o3t2 trunk tiles | 122 | 90 | 149 |
| FID_TREES trunk tiles | 83 | 27 | 132 |

FID_TREES has fewer trees but about 1.9 wood per trunk tile, against v8's 1.

## Gate 4: speed

Tool: `tools/sim_throughput.c`, the v9 D18 method. One thread, 64 lanes, uniform legal
actions drawn from each lane's mask, and the full `tl_batch_step` per step (env_step,
observation, mask), with resets included. Each library ran 3 interleaved rounds of 20,000
steps per lane on an Apple M5 Pro; the table reports the median. Libraries were measured in
two groups of at most 8, each with v8 as its reference. Raw JSON:
`experiments/fidelity-v8fid-20261107/throughput_{a,b}.json`.

| build | steps/s (median) | min-max | ratio vs v8 |
|---|---|---|---|
| v8 o3t2-inv (group a / b) | 1,289,233 / 1,301,604 | 1.29-1.30 M | 1.00 |
| v8fid-off | 1,302,644 | 1.30-1.30 M | 1.01 |
| v8fid-mobs | 1,151,381 | 1.146-1.154 M | 0.89 |
| v8fid-combat | 1,219,204 | 1.219-1.221 M | 0.95 |
| v8fid-physics | 1,176,499 | 1.173-1.177 M | 0.91 |
| v8fid-mining | 1,410,316 | 1.410-1.420 M | 1.09 |
| v8fid-trees | 1,366,014 | 1.363-1.378 M | 1.06 |
| v8fid-mobcombat | 1,106,835 | 1.106-1.108 M | 0.86 |
| v8fid-all | 1,117,150 | 1.108-1.120 M | 0.86 |

Every build passes the 1/1.5 sim-cost gate.

The NPC port's first version measured 0.63x. Collision then scanned the real routine's full
neighbourhood; it now scans only the tiles the moved box overlaps, which changes no result
(all probe hashes identical before and after).

Under a random policy, mining and trees run faster than v8 because fewer tiles change, so
there are fewer light updates. The ratios come from uniform legal actions and will differ
under a trained policy.

## Gate 5: training smoke (CPU)

`tools/iterate_ppo.py` ran with the `max2_pot0_nov01_unimix_g9998` training arguments,
adapted to CPU: `--potential 0 --novelty .01 --unimix .01 --gamma .9998`, targets
architecture, 1024 envs × 128, 16 minibatches, `--native-autoreset --compact-obs`. The
CUDA-only options (`--collect-device cuda`, compile, bf16, fused Adam, async evaluation)
were dropped. Library: `build-v8fid-all`; seed 2001; 2,097,152 steps.

| | |
|---|---|
| validation at 1,048,576 steps | 2.969/32 (death 50.0%) |
| validation at 2,097,152 steps | 3.938/32 (death 72.7%) |
| checkpoints | `step-1048576.pt`, `step-2097152.pt` (128 validation worlds each) |
| throughput | 10,089 steps/s, 208.5 s |
| last-200-episode hits | defeat Blue Slime 154, heal 146, place block 200, workbench 14 |

The pipeline (status length 526, new entity offset, novelty decode, native autoreset,
validation, checkpoint) runs end to end. Run directory:
`experiments/fidelity-v8fid-20261107/smoke_all_g9998/` (checkpoints stay local).

## Learnability

Training results for the fidelity builds (2B steps, 5 seeds, the generic and shaped arms on
the GPU node) will be appended to this section by the parent study. No learnability
conclusion is drawn here from the 2M-step smoke run.

## Reproduce

    sh tools/v8fid_test.sh
    # builds: see variants/v8fid/README.md
    PYTHONPATH=python uv run python tools/v8fid_probe.py perf/v7/build-v8-o3t2-inv/libterraria.so perf/v7/build-v8fid-*/libterraria.so
    cc -O2 tools/sim_throughput.c -o /tmp/sim_throughput
    cd perf/v7 && /tmp/sim_throughput -r 3 -s 20000 build-v8-o3t2-inv/libterraria.so build-v8fid-{off,mobs,combat,physics,mining,trees,mobcombat}/libterraria.so
