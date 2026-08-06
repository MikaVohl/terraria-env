Inspiration: [Craftax](https://craftaxenv.github.io/)

Plan:
1. Write terraria-lite in C
2. Train PPO on the game
3. Iteratively optimize to run faster and fix exploits
4. Connect an LLM as a benchmark performance
	1. See https://terrariabench.com/

Scope of game:
- **World:** 128 wide × 96 deep, single biome. Surface around y=30, dirt layer, stone layer, ores by depth. Agent sees a local window (Craftax uses 9×7). Vertical layering gives you a depth-gated tech tree for free.
- **Tiles (~12):** air, dirt, grass, stone, tree/wood, copper ore, iron ore, torch, workbench, furnace, placed block, bedrock.
- **Actions (~15):** move L/R, jump, mine in 4 directions, place in 4 directions, and a handful of craft actions. Craftax has 17, so this is comparable.
- **Crafting (~6 recipes):** wood→workbench, stone→furnace, wood+stone→stone pickaxe, copper ore+furnace→copper bar, copper bar+wood→copper pickaxe, copper bar+wood→torch. Tool tier gates what you can mine — hand gets dirt and wood, stone pick gets stone and copper, copper pick gets iron. That gating _is_ the RL structure.
- **Physics, simplified hard:** grid-snapped horizontal movement, gravity as "fall one tile per tick until supported," fall damage past a threshold. No continuous position, no sub-tile AABB. This is the single biggest complexity cut and it costs you real Terraria fidelity.
- **Keep lighting, cut liquids.** If you keep exactly one propagation system, make it lighting — darkness underground is what makes torches meaningful and creates the exploration gradient, and it's a bounded Jacobi relaxation rather than an ordering nightmare.
- **Cut:** mobs, biomes, day/night, hunger, walls, wiring, all liquids. Health exists only for fall damage.

Notes:
- There should be a beautiful terraria-clone for textures when a human is observing the environment
