# v8fid: Terraria behaviour ports on top of v8

A copy of `variants/v8` with five independent compile-time fidelity knobs. Each knob
replaces one simplified mechanic with a port of the real Terraria 1.4.4 behaviour
(tModLoader 2026.08). The ports were written in C from the decompiled
`Terraria.NPC`, `Player`, `Collision`, `Item`, `WorldGen`, `HitTile` and `Projectile`
classes; no game code or files are in this repository. Each port's comment names the
method it follows.

With every knob at 0 the build is v8. `build-v8fid-off` and v8 `o3t2-inv` produce the
same world hash, rollout hash and state size in `tools/v8_probe.py` and
`tools/v8fid_probe.py` (`docs/reports/FIDELITY_V8FID_2026_11.md`).

| Knob | Default | Replaces |
|---|---|---|
| `FID_MOBS` | 0 | the grid slime/bat AI, with real slime and bat AI, sub-tile NPC bodies and real stats |
| `FID_COMBAT` | 0 | v8's fixed attack, damage and hurt cooldown, with real damage, i-frames, NPC immunity, knockback and sword hitboxes |
| `FID_PHYSICS` | 0 | the one-cell grid player, with a fixed-point 20x42 px player that runs, jumps with variable height and collides |
| `FID_MINING` | 0 | the fixed mining cooldown, with pick power vs. tile, hit counters and tool use time |
| `FID_TREES` | 0 | 4-6 (x `TREE_HEIGHT_PCT`) tile trunks and one wood per trunk tile, with real forest tree heights and wood drops |

v8's knobs (`ORE_PCT`, `TREE_HEIGHT_PCT`, `INV_LOG`, `VIEW_W/H`, `WORLD_W`) still apply.
Stations stay single cells and there are no liquids. Recipes, rewards, achievements and
the action set (count and names) do not change.

## Time scale

The knobs that run in game ticks (mobs, combat, physics, mining) advance **4 real 60 Hz
ticks per agent action** (`FID_TICKS`). The action's input is held for those 4 ticks, so
one action lasts 1/15 s and a 3000-step episode is 200 s of game time. Knobs that are off
keep v8's one-update-per-action rules. Cooldowns that a port replaces are counted in ticks.

## Units

Positions and velocities are Q16.16 fixed-point pixels (`fix_t`; 16 px per tile), the
same units Terraria uses in floats. All arithmetic is integer, so runs are deterministic
and save/load is still a byte copy of `Env`. `fmul` rounds products to nearest, symmetric
about zero, so left and right motion stay mirror-exact. Tile collision
(`include/fid.h`) ports `Collision.TileCollision`, `SolidCollision` and `CanHit`; there
are no slopes or half bricks in the grid world. It scans only the tiles that overlap the
moved box. This gives the same result as the real code's wider scan, and the
`tools/v8fid_probe.py` hashes were checked to be identical before and after the change.

## FID_MOBS: Blue Slime and Cave Bat

**Stats** (`NPC.SetDefaults`, types 1 and 49):

| | life | damage | defense | knockBackResist | hitbox |
|---|---|---|---|---|---|
| Blue Slime | 25 | 7 | 2 | 1.0 | 24x18 px |
| Cave Bat | 16 | 13 | 2 | 0.8 | 22x18 px |

Contact damage applies when the NPC's hitbox overlaps the player's 20x42 px box
(`Player.Update_NPCCollision`). Without `FID_PHYSICS`, that box is centred in the
2x3 grid body.

**Slime** (`NPC.AI_001_Slimes`, type 1):
- While grounded (velocity.Y == 0), `ai[0]` counts up 1 per tick, or 2 when the slime is
  aggressive.
- It hops at `ai[0] >= 0`, at -1000 and at -2000, then resets `ai[0]` to -1120, -2120 and
  -200. The third hop is the big jump.
- Hop velocities: vy -6, vx += 2·dir for the two small hops; vy -8, vx += 3·dir for the big one.
- Grounded gaps between hops are 120, 120 and 200 ticks when passive and half that when
  aggressive.
