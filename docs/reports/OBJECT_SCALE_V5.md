# Native-scale object footprints — v5 preview

Implemented and verified on 2026-10-11 in a **separate playable preview**.
The main checkout remains v4; the earlier five-seed credit study is complete.
The simulator cost gate passes, including a no-concurrent-RL confirmation in
[CRAFTING_BOTTLENECKS_2026_10.md](CRAFTING_BOTTLENECKS_2026_10.md). The original learning
cohort was stopped at the user's reporting deadline.
[Partial results](FOOTPRINT_LEARNING_PARTIAL_2026_10.md) include completed 16M
runs, strong plain-PPO gains and weaker spatial/recurrent scores. The full
five-seed study was subsequently [completed and audited](FOOTPRINT_LEARNING_2026_10.md)
on 2026-10-12: MLP mean 13.79→17.32/32, targets 17.68→17.07 and memory
17.76→17.05. Learning non-inferiority is inconclusive for all packages; v5 is
not promoted. Proficiency must not be inferred from simulator speed alone.

## Corrected scale

Previously the original multi-tile sprites were stitched together and shrunk
into a single simulator cell. The preview now gives them matching physical and
visible footprints, using the original installed Terraria pixels:

| Object | Old footprint | Preview footprint | Primary reference |
| --- | --- | --- | --- |
| Chest / opened chest | 1×1 | 2×2 | [Chests](https://terraria.wiki.gg/wiki/Chests) |
| Life Crystal | 1×1 | 2×2 | [Life Crystal](https://terraria.wiki.gg/wiki/Life_Crystal) |
| Furnace | 1×1 | 3×2 | [Furnace](https://terraria.wiki.gg/wiki/Furnace) |
| Campfire | 1×1 | 3×2 | [Campfires](https://terraria.wiki.gg/wiki/Campfires) |
| Work Bench | 1×1 | 2×1 | [Work Benches](https://terraria.wiki.gg/wiki/Work_Benches) |
| Iron Anvil | 1×1 | 2×1 | [Pre-Hardmode Anvils](https://terraria.wiki.gg/wiki/Pre-Hardmode_Anvils) |

Torches, ropes, platforms and mushrooms stay single-cell. Mobs and trees are
unchanged; this is not an attempt to reproduce every Terraria collision or
support rule at once. Existing unanchored placement remains; objects require
empty space across their full footprint, but this change does not introduce a
new furniture-support strategy constraint. Generated objects do have floors.

## Mechanics and human UI

- One placed item creates one complete object. The target is its bottom-left
  anchor. Full-footprint bounds and occupancy are checked before any writes.
- Mining any component removes the complete object and yields exactly one
  item. Adjacent identical objects remain distinct; four crystal quadrants do
  not create four Life Crystals.
- Looting a chest changes all four components once. Interaction can use any
  adjacent visible component, not just the old anchor. Loot tables/counts and
  the number of generated chests/crystals are unchanged.
- Stations are detected across their full footprint. They remain pass-through;
  benches/anvils retain their one-way top collision. Campfires remain one light
  source rather than multiplying brightness by six.
- Placement masks check only visible obstacles; unlit occupied cells permit
  attempts instead of revealing hidden terrain. All checks remain physical/
  epistemic legality, not strategy.
- The pixel frontend displays native multi-tile sprites, full-size placement
  ghosts and footprint outlines. Hover legality now uses the same mask as the
  simulator. Mining outlines describe whole-object removal. The Life Crystal
  hint correctly says 400 HP maximum.
- Inventory icons remain icons, not world-size sprites. Original assets are
  loaded from the local Terraria installation; none are included in the patch.

## Measured cost

Five interleaved v4/v5 pairs, alternating order, each with three repetitions
inside each harness: 262,144 transitions, 64 environments, uniform legal
actions, mask/step/observation and subsequent resets. Native batching uses four
workers. **The frozen PPO jobs were running concurrently on the active M5 Pro
desktop**, so these are contended comparative measurements, not isolated maxima.

| Workload | v4 median | v5 median | Interpretation |
| --- | ---: | ---: | --- |
| Single-thread C core | 1,044,998 steps/s | 1,049,764 steps/s | Essentially unchanged |
| Native batched rollout | 685,117 steps/s | 676,897 steps/s | About 1.2% lower, within noise |

The median paired v5/v4 ratio was 1.005 for core and 1.006 for batching; batch
pair ratios ranged 0.955–1.056. Ratios of medians and medians of paired ratios
are different summaries. These results show **no detected large slowdown**,
not a statistically established speedup or a promise of zero cost.
The predeclared provisional gate allowed at most 10% loss in median paired
native throughput, and passed. Repeat in isolation after the main study ends.
Changed game trajectories mean this is a workload comparison, not identical-
trajectory optimization parity. Frontend-only refinements followed timing;
the measured simulator sources did not change afterward.

Env storage: **38,712 → 51,000 bytes** (+12 KiB/world, about 32%). That is
**0.75 MiB extra for 64 worlds**, not 32% more total learner memory. Each cell
has a byte identifying its object's sub-tile frame; there are no new entity
lists, heap allocations or physics loops over growing object populations.
Actions stay **73**, observations **2961**, tile taxonomy **24 including
unknown**, and achievements **32**. Neural-network dimensions do not increase.
These probes do not measure end-to-end PPO optimization speed.

## Verification

- Existing 100-world mechanics/determinism tests and 24,000 incremental/full
  light comparisons pass.
- New object tests cover atomic placement, all crystal quadrants, one-item
  drops, adjacent-object isolation, world boundaries, hidden obstacles,
  station range, bench support/drop-through, chest component visibility and
  opening, single-source campfire light and observation taxonomy.
- All footprints and floors are consistent in 256 generated worlds, with
  exactly ten chests and eight whole crystals per world.
- 64,000 scalar/native transitions with 1/2/4/8 workers, encoding, legal-support,
  recurrent boundaries, checkpoint reloads and novelty checks pass on v5.
- Pixel fixtures load all 22 original tile types, 31 inventory icons, player
  and three torso armor variants. Native-scale objects and the full furnace
  placement ghost were visually inspected.
- v5's distinct environment version rejects v4 policies/tapes. No old scores
  are relabeled as v5 evidence. All frozen v4 study hashes still match.

## Play / inspect

```sh
experiments/object-scale-v5-20261011.44UmHy/v5/terraria-px --seed 9
```

Preview sources and binaries:
`experiments/object-scale-v5-20261011.44UmHy/v5`.
Raw measurements: `experiments/object-scale-v5-20261011.44UmHy/benchmarks.json`.
Local screenshots: `ui-fixture.png` and `placement-fixture.png` in that study
directory. These are synthetic UI fixtures, not agent proficiency examples.

The tracked [OBJECT_SCALE_V5.patch](../../patches/OBJECT_SCALE_V5.patch) contains the code and
regression tests; `git apply --check OBJECT_SCALE_V5.patch` passes against the
current checkout. It has **not** been applied to the main checkout. This preserves
the completed v4 evidence and lets us review/keep the new task separately.

Original recommendation: the implementation cost warranted a matched fresh
learning comparison before making v5 official. That comparison is now complete
and its test split consumed. Larger furniture requires more free placement
space; larger objects also become easier to see/interact with. The full package
has mixed learner effects, not proven learner-neutrality. Keep it as a fidelity
candidate pending an explicit promotion decision, not an automatic default.
Keep recipe/tool/resource-supply changes separate from this footprint test.
