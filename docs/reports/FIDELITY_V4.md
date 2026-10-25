# v4 — core Terraria fidelity and fresh measurements

Current environment: `TerrariaLite-v4`, **73 actions, 2961 observations,
32 achievements, 31 inventory types, 19 recipes, 3000 actions per episode**.
Item/recipe/achievement universe and reward weights are unchanged from v3.
Geography, mobs and loot remain seed-dependent. Historical [v3 results](ITERATION_2026_10.md)
and their JSON are preserved; cross-version scores are different tasks.

## Corrected mechanics

- Body collision is now **2 columns × 3 rows**, anchored at the left feet cell.
  Movement, headroom, one-tile step-up, spawning, rope contact, melee/contact
  damage, chest proximity and crafting proximity account for the entire body.
  Either foot can support the player; a narrow one-cell shaft no longer fits.
- Natural trees are pass-through and non-opaque. Walking through them yields
  nothing; axe chopping still fells the connected trunk above the cut. Crowns
  are decorative, not separately mineable; ground supporting a trunk cannot
  be mined until the trunk is removed. Placed wood remains solid and opaque.
- Workbenches, furnaces and anvils are pass-through. Workbenches/anvils support
  landing from above and permit drop-through, like platforms. A solid tile
  under the other foot still supports the body.
- The base jump reaches six tiles. Default safe fall distance is 25 tiles,
  with ten damage per additional tile, reduced by the simplified Classic-mode
  defense rule (half defense rounded up, preserving odd-defense protection).
  Life Crystals grant 20 HP each, up to **400 HP**.
- Reach covers all twenty cells in a 4×5 rectangle: fourteen border targets
  plus six body targets. The latter allow chopping an overlapped trunk or
  placing rope/torches; solid placement inside the body is illegal. This is
  geometric access, not a strategic action abstraction.