- Ground friction is x0.8. In the air the slime steers 0.2/tick toward its direction, up to |vx| 3.
- Faces the player on spawn and, when aggressive, before each hop.
- Reverses after a big jump that went nowhere.
- Aggressive means damaged, or below `Main.worldSurface`, whose stand-in is the row under
  `SURFACE_MAX`. v8 has no night, so it is always day.

**Bat** (`NPC.AI` aiStyle 14, type-49 branch):
- No gravity. It passes through platforms.
- Re-targets the player every tick.
- Accelerates 0.1/tick toward the player horizontally (cap |vx| 4) and 0.04/tick vertically
  (cap |vy| 1.5), with the real asymmetric slowdown when moving the wrong way.
- Bounces off tiles at -0.5x velocity, with minimum speeds of 2 (x) and 1 (y).
- After 200 ticks without line of sight it runs the real `ai[1]`/`ai[2]` wander.

NPC update order (`NPC.UpdateNPC_Inner`): AI, immunity countdown, gravity (0.3, cap 10),
|vx| < 0.005 → 0, then tile collision. Collision sets vy to 0.01 on a ceiling hit, records
collideX/collideY, and moves the NPC.

**Unchanged from v8:** spawns (every 120 actions, 8-14 columns away), the despawn radius,
initial placements and gel drops. Real NPC spawning is not ported. The observation keeps
v8's four entity channels per cell. The phase channel is the slime's time to its next hop
or the bat's line-of-sight timer, in 30-tick bins.

## FID_COMBAT

**Weapons.** Values from `Item.SetDefaults`. v8's damage table was already the real one.

| weapon | damage | useAnimation | knockBack | style |
|---|---|---|---|---|
| Copper Shortsword | 5 | 13 | 4 | stab projectile |
| Wooden Sword | 7 | 20 | 5 | swing |
| Copper Broadsword | 9 | 21 | 5.5 | swing |
| Iron Broadsword | 12 | 20 | 5.5 | swing |
| Silver Broadsword | 14 | 20 | 6 | swing |
| Gold Broadsword | 15 | 18 | 6.5 | swing |

**Attack.** One action starts a use: `itemAnimation = useAnimation`. The use plays out
over the following ticks whatever the next actions are. `attack` is legal again once the
animation ends.

**Swing hitbox.** `ItemCheck_GetMeleeHitbox` for useStyle 1, with item locations from
`ItemCheck_ApplyUseStyle`. It uses the dedicated server's 32x32 item frame:
- first third of the swing: a 64x44 px box overhead (it also reaches behind the player);
- middle third: 32x32 px in front, at head height;
- last third: 44x35 px low in front.

**Melee hits** (`ItemCheck_MeleeHitNPCs`):
- Each NPC can be hit once per swing (`NPC.immune = itemAnimation`).
- After a hit, `attackCD = max(1, itemAnimationMax·0.33)`.
- A hit needs `Collision.CanHit` line of sight.

**Shortsword stab** (`Projectile.AI_161_RapierStabs`):
- The projectile centre starts at the player centre and advances 2.1 px/tick (ai[0] 1-15).
- It collides along 6 velocity steps, line width 10. Here that line is approximated by
  an axis-aligned box.
- Each NPC is hit once per stab. The stab reaches about 47 px past the player's centre.

**Damage to NPCs** (`NPC.HitModifiers.GetDamage`):
- `Main.DamageVar` applies ±15% (integer-exact, `Math.Round` half to even).
- Then subtract defense·0.5, with a minimum of 1.
- Crits (4% base melee chance) double the damage.

**Knockback on NPCs** (`NPC.StrikeNPC`):
- kb x1.4 on crits.
- If damage·10 > lifeMax, velocity is set toward the hit direction up to kb, and vy
  += −0.75·kb (−0.5·kb for the bat). This branch ignores knockBackResist.
- Otherwise velocity is (kb·dir·resist, −0.75·kb·resist).
- Without `FID_MOBS`, a knocked-back grid mob is shoved one cell.

**Damage to the player** (`Player.Hurt`, `HurtModifiers.GetDamage`):
- DamageVar, then `(int)max(dmg − defense·0.5, 1)`.
- `immuneTime` is 40 ticks (20 if the hit did 1 damage). It replaces v8's 8-action
  `hurt_cd`.
