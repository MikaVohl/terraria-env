# Terraria-Lite v9 — design spec (draft, 2026-11-08)

Status: **brainstorm → spec**. Nothing here is frozen. Decisions marked **[T]**
are tunable: we expect to revisit them after the pilot results in §10, and each
lists what would make us change it. Unmarked decisions are intended to hold.

## 1. Goal

One polished, released environment that is

- **faithful** to early pre-Hardmode Terraria, at reduced scale;
- **unsaturated**: today's best policy should score well below the ceiling;
- **learnable**: our current PPO machinery has a realistic chance at the lower
  three tiers, so the benchmark has a gradient rather than a cliff;
- **fast**: Craftax-class throughput, so 1B-step budgets stay about a GPU-hour;
- a common ground for **RL and LLM agents** (same observation, actions and score).

v8 (ore 3× + trees 2×) is the starting point. It is *not* released separately.

## 2. Decision log

| ID | Decision | Rationale | Tunable? |
|---|---|---|---|
| D1 | Release **one** environment (v9), no separate "Classic" | Avoid shipping a saturated twin; v8 results remain as development history | |
| D2 | Difficulty follows **Terraria's own progression**: depth layers, pickaxe-power gates, night, a boss | Faithful and gives a natural tiered ladder (Craftax's floors, but native) | |
| D3 | **Eye of Cthulhu is the final boss** and the end of the environment; no underworld | Iconic milestone; keeps the world small and the chain learnable | |
| D4 | Difficulty comes from **mobs, night, darkness, distance**, not from starving resources | v7's exact-minimum iron produced an unfair cliff (+0.9 when fixed in v8) | |
| D5 | Resource supply: **realistic density with a guaranteed per-layer minimum** (fair, not generous) | Every world completable; no 3× abundance | **[T]** minimums and density, from the oracle audit and pilots |
| D6 | World **128 wide × 128 deep** (v8: 128 × 96), three layers + bedrock | Progression is vertical; the 256-wide test cost 1–6 points | **[T]** depth 112–144; width stays 128 unless pilots say otherwise |
| D7 | Episode length **10,000 steps** (v8: 3,000) | Room for a full day/night cycle plus the boss chain; matches Crafter/Craftax | **[T]** 6,000–10,000, by pilot learning curves |
| D8 | Day/night cycle, start at dawn | Faithful; night spawns create risk and the summon window for the boss | **[T]** cycle length (draft: 1,800 day + 1,200 night steps) |
| D9 | Observation: same 11×9 local view; status block extended (time of day, layer, boss state) | Larger views cost points in v8 | **[T]** a coarse explored-map channel is a prototype option (§7), off by default |
| D10 | **Craftax-style score**: tier weights 1/3/5/8, headline = % of max weighted score | Familiar, deliberate weighting, room at the top | **[T]** weights after pilots, if they induce unwanted trade-offs |
| D11 | **Evaluation is not the training reward.** Training may use any reward; entries disclose prior knowledge | Same separation we already use (recipe shaping vs generic) | |
| D12 | No health term in the score; deaths reported separately | Keeps the score a pure progress measure | |
| D13 | Report alongside the headline: per-tier success, Crafter geometric score, furthest milestone, deaths | Breadth, rare-achievement weight and an LLM-friendly narrative | |
| D14 | Score target bands on the frozen version: random < 5%, PPO-generic at 1B ≈ 25–35%, our best RL ≈ 40–50%, oracle ≥ 95% | Avoid both Crafter's compression and Craftax's no-gradient cliff | **[T]** the content and parameters move to hit these, not the bands |
| D15 | Budgets: pilots at **250M / 1B / 4B**; fix official budget levels afterwards | Measure the curve before choosing | **[T]** final levels |
| D16 | Faithful recipe quantities where they differ from v8 (e.g. iron pickaxe 12 bars, iron chainmail 20 bars) | Faithfulness; small effect on learnability | **[T]** per recipe, if a tier shows no signal |
| D17 | Simplifications kept: single-cell stations, one-cell regular mobs, coarse action ticks, no flowing liquids | Sim speed and observation size | |
| D18 | Every added feature passes a **sim-cost gate**: whole-step throughput ≥ 1/1.5 of v8 on the same hardware | Speed is the reason people adopt the benchmark | **[T]** gate value |
| D19 | Build **tier by tier**, each through the sim-cost and learnability gates (§10) | Never ship a cliff | |
| D20 | King Slime, bows/ranged, potions brewing, NPC housing, extra biomes: **not in v9** | Breadth without depth; keep the chain learnable | Candidates if the ceiling turns out too low |
| D21 | Oracle achievability audit after everything else is decided | Most items are known reachable from v4–v8 | |

