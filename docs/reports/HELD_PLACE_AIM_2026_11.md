# Held place and aimed attacks in v10 (`HELD_PLACE`, `AIM_ATTACK`), 2026-11-11

Two Terraria input semantics for v10's standalone actions, each a compile-time knob, default on
with the ports (`HELD_PLACE` = `FID_PHYSICS`, `AIM_ATTACK` = `FID_COMBAT`, so `build-v10-noport`
is unchanged and still equals v9). With a knob at 0 the preprocessed sources (sim, worldgen,
light, obs, mobs, boss) are token-identical to `7947630`, so that build is bit-identical.
Details: `variants/v10/README.md` ("Held place and aimed attacks"). PPO validation:
`docs/reports/V10_HELD_AIM_1B_2026_11.md` (the stock-only mask below caused place spam; the mask
was tightened, next section).

## Held place (DECISIONS B12, B14)

Since `BG_WALLS` a block needs a neighbour or a wall. `place` acted only at tick 0 of the
15-tick step, and one step after a jump the cell under the feet floats 4-5 rows up, so pillaring
failed (COMBO_ACTIONS report). Now every `place` action holds the use button for the step, as
Terraria's held use and the place combos (same code path in `env_step`): it places at the step
start when that is legal (identical result), else after the first game tick where the target
cell, relative to the body at that tick, takes the item; at most one item per step. Retries are
skipped while the body position and the stock are unchanged since the last try (nothing else
`do_place` reads changes within a place step); a 320,000-step random-play hash with and without
the skip is identical (combos off and on).

**Mask (original, superseded):** a place action was legal iff the selected placeable is stocked
(as the place combos): a held place may land on any tick, so step-start legality no longer
decides it. Consequence: the mask no longer told the policy where a block fits, and PPO at 1B
spent about 40% of its steps on place actions, 87% of which failed (V10_HELD_AIM_1B report).

**Mask (current, 2026-11-11):** a place action is legal iff it is legal at the step start or
after some tick of the step on the body's predicted path (`held_place_mask` in `sim.c`): a place
step holds no movement, so the path is `player_tick` with no input from the current state, run on
the body itself with every written field restored (fall damage kept out of reach); a tick that
changes nothing ends it. Mobs are ignored, so a contact knockback can still make a masked-in
place miss or a masked-out one land; hidden cells permit attempts as before. Place combos keep
the stock mask. Gates: computing the mask leaves the Env byte-identical (selftest, 8,000 random
steps on 4 worlds); on those steps, trying every place slot on a copy: masked in 25,613 placed /
9,099 failed (all 9,099 next to a hidden cell), masked out 21 placed / 94,307 failed; with no
mobs in the open-air arena the mask predicts every `place down` outcome. Scripted climb with the
new mask (table below has the original numbers): naive (place whenever legal, else jump) now
climbs shaft 32/32 in 30.0 steps (0.97 per row) and open air 32/32 in 80.0 (4.00 per row, as
timed); random play shaft 32/32 in 63.7, open 32/32 in 151.9; timed unchanged. Cost: same
uniform action stream with and without the prediction, 64 lanes x 20,000 steps on eg18: 556k vs
582k steps/s (-4.5% raw simulation); `sim_throughput` (random legal actions, different mixes):
413k tight vs 451k stock-only vs 426k `HELD_PLACE=0`. Checks: selftest 199/199 (also with
combos), 193/193 both knobs off, 99/99 noport, 203/203 `ENV_FX=1`, fid_test 106/106, combo_test
35/35 (31/31 both off), `check_v10.py`, `v10_noport_parity.py` 400,000 steps identical,
`make check-pixel-v10`; with `HELD_PLACE=0` the six sources are token-identical to `2314765`.

### Scripted climb (`combo_test.c`, 32 worlds, 200 dirt, <= 400 steps)

`shaft`: a 2-wide shaft 30 rows below the surface at the spawn (31 rows to climb); `open`: flat
floor without walls, 20 rows. Policies: `timed` (continue a jump, else place once airborne, else
jump), `naive` (place whenever the mask allows, else jump), `random` (uniform over legal noop /
jump / place down, plus jump + place down with combos). Out/32, mean steps of the successes
(steps per row), deaths.

| Scene | Policy | Step-start place (old default) | **Held place (new default)** | Combos on (held) | `BG_WALLS=0` (held) |
|---|---|---|---|---|---|
| shaft | timed | 11/32, 150.1 (4.84), 9 | **32/32, 27.7 (0.89), 0** | 32/32, 27.7 (0.89) | 32/32, 18.0 (0.58) |
| shaft | naive | 12/32, 60.2 (1.94), 9 | 0/32, 7 deaths (degenerate, below) | 32/32, 22.5 (0.73) | 0/32 |
| shaft | random | 29/32, 110.2 (3.55), 3 | **31/32, 69.5 (2.24), 0** | 32/32, 43.5 (1.40) | 32/32, 49.7 (1.60) |
| open | timed | 0/32 | **32/32, 80.0 (4.00)** | 32/32, 80.0 (4.00) | 32/32, 12.0 (0.60) |
| open | naive | 0/32 | 0/32 (degenerate) | 32/32, 40.0 (2.00) | 0/32 |
| open | random | 16/32, 345.6 (17.3) | **32/32, 171.6 (8.58)** | 32/32, 82.3 (4.12) | 32/32, 34.2 (1.71) |