- Knockback velocity is (4.5·dir, −3.5) with fallStart reset.
- Without `FID_PHYSICS`, the grid body is pushed 5 cells, one per action. That is the
  distance the physics port carries this velocity on flat ground (fixture test: 5.05 tiles).
- Fall damage also goes through Hurt: i-frames, no variance.

The real NPC stats (damage 7 and 13, defense 2) are used whenever `FID_MOBS` or
`FID_COMBAT` is on.

## FID_PHYSICS

`Player.Update` defaults:

| constant | value |
|---|---|
| gravity | 0.4 |
| maxFallSpeed | 10 |
| jumpHeight | 15 ticks |
| jumpSpeed | 5.01 |
| maxRunSpeed / accRunSpeed | 3 |
| runAcceleration | 0.08 |
| runSlowdown | 0.2 (half in the air) |
| hitbox | 20x42 px |
| Cloud in a Bottle | jump = (int)(15·0.75) = 11 ticks |

Per tick, in this order:
1. `HorizontalMovement`.
2. `JumpMovement`: a held jump re-applies −5.01 for up to 15 ticks; a new jump needs the
   key released first.
3. Gravity.
4. `Collision.StepDown` when vy == gravity, which follows 1-tile drops.
5. `Collision.StepUp` when vy ≥ gravity and Down is not held, which climbs 1-tile steps.
6. `DryCollision` / `TileCollision`, with solid-top tiles passable while holding Down.
7. World edges.
8. The real fall check: on landing (vy == 0), tiles fallen past 25 from `fallStart` cost
   10 hp each.

Measured: a full jump rises 97.9 px (6.1 tiles); a one-action tap rises 42.6 px (2.7 tiles).

**Inputs.**
- `left`/`right` hold that direction for the action's 4 ticks.
- `jump` holds Jump. It continues a held jump if one is in progress; otherwise it is a
  fresh press.
- A held jump survives `left`/`right` actions while its jump ticks last (running jumps).
  Any other action releases it.
- `drop` holds Down (falls through platforms).
- `climb up`/`climb down` hold Up/Down. On a rope this is a simplified `pulley` port:
  - the hitbox snaps to the rope column;
  - no gravity;
  - Up accelerates −0.2/tick (−0.02 past 3, cap 8) while rope continues above the head;
  - Down accelerates +0.2/tick (+0.1 past 3);
  - no input damps by x0.7;
  - left, right or jump leave the rope.
- Facing follows the last left/right input. It is locked during a sword swing
  (useTurn = false).

**Mask.** `left` and `right` are always legal. `jump` is legal when grounded, with an
unused cloud jump, or while a jump is held. `climb` is legal when the centre column
touches rope. `drop` is legal when standing on a solid-top tile.

**Grid anchors.** `px` is the left of the two columns nearest the hitbox centre and `py`
is the row of its bottom pixel. Reach targets, light, depth and achievements still use
`px`/`py`. Placing a solid block is refused when it overlaps the real hitbox.

**Observation.** Four status entries are added before the entity block:
- sub-tile x: hitbox centre within the two body columns, 0.25-0.75;
- sub-tile y: feet within the feet row, (0, 1];
- vx/3;
- vy/10.

`jump` reports Player.jump/15.

## FID_MINING

**Tools.**

| tool | power | useTime |
|---|---|---|
| Copper Pickaxe (start) | 35 | 15 |
| Iron Pickaxe | 40 | 13 |
| Gold Pickaxe | 55 | 17 |
| Copper Axe (for trees) | axe 7 → (int)(7·1.2) = 8 per hit | 21 |

The agent has no item switching, so the mine action uses the real starting Copper Axe on
tree trunks and the best owned pickaxe elsewhere.

**Per hit** (`Player.GetPickaxeDamage`):
- dirt takes 2x pick power;
- torches and mushrooms (`tileNoFail`) and rope (`tileRope`) break in one hit;
- every other tile takes pick power.

