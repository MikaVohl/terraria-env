# viz: watching a reinforcement learner

A scroll-driven page about the whole project. Everything on it runs live in the browser:

- **The real simulator.** `variants/v8` is compiled to WebAssembly with default knobs, which makes it byte-identical to frozen v7.
- **The real trained policy.** The "targets" actor-critic from the eg15 run `eg15-envopt2b-v8-20261101/build-v8-g0/runs/pot_e1024_max2-2001` (2.1B steps, 25.72/32 on validation), evaluated by `wasm/policy.c`.

```sh
make -C viz serve      # builds viz/terraria.wasm, links viz/textures, serves http://localhost:8777
```

The canonical main checkout on Omarchy is `/home/mika/Projects/terraria-lite`,
backed by `/mnt/storage/data/projects/terraria-lite`. Run the commands here
from that checkout. This browser intentionally uses the default v8 core;
dated v4/v7 studies and newer v9/v10 environment documentation describe
other profiles, not a change to this build target.

The art is Terraria's own. `make -C viz textures` points the gitignored `viz/textures` symlink at a local install's `ExtractedTextures`. The default follows the platform's usual Steam path; pass `TEXTURES=<dir>` for a nonstandard extraction location. Original game textures are never tracked or published in Git, so the page only works on a machine that has the extracted art. If a sheet is missing, loading stops with an error naming the file; there is no substitute art.

On Linux, the default is the local Steam extraction path. Override it when needed, for example:

```sh
make -C viz serve TEXTURES="$HOME/.local/share/Steam/steamapps/common/Terraria/ExtractedTextures"
```

The four `data/policy-*.bin` files are this project's exported float16 policy
weights and are intentionally versioned with the compact training metadata
in `data/run.json`. Original game textures and generated `terraria.wasm`
remain gitignored; rebuilding or transferring them does not publish them.

A Web Worker can't load a module from `file://`, so the page has to be served over HTTP.

## Chapters

| Chapter | What runs |
|---|---|
| Play | You play seed 42. A/D walk, W jump, click a highlighted cell to mine, right-click to place, E cycles the block, F attacks. Crafting is in the bottom-right panel. Time only advances on a step: idle ticks while airborne or on cooldown become real NOOP steps. |
| Agent | The policy takes over the same `Env`. Panels show π(a\|s), V(s), entropy and return. The checkpoint buttons switch between untrained, 134M, 537M and 2.1B. |
| Scale | 256 worlds on N Web Workers. Each worker runs its own wasm instance and its own copy of the policy, with autoreset to consecutive seeds. Aggregates are computed only from episodes finished in the tab. |
| Training | `data/run.json`: the run's validation curve and per-achievement hit rates. |
| One episode → Simulator | Validation seed 23000001, played by the 2.1B policy and recorded lazily. Scrolling advances one step every 22 px. Seeking restores the nearest saved `Env` snapshot (one memcpy, every 25 steps) and replays the recorded actions from there. The panels show the observation encoding, the 83-action masked distribution, reward / V(s) / Gₜ / GAE advantages, the network's forward activations and ∇ log π(aₜ\|oₜ) (a real backward pass in C), and the live `Env` bytes with each step's diff. |
| Plateau | Per-achievement success of the final checkpoint. |

## Files

| Path | Role |
|---|---|
| `wasm/web.c` | Flat wasm API over the core, plus the libc subset it needs. `w_layout()` reports `Env`/`Obs` offsets so the JS never hardcodes them. |
| `wasm/policy.c` | Batched forward for the 256-world grid, and a traced forward + backward for one observation. |
| `wasm/shim/` | Freestanding headers. `sinf`/`cosf`/`logf` are imported from JS as `Math.fround(Math.sin(x))` and so on. |
| `js/` | Page modules: `main.js` (scroll timeline), `play.js`, `grid.js` + `grid.worker.js`, `replay.js`, `lab.js`, `obs.js`, `actrew.js`, `net.js`, `csim.js`, `outro.js`, `terraria.js` (texture loading), `render.js`. |
| `data/` | `policy-<steps>.bin` (float16 weights in `policy.c` blob order) and `run.json`. |

The toolchain is LLVM `clang --target=wasm32` and LLD `wasm-ld`, with no
Emscripten and no sysroot. macOS keeps the Homebrew defaults
`/opt/homebrew/opt/llvm/bin` and `/opt/homebrew/opt/lld/bin`; Linux resolves
both tools from `PATH` (install the distribution's LLVM/Clang and LLD
packages). If `wasm-ld` is absent from `PATH`, the linker directory falls back
to `/usr/bin`; it still needs an installed `wasm-ld`. Existing
`LLVM=<clang directory>` and `LLD=<wasm-ld directory>` make overrides select
a different installation. For example:

```sh
make -C viz LLVM=/usr/bin LLD=/usr/bin
```

## Checks

```sh
make -C viz parity     # wasm vs native (non-LIGHT_WINDOW) build: Env + Obs + mask hashes, 80 worlds + 4 random-legal episodes
make -C viz policies CKPT=<run dir with step-*.pt, curve.json, summary.json>
```

`tools/viz_parity.py` must be compared against a build without `LIGHT_WINDOW`. That patch leaves `Env.light` stale outside the observation window, so observations agree but whole-state bytes do not.

`tools/viz_export_policy.py` re-exports the weights. It then checks the wasm forward pass against PyTorch on 160 observations, using the same float16-rounded weights; the last export gave max |Δlogit| 7.6e-6. The backward pass (`w_policy_trace`) was compared once against `torch.autograd`: ∂ log π / ∂h₂ agreed to 1e-6.

## Display-only liberties

The browser shows the simulator's real state, with three liberties taken for display only:

- **Art follows the frozen v7 pixel frontend** (`experiments/v7-reward-20261017.sGYPqq/variants/v7/src/px_render.c`): same sheets, frame table, crops, slime tints and player layers, in `js/terraria.js`. Trees go one step further: each trunk top wears a whole `Tree_Tops_0` sprite instead of tiled leaf crops. The leaf cells stay in the simulator unchanged.
- **The parallel grid is a map view**, one pixel per tile, coloured with each texture's average colour (like Terraria's minimap).
- **Light bleeds visually** about 4 tiles into solid blocks in the big views, so terrain under the surface isn't a black wall. The observation chapter shows the simulator's own light and darkness.
- **Grid cells keep a minimum brightness** for terrain.