## 3. World

### Geometry and layers (D6)

| Rows (draft) | Layer | Contents |
|---|---|---|
| 0 – surface | Sky | Light from the day/night cycle |
| surface (22–38) | **Surface** | Grass, dirt, trees, Blue Slimes (day), Zombies and Demon Eyes (night), surface chests |
| surface+8 – 64 | **Underground** | Dirt/stone mix, copper and iron, Cave Bats, Life Crystals, chests |
| 64 – 125 | **Caverns** | Stone, open cave systems, silver and gold, Skeletons, Cave Bats, **Demon Altars**, chests |
| 126 – 127 | Bedrock | Indestructible |

`descend deep` is replaced by `reach the caverns` (row 64).

### Supply (D4, D5)

Ores by layer (faithful to Terraria's depth ordering):

| Ore | Layers | Guaranteed minimum per world (draft) |
|---|---|---|
| Copper | underground + caverns | enough for 2 swords' worth plus slack (≥ 30 ore) |
| Iron | underground + caverns | anvil + iron pickaxe + chainmail + sword = 5+12+20+8 bars → ≥ 140 ore |
| Silver | caverns | ≥ 40 ore |
| Gold | caverns (lower half) | gold pickaxe 12 bars → ≥ 60 ore |
| Trees | surface | ≥ 150 wood in reach of spawn |
| Demon Altars | caverns | ≥ 2 per world |
| Life Crystals | underground + caverns | ≥ 3 per world |

Density above the minimum is "realistic": roughly v7's vein rate scaled by depth,
not v8's 3×. **[T]** via D5.

## 4. Time

- Day/night cycle (D8). Draft: 1,800 day steps, 1,200 night steps; 10,000-step
  episodes see about 3.3 cycles. Sky light falls to near zero at night.
- Lighting is recomputed only at the two transitions per cycle; tile changes keep
  using the incremental path.

## 5. Mobs

| Mob | Where / when | Behaviour (simplified) | Drops |
|---|---|---|---|
| Blue Slime | surface, day | hop toward player (existing) | gel |
| Zombie | surface, night | walk toward player, contact damage, can step up one tile | — |
| Demon Eye | surface, night | flying, weaving approach, contact damage | **lens** (≈ 1/3) |
| Cave Bat | underground, caverns | erratic flight (existing) | — |
| Skeleton | caverns | walk toward player, more HP and damage than zombies | bone (no use in v9; flavour only) **[T]** drop or drop it |
| **Eye of Cthulhu** | summoned at night only | 3×3 flying boss. Phase 1: hover above, periodic dashes. Phase 2 (< 50% HP): faster repeated charges. Despawns at dawn or if the player dies | **demonite ore** (the boss-kill reward; no further use in v9) |

- Mob cap: 8 → 12 regular mobs plus one boss slot **[T]**.
- Damage and HP scaled to our 100-HP player so that, unprepared, a night is
  dangerous but survivable with a wooden sword and some care **[T]**.
- EoC HP and damage tuned so that iron/gold gear + 2–3 Life Crystals make the fight
  winnable by the oracle at ≥ 90% **[T]**.

## 6. Items, stations and recipes

Existing v8 recipes stay, with the D16 quantity changes. New:

| Recipe | Ingredients | Station | Notes |
|---|---|---|---|
| Suspicious Looking Eye | 6 lens | **Demon Altar** (cavern tile) | Faithful; altar is a fixed, unmineable world tile in v9 |
| Gold chainmail | 25 gold bars | anvil | Optional; adds a tier-3 armor step **[T]** |

New actions: `use summon item` (only legal at night with the eye in inventory and no
boss alive). Crafting actions grow by the new recipes.

## 7. Observation and actions (D9)

- Same 11×9 local view, one-hot tiles (new tile kinds: Demon Altar) and per-cell
  mob kinds (Zombie, Demon Eye, Skeleton, EoC parts).
- Status block adds: time of day (phase + is-night bit), current layer, boss
  present / boss HP fraction, new item counts (lens, eye, demonite).
- Achievement bitmask grows past 32 (u32 → u64).
- Action mask unchanged in spirit: illegal crafts and the summon are masked.
- **Prototype option:** a coarse explored map (e.g. 16×16 cells of 8×8 tiles, each
  cell = explored / solid fraction / station seen). Off by default; tested in pilots
  because return-to-surface and altar-finding are navigation problems.

## 8. Achievements and tiers (D10)

Draft list: 38 achievements. Weighted max = 13×1 + 12×3 + 8×5 + 5×8 = **129**.

| Tier (weight) | Achievements |
|---|---|
| **1 Basic (×1)** | collect wood, collect stone, place block, place torch, place platform, craft workbench, craft wooden sword, collect copper, defeat Blue Slime, open chest, explore 30 columns, climb rope, heal with food or potion |
| **2 Intermediate (×3)** | craft furnace, smelt copper, collect iron, smelt iron, craft anvil, craft metal sword, craft wood breastplate, use Life Crystal, defeat Zombie, defeat Demon Eye, survive a night, reach the caverns |
| **3 Advanced (×5)** | craft iron pickaxe, collect silver, smelt silver, collect gold, smelt gold, craft iron chainmail, defeat Skeleton, return to surface (from the caverns) |
| **4 Very advanced (×8)** | craft gold pickaxe, collect lens, craft Suspicious Looking Eye, summon the Eye of Cthulhu, defeat the Eye of Cthulhu |

Changed from v8's 32: `descend deep` becomes `reach the caverns`; `defeat Cave Bat`
and `double jump` are no longer scored (bats and Cloud in a Bottle stay in the game).
Tier placement is from v8 success rates where we have them **[T]**: an achievement
moves tier if pilots show it is much easier or harder than its tier peers.

Rationale for v8 achievements now in higher tiers: the iron pickaxe is the
current learning frontier (≈ 40% of shaped seeds, 0% generic); gold pickaxe and
chainmail were never reached in v8.

## 9. Scoring and evaluation (D10–D13, D15)

- **Headline:** mean over evaluation episodes of (Σ weights of unlocked achievements) / 129, as a percentage. IQM and bootstrap 95% CIs across training seeds.
- **Always reported:** per-tier success rates, all per-achievement rates, Crafter geometric score, furthest milestone, death rate, budget (environment steps and GPU-hours or API cost).
- **Worlds:** public validation seeds; reserved test seeds evaluated once per frozen configuration (as in v8).
- **Policy sampling:** categorical, fixed sampler seed; masked actions.

## 10. Build plan and gates (D18, D19)

Order: **(a)** geometry + layers + supply → **(b)** day/night + night mobs + lens → **(c)** caverns: skeletons, altars, silver/gold changes → **(d)** Eye of Cthulhu + summon + scoring. One integration branch; each step:

1. Determinism and parity tests (seeded replay, save/load state, Python = C).
2. **Sim-cost gate:** whole-step throughput ≥ 1/1.5 × v8 on the same machine (D18).
3. Scripted or oracle check that the new content is reachable on sampled worlds.

**Pilot trials** after (d): generic and shaped PPO at **250M, 1B and 4B** steps,
2–3 seeds each, γ 0.9999. Read-outs: per-tier curves, the D14 bands, deaths,
night behaviour, whether the minimap option helps navigation.

**Tweak triggers:**

| Observation | Likely tweak |
|---|---|
| A tier shows no learning signal at 1B for any arm | Lower that tier's costs (D16), supply minimums (D5) or mob difficulty |
| Deaths dominate early training | Night mob damage / spawn rate, day length (D8) |
| Lower tiers collapse versus v8 | Episode length (D7), world depth (D6) |
| Agents never find altars | Altar count, minimap option (D9) |
| Throughput below gate | Mob cap, lighting cadence, world depth |
| Scores above the D14 bands | Add D20 content or tighten D5/D16 |

## 11. Simplifications versus Terraria

Single-cell stations; one-cell regular mobs (EoC 3×3); discrete action ticks;
no flowing liquids, underworld, evil biome, NPCs, ranged/magic weapons, or
potion brewing; Suspicious Looking Eye is the only boss summon; demonite has no
use. Tile art and names follow Terraria.

## 12. Open questions

- Should `collect lens` stay in tier 4, or move to tier 3 as a stepping stone?
- Does the boss fight need servant mobs (Servants of Cthulhu) for faithfulness?
- Gold chainmail: include as a tier-3 step or leave out?
- Minimap: prototype only, or default if it helps?

## 13. Implementation notes (first build, 2026-11-07)

Facts of the implementation in `variants/v9/` that differ from, or pin down,
the draft above. Each is marked **[IMPL]**; knobs and defaults are listed in
`variants/v9/README.md`.

- **[IMPL] Altar footprint.** The Demon Altar is a 3x2 object (Terraria's footprint,
  using the existing multi-tile object machinery, like the furnace), not single-cell.
  It is unmineable, non-solid, and emits light 5 so it is visible a few tiles away in
  the dark. Worlds get 2-3 altars, each in a carved 7x4 cavern chamber on a stone floor.
- **[IMPL] Bone.** Skeletons drop nothing (section 5 left "drop or drop it" open).
- **[IMPL] Gold chainmail** is a recipe (25 gold bars, anvil; armor defense 4) with
  **no achievement**, so the section 8 list stays at 38 / max 129 (open question 3).
- **[IMPL] Gold pickaxe** is 12 gold bars + 3 wood (v8: 10 + 4), iron pickaxe 12 + 3,
  iron chainmail 20, all knobs (D16).
- **[IMPL] Training reward is unchanged** (+1 per first unlock, -1 on death); the tier
  weights are evaluation-only (`weighted_score`, D11).
- **[IMPL] Mob numbers** (draft gave none): Zombie 30 HP / 10 damage (walks every other
  tick, steps up one tile), Demon Eye 30 / 12 (flies, weaves +-2 rows around the head),
  Skeleton 50 / 16 (walks 6 of 8 ticks), Slime and Cave Bat as v8. Spawn attempts every
  120 steps, every 60 on the surface at night (50% Demon Eye / 50% Zombie); caverns
  50% Skeleton / 50% Cave Bat; underground Cave Bats. Lens drop 33%.
- **[IMPL] Dawn.** "Survive a night" is awarded on the dawn tick if alive; Demon Eyes
  leave at dawn, Zombies stay until they despawn by distance; the boss despawns.
- **[IMPL] Night light.** Sky light 3 (of 15) at night (dark threshold 2): open surface
  stays barely visible, everything one tile into the ground is dark without a torch.
  Full light recomputes run only at the two transitions per cycle.
- **[IMPL] Eye of Cthulhu.** `src/boss.c`, self-contained (state struct + summon / tick /
  attack / despawn) so a behaviour port of Terraria's AI can replace it. 240 HP; 3x3,
  ignores terrain; hover toward 8 rows above the player, then 3 aimed dashes (2
  tiles/tick, 8 ticks, 6-tick pauses), repeat. Phase 2 at <= 50% HP: 15-tick hover,
  5 dashes at 3 tiles/tick, 3-tick pauses, contact damage 18 (phase 1: 12). Drops 30-87
  demonite ore. No Servants of Cthulhu (open question 2). A scripted fight (iron
  broadsword, iron chainmail, 140 HP, 3 potions, chase-and-swing) wins 194/200 worlds.
- **[IMPL] Boss observation.** Besides present / HP fraction the status block carries
  a phase-2 bit and the boss's clipped relative position (dx/32, dy/32), and the boss
  is drawn in the entity grid regardless of light: the real game's screen is much
  larger than the 11x9 view and the boss is always on it.
- **[IMPL] Entity block** is 8 channels per cell (Blue Slime, Cave Bat, Zombie, Demon
  Eye, Skeleton, Eye of Cthulhu, health, phase); the minimap option (16x16 cells x
  {explored, solid fraction, station seen}) sits before it in the status scalars.
  Explored = the cell overlapped the view window; solid fraction is the true fraction
  of that cell (recounted when the player edits tiles there).
- **[IMPL] Supply.** Ore vein counts use v7's per-row vein rate over each ore's v9
  band; all ores are band-locked (copper and iron underground + caverns, silver
  caverns, gold rows 95-125). Floors are met by extra veins (single tiles only as a
  last resort). Over 512 worlds: copper min 158 / median 281, iron 140 / 192, silver
  70 / 133, gold 60 / 63 (natural generation at v7's rate is usually below the gold
  floor), 2-3 altars, 3-5 life crystals (own pockets; v8 had one per treasure room),
  10 chests (2 surface, 8 rooms alternating underground and caverns).
- **[IMPL] Wood.** Trees are 8-12 tiles tall, 5-10 columns apart; the 150-wood floor
  within 48 columns of spawn is met by growing those trees (max 16), so nearly every
  world sits exactly at the floor (median 150, max 156).
- **[IMPL] Sim-cost gate (D18), M5 Pro, one thread, 64 lanes, uniform legal actions,
  whole step + observation + mask + resets (`tools/sim_throughput.c`).** v8
  (`build-v8-o3t2-inv`) 1.29 M steps/s, v9 1.23 M (0.95x), v9 + minimap 0.98 M
  (0.76x). Both pass the 1/1.5 gate.