Damage accumulates in a `HitTile` slot, and the tile breaks at 100. A failed hit on grass
turns it into dirt (`WorldGen.KillTile(fail)`). After every hit, `HitTile.Prune` ages all
slots and decays their damage by 2/5/7/10 once their 60-hit lifetime is below 48/36/24/12.

Holding the mine action uses the tool every `useTime` ticks; `toolTime` counts down every
tick whatever the action. The cooldown mask gate is gone. The observation adds the last
dug tile's accumulated damage/100, and `mine_cd` reports toolTime/21.

Hits per tile:

| tile | copper | iron | gold |
|---|---|---|---|
| dirt | 2 | 2 | 1 |
| grass | 2 | 2 | 2 |
| stone, ores, wood blocks | 3 | 3 | 2 |
| torch | 1 | 1 | 1 |
| tree (copper axe) | 13 | 13 | 13 |

Stone with the copper pick takes 31 ticks (8 actions); a tree takes 253 ticks (64 actions).
No tile here needs more pick power than the copper pick has, in the real game as here.

## FID_TREES

**Heights.** `WorldGen.GrowTree` draws trunk height from `genRand.Next(5, 17)`: uniform
5-16 tiles. The 5-wide column up to height + 4 must be empty (`EmptyTileCheck`).
`TREE_HEIGHT_PCT` is ignored.

**Wood** (`WorldGen.KillTile_GetTreeDrops`):
- Each tree tile drops 1 wood, plus 1 more if `genRand.Next(100) < axe` (Copper Axe: 7)
  or `rand.Next(3) == 0`. That is 1.38 wood per tile. The decompiled code uses the internal
  axe value (7), not the wiki's axe-power/175.
- Tree tiles include branches: 2 in 10 per side on each inner trunk tile, never on two
  consecutive tiles of a side.
- They also include 1-2 roots when the base is cut.
- Branches and roots are sampled at felling, because the grid keeps single-column trunks.
- Fixture: 400 worlds, mean trunk 10.4 tiles, 20.1 wood per tree.

v8's canopy leaves, felling the whole trunk above the cut and the tree-ground rule are
unchanged.

## Builds

All builds use the v7 fast-path Makefile. Each build records its flags in `$(BUILD)/variant`.

    B="-DORE_PCT=300 -DTREE_HEIGHT_PCT=200 -DINV_LOG=1"   # v8 o3t2-inv base
    T="-DORE_PCT=300 -DINV_LOG=1"                         # FID_TREES replaces tree height
    mk() { make -C perf/v7 V7=$PWD/variants/v8fid LIGHT_WINDOW=1 BUILD=$1 VARIANT="$2"; }
    mk build-v8fid-off       "$B"
    mk build-v8fid-mobs      "$B -DFID_MOBS=1"
    mk build-v8fid-combat    "$B -DFID_COMBAT=1"
    mk build-v8fid-physics   "$B -DFID_PHYSICS=1"
    mk build-v8fid-mining    "$B -DFID_MINING=1"
    mk build-v8fid-trees     "$T -DFID_TREES=1"
    mk build-v8fid-mobcombat "$B -DFID_MOBS=1 -DFID_COMBAT=1"
    mk build-v8fid-all       "$T -DFID_MOBS=1 -DFID_COMBAT=1 -DFID_PHYSICS=1 -DFID_MINING=1 -DFID_TREES=1"
    TERRARIA_LITE_LIB=$PWD/perf/v7/build-v8fid-all/libterraria.so ...

`ENV_VERSION` stays 7. `FID_PHYSICS` and `FID_MINING` lengthen the status vector, and the
library reports the new size and entity offset (`tl_status_len`, `tl_status_entity0`).

## Checks

    sh tools/v8fid_test.sh                     # fixture tests per knob set (C)
    PYTHONPATH=python uv run python tools/v8fid_probe.py \
        perf/v7/build-v8-o3t2-inv/libterraria.so perf/v7/build-v8fid-*/libterraria.so
                                               # parity, determinism, save/load
    cc -O2 tools/sim_throughput.c -o /tmp/sim_throughput && (cd perf/v7 && /tmp/sim_throughput -r 3 -s 20000 LIB...)