- Held standalone place climbs exactly as the place combos with the same script (timed: 27.7
  / 80.0 steps), with no extra actions. Random play gets out of open caves 32/32 (was 16/32) in
  half the steps.
- `naive` degenerates under the new mask: place is always legal with stock, so it never jumps.
  With step-start masks (`HELD_PLACE=0 BG_WALLS=0`) naive climbs 32/32 in 21.0 / 12.0 steps.
- Open-air pillaring under walls costs 4 steps per row (jump, place until it lands, settle)
  vs 0.6 without walls: the block lands only once the falling feet are one row above the floor
  or pillar top, which a single step after the jump does not reach.
- selftest fixture (`test_held_place`): 10/10 open-air rows in 40 steps.

## Aimed attacks (DECISIONS B15)

Verified against the decompiled 1.4.4 source (`omarchy:~/tml-bench/decomp`): Copper Shortsword
(3507) `shoot = 938`, useAnimation 13, kb 4; `AI_161_RapierStabs`: `Center = player.MountedCenter
+ velocity * (ai[0] - 1)`, `Kill()` at `ai[0] >= 16`; `Projectile.Colliding` for types 938-945:
`Collision.CheckAABBvLineCollision(target, Center, Center + velocity * 6, 10 * scale)`. The
velocity is shootSpeed 2.1 toward the cursor and the player faces the cursor's side.

- `attack` (id 66) aims forward; 7 actions appended after `use summon item` (ids 86-92): up-forward,
  up, up-back, back, down-back, down, down-forward, relative to the facing. Relative because it
  keeps `attack` meaning what it meant and covers all 8 absolute directions in every state.
  `COMBO_ACTIONS` ids shift by 7 (ablation knob). Masks: all = `attack`'s.
- The player turns to the aim's side when a use starts (up/down keep the facing; a running use
  ignores the action, as before). Stab: unit aim vector in Q16 (diagonals 46341/65536), segment
  test ported exactly in integer arithmetic (`fid_line_hits` in `fid.h`: broad AABB, then the
  target corners in the strip and its edges crossing the strip's long edges; like the original
  it misses a target that wholly contains the strip). This also replaces the old box for the
  forward stab: the box added 5 px at both ends, so forward reach is now 42 px past the centre
  (fid_test reach probe: 41) instead of 47. Broadswords and tool swings: same arc, timing,
  damage and knockback, on the chosen side.
- Pixel player: F attacks toward the mouse (nearest of 8 directions from the body centre);
  the stab sprite follows the aim (`/tmp/terraria-v10-ui-aimed-stab.bmp` from
  `make check-pixel-v10`).

Tests: fid_test 106/106 (new: 8-direction stab matrix, aimed stab hits / forward misses a bat
in each direction, facing after each aim; `attack up` hits a Demon Eye overhead that `attack`
misses; `attack down-forward` hits a slime below a one-tile ledge that `attack` passes over;
broadsword `attack back` turns and hits a foot-level slime behind that the forward arc misses,
`attack up` = `attack`). Scripted EoC fight 193/200 (unchanged). Determinism / save-load:
selftest and combo_test random streams include the new actions.

### Night probe (B2: scripted fighter at the spawn, one full surface night, 64 worlds)

`tools/v10_night_probe.c`. `horizontal` = V10SurfaceBug's fighter (turn one step, then
`attack`); `turn` = `attack` / `attack back` toward the mob's side (turn and attack in one step,
no vertical aim); `aimed` = the nearest of the 8 aims at the mob's box centre. Deaths/64 (worlds
with a Demon Eye kill, lenses).

| Gear | horizontal, `AIM_ATTACK=0` | horizontal | turn | **aimed** |
|---|---|---|---|---|
| copper shortsword, no armor | 64 (1, 1) | 64 (0, 0) | 64 (0, 0) | **62 (5, 2)** |
| wooden sword + wood breastplate | 62 (24, 17) | 62 (24, 17) | 61 (51, 50) | **60 (53, 50)** |
| iron sword + iron chainmail | 61 (62, 63) | 61 (62, 63) | 42 (63, 118) | **41 (63, 129)** |

`AIM_ATTACK=0` reproduces the B2 numbers exactly. Most of the gain is the turn folded into the
attack (back attacks); the vertical aims add Demon Eye kills with the shortsword (1 -> 5 worlds)
and lenses. Nights stay lethal without iron gear.

## Checks (all run)

selftest 198/198 (knobs on; 193/193 with both off, 99/99 noport, 202/202 `ENV_FX=1`, 198/198
with combos), fid_test 106/106 (102/102 with `AIM_ATTACK=0`), combo_test 33/33 (31/31 with both
off), `check_v10.py` (93 actions), `perf/check_shaping.py` OK, `tools/v10_noport_parity.py` 400,000
steps identical, `make check-pixel-v10` passed. Token identity with both knobs off: all six
sources identical to `7947630` (also noport); with `COMBO_ACTIONS=1` and both off the only
difference is the exact retry skip (and a renamed local). Raw simulation (`tools/sim_throughput`,
64 lanes x 20,000 steps, random legal actions): both off 618k steps/s, held place only 629k,
both on 615k (0.99x; the action mixes differ).