Primary evidence: installed `Terraria.exe` constants were inspected using
[tools/terraria_fidelity_audit.py](../../tools/terraria_fidelity_audit.py). The real
hitbox is **20×42 pixels**; a 2×3-tile envelope is our integer-grid approximation,
not a claim that Terraria's hitbox is 32×48 pixels. Original Terraria sources
also document [trees](https://terraria.wiki.gg/wiki/Tree),
[6.27-tile base jumping](https://terraria.wiki.gg/wiki/Jump_speed),
[fall damage](https://terraria.wiki.gg/wiki/Fall_damage),
[Life Crystals](https://terraria.wiki.gg/wiki/Life_Crystal) and
[Classic defense](https://terraria.wiki.gg/wiki/Defense).

The SDL avatar now composites the original **40×56 sprite frame** without the
previous 26×37 downscale. Camera, terminal body, reach hit targets, keyboard
bindings and hearts (20 HP per heart) were updated. Assets are loaded from the
local installation; held tools now follow the interpolated body's center
symmetrically in either facing direction. No original art is redistributed.
Cropping, palettes and
lighting remain simplified, not pixel-identical Terraria rendering.

## Simulator cost and exact optimization

M5 Pro, 48 GiB, active desktop, no training jobs during these probes.
Three repeats of 262,144 transitions, 64 worlds, legal uniform actions,
including mask/step/observation and subsequent resets. Python uses four native
workers and float32 encoding; C and Python use different samplers, so compare
within each harness. Full neural training is not included.

| Version | Single-thread core steps/s | Native batched steps/s | Bytes/world |
| --- | ---: | ---: | ---: |
| Frozen v3 | 1,205,631 | 1,057,238 | 38,712 |
| v4 before station-mask reuse | 931,124 | 915,452 | 38,712 |
| v4 optimized | 1,282,499 | 982,691 | 38,712 |

The larger body expanded crafting neighborhoods, which were repeatedly scanned
for each recipe. The legal mask now scans once and shares an exact station
bitset across recipe checks: **1.38× core / 1.07× batched** speedup on the same
v4 task. Both implementations produce the same digest over **27,913 transitions**.
There is no additional per-world storage and no approximated simulation rule.

Optimized v4's batched workload is about **7.1% slower than v3**, while the C
workload is 6.4% faster. Actions and trajectories changed between versions;
these are workload costs, not strict optimization speedups. Raw timing samples,
native/source hashes and a separate uncached v4 snapshot are preserved locally.
The final held-item alignment is a later renderer-only edit; the measured
simulator sources/native library and training implementation remain unchanged.

## Learning remeasurement

The rules are frozen during training. Six fresh runs compare plain shared-trunk
MLP PPO and independent actor/critic MLP PPO, each at **4,194,304 transitions**
with seeds 101/202/303: **25,165,824 transitions** total. No expert cloning,
demonstrations, prerequisite shaping, curiosity or strategic masks.

Matched settings: 64 environments × 128 steps, four epochs/four minibatches,
gamma .999, GAE lambda .95, entropy .01, LR .0003 linearly annealed, six Torch
CPU threads. At most three concurrent training jobs; wall times include contention
and validation, not dedicated-machine ceilings. Independent trunks have more
parameters (**3,596,362 vs 1,817,162**)/compute, so this compares methods at equal
transitions, not equal FLOPs.

Validation uses worlds 2,000,001–2,000,128, sampler seed 54321, sampled legal
actions, 3000-action limit. Selection is highest validation mean achievement
count, with ties resolved by lower death rate, fewer steps, then run name.
A fresh reserved test split, **4,000,001–4,000,128**, is evaluated once after
selection. It must not be reused for tuning. Seeds do not randomize the item
or achievement universe.

Final fixed-budget validation results (mean ± sample SD across three training
seeds; death rate averaged across seeds):

| Method | Achievements / 32 | Death rate | Mean wall time including validation |
| --- | ---: | ---: | ---: |
| Plain shared-trunk MLP PPO | **10.17 ± 0.15** | 8.6% | 4.80 min |
| Independent actor/critic PPO | **10.32 ± 0.45** | 1.6% | 7.27 min |
| Uniform legal random | 4.84 | 92.2% | Not a training run |

| Matched training seed | Plain MLP | Independent trunks | Difference |
| --- | ---: | ---: | ---: |
| 101 | 10.000 | 10.836 | +0.836 |
| 202 | 10.227 | 10.125 | −0.102 |
| 303 | 10.289 | 9.992 | −0.297 |

The independent variant gains only **0.146 achievements on average**, loses on
two seeds and wins on one, with roughly **1.51× wall time and 1.98× parameters**.
There is no convincing v4 evidence to promote it as the default method.
Its lower death rate is useful secondary evidence, not proof of proficiency.
Three seeds are exploratory, not a precise algorithm leaderboard. Plain MLP
remains the default; both variants remain supported.

Validation selection picked **independent trunks, seed 101, step 4,194,304**
from 24 checkpoints. On the one-time reserved test it scored **10.828/32**,
with **1/128 deaths (0.8%)**, median/max 11, and workbench 128/128. Wooden swords
were crafted in 109/128 worlds. The test split is now consumed. Selection and
checkpoint/source hashes were saved before this test; no tuning used its results.
All curves, final rates, timings, provenance and the selection are in
[FIDELITY_V4.json](FIDELITY_V4.json).

### What the methods now fail to learn

**All six final policies collected stone in 0/128 validation worlds**, and none
crafted a furnace or reached the ore ladder. They reliably learn surface
harvesting, basic placement, slimes, chests, healing and rope. This is far from
environment saturation. The selected policy's test has the same surface-only
profile; it is not proficient underground.

The seed-101 plain policy's peak wood averages 11.94 (max 15); the independent
policy averages 19.74 (max 44). Both have peak stone/ore **zero** in 128 inspected
validation worlds. The independent policy's gain chiefly comes from collecting
enough extra wood to craft a wooden sword, not deeper mining. Its under-left
and under-right mining actions remain legally available in all worlds, but
their mean choice probabilities when legal are only **2.9% and 3.8%**; plain
PPO uses them at **1.4% and 0.6%**. Furnace crafting is never legal because the
necessary resources are never acquired, not because of a strategic mask.

The likely immediate barrier is multi-action digging/navigation plus sparse
exploration/credit assignment: removing one underfoot cell leaves the other
foot supported. A focused fixture digs a twenty-row two-wide shaft safely and
crafts a furnace from its stone, proving the primitive mechanics work. It is
test-only code, never a demonstration given to PPO. These explanations are
inferences from inventory/action evidence; several rules changed together, so
this study does not isolate the width change's entire causal effect.

Next learning work should keep v4 rules fixed and compare longer budgets,
generic spatial encoders and exploration/temporal-credit settings. The current
4M architecture comparison does not establish which of those will solve this.

### Training throughput is not simulator throughput

Plain PPO averages **191.6 s optimization + 73.3 s collection**, versus **310.1 s
+ 105.5 s** for independent trunks; remaining wall time includes validation and
bookkeeping. Collection includes policy inference and rollout handling, not
just C stepping. PPO optimization alone uses roughly **67–71% of wall time**.
The simulator remains fast and bounded; the dominant measured training phase
is neural optimization on CPU, not file I/O or added per-world memory. Isolated
1M-step/s simulator numbers must not be presented as end-to-end training rates.

Three completed provisional runs (12,582,912 transitions) and two interrupted
pilots were archived after a final source check corrected odd-defense rounding.
They are excluded from the matched comparison and model selection. Their
pre-release v4 metadata does **not** make them compatible with the final rules;
use their matching frozen snapshot if inspecting them. No reserved test data
was used before that correction. All headline timings/results use the final rules.

## Verification and regression gates

- `make check`: 100-seed invariants; focused full-body/headroom/support/contact,
  pass-through trees/furniture, complete reach, shifted key binding, placement,
  six-tile jump, 25/26/27-tile falls and two-foot shaft/furnace reachability;
  24,000 arbitrary light edits
  exactly match the independent reference propagator.
- `python -m terraria_lite.ppo_selftest`: 64,000 scalar/native transitions,
  1/2/4/8 workers, exact raw/flat encoding, architecture reload/gradient checks,
  and recurrent/GAE episode boundaries.
- AddressSanitizer/UndefinedBehaviorSanitizer pass mechanics, fidelity and light.
- `make check-pixel`: all 22 tile/31 inventory textures, three armor variants,
  tree chopping/axe display, recipe/inventory hit targets. Before/after rendered
  fixtures were visually inspected; 72 original PNGs and assembly hash audited.
- Gym registration, C rule/geometry queries and old-checkpoint rejection pass.
  Old checkpoints/tapes require their frozen version, not dimension-only loading.
- A fixed seed-9 sampled replay earns 11 achievements in 3000 actions; Python
  and SDL agree exactly on steps, HP, achievement mask and return. It was not
  chosen by a best-of sweep. [tools/verify_replay.py](../../tools/verify_replay.py)
  records this check and the tape hash.
- Compare speed only after exact parity, with unchanged samplers and isolated
  repeats. Treat a >15% same-task median slowdown as a profiling trigger, not a
  flaky hard CI gate. Compare PPO with matched budgets and multiple training seeds;
  do not interpret a one-seed bump or cross-version count as an algorithm win.

## Remaining intentional approximations

This is not a faithful Terraria port. Movement/gravity/cooldowns are coarse
action ticks, not pixel velocities; no variable held-jump timing, slopes,
liquids or separate foreground/background storage. Trees are short and yield
one wood per trunk cell. Stations still occupy one cell rather than real
multi-tile footprints; placement anchoring and reach are simplified. Player
glow and local partial observations remain the benchmark's rules. Mobs use
bounded one-cell approximations, not full Terraria AI/hitboxes. Chests, armor,
loot, crafting and achievements remain a reduced fixed universe.

These changes fix central collision/interaction mismatches without adding a
new content universe or task-specific policy machinery.

## Reproduction and local artifacts

Study root: `experiments/fidelity-v4-20261010.5spuaF/`. Frozen `v3`, `v4-uncached`
and optimized `v4` sources/packages are retained there. Policies, protocols,
curves and per-world records remain in this ignored local directory.
The selected policy is `selected/model.pt`; its ready-to-watch tape is
`selected-demo.tape`. No training jobs remain running after handoff.

```sh
make -j8 all lib terraria-px check check-pixel
.venv/bin/python tools/iterate_ppo.py --out NEW_DIR --seed 101 --architecture mlp --steps 4194304 --threads 6
.venv/bin/python tools/measure_fidelity.py --roots STUDY/v3 STUDY/v4-uncached STUDY/v4 --out NEW_BENCHMARK.json
./terraria-px --watch experiments/fidelity-v4-20261010.5spuaF/selected-demo.tape
.venv/bin/python tools/fidelity_evidence.py --study experiments/fidelity-v4-20261010.5spuaF --out FIDELITY_V4.json
```
