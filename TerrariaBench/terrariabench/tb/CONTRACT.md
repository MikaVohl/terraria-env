# tb-api-1.0 (draft) — TerrariaBench programmatic track API contract

Frozen per leaderboard. A result is labelled with the API version, the library version (this package + `path.py`
capabilities) and the harness (`tools/terrabot`). Changing any function's semantics, visibility rule or the
pathfinder's capability list requires a new version.

## Components
| Layer | Where | Role |
|---|---|---|
| TerraBot mod | `mod/TerraBot/TerraBot.cs` | Unix-socket JSON-lines server inside the game client; requests run on the game thread (before player update and after each update) |
| Proxy | `tools/terrabot/session.py` | The only socket a program can reach. Whitelists the ops below, journals every action to `inputs.jsonl` (`actor: agent`, `dispatch: tb-api`, wall-clock start/end), releases keys when a program disconnects |
| `tb` library | `terrariabench/tb/` | Python client, `Grid`, pathfinder (`path.py`). Programs see a frozen copy |
| Sandbox | `tools/terrabot/sandbox.py` | `python -I -S` + audit hook + `unshare -rn` (no network) + rlimits; imports: stdlib, `tb`, workspace modules; files: workspace only; wall-clock limit per program (default 60 s) |

## Ops (wire level) and `tb` functions
Reads (no game effect): `me`, `inventory`, `time`, `world`, `tiles`, `find_tiles`, `npcs`, `items` (`tb.items_near`),
`events`, `recipes`, `chest`.
Actions (journaled): `input` (`tb.hold`, and through it `walk`, `jump`, `face`, `use_at`, `mine`, `place`,
`swing_at`, `open_chest`, `goto`), `stop`, `select`, `craft`, `equip`, `take`, `put`, `close_chest`.
Other: `wait` (`tb.sleep`), `screenshot` (proxy-side capture of the game window).
Library-only (pure Python over the ops above): `goto`, `path_to`, `mine`, `place`, `swing_at`, `open_chest`, `count`,
`has`, `log`, `store`.
Function signatures and return fields: see the docstrings in `tb/__init__.py` (rendered into the agent prompt).

## What each action really does
| Action | Mechanism | Same as |
|---|---|---|
| `input` keys for N updates | `ModPlayer.SetControls` sets `controlLeft/Right/Up/Down/Jump/UseItem/UseTile/QuickHeal/QuickMana/Hook` (+ `QuickBuff`) for exactly N updates; `aim` sets `Main.mouseX/Y` to the world point | held keys and mouse buttons; all effects go through the game's own movement, item-use (reach, tool power, swing hitbox, damage, knockback), placement and tile-interaction code |
| `select` | `selectedItem` = hotbar slot; an item elsewhere in the inventory is swapped into hotbar slot 9 first | number key / dragging an item to the hotbar |
| `craft` | `Recipe.FindRecipes` with `Player.AdjTiles`, then `Main.CraftItem(recipe)` (the crafting menu's click handler), cursor item into the inventory with `GetItem(InventoryUIToInventorySettings)` | clicking the recipe in the crafting menu |
| `equip` | `ItemSlot.SwapEquip` | right-clicking armour/accessory in the inventory |
| chest | the player opens it with `use_tile` on it (real interaction, reach-checked); `take()` = `ChestUI.LootAll`, `take(item)`/`put(item)` move stacks with `GetItem`/stack merge; `close_chest` | chest UI buttons / shift-click / Escape |

Declared UI shortcuts (not pixel-faithful): select, craft, equip and chest transfers skip cursor movement in the
inventory UI. They use real recipes, stations, items and the UI's own code paths; they cannot create anything the
UI could not.

Not available: teleporting, item spawning, tile editing, time/weather control, NPC control, game settings, chat
commands, any op not listed above (the proxy refuses it).

## Visibility rules (no X-ray)
- **Tiles** (`tiles`, `find_tiles`): a cell is known iff `Main.Map.IsRevealed(x, y)` (the player's own map,
  revealed only by light reaching the cell while the player is nearby) **or** it is on screen with
  `Lighting.Brightness > 0.03`. Unknown cells return type −2 / kind `Unknown` and no flags. Known cells return the
  *current* tile (a revealed cell that changed out of view shows its new state — small, documented leak).
- **NPCs** (`npcs`): only NPCs whose hitbox is on screen with a lit centre, or within 4 tiles of the player. Fields:
  id, name, type, centre position, size, life, life_max, hostile, boss, town. No AI state, target, velocity,
  timers or spawn information.
- **Dropped items** (`items`): same on-screen rule; name, type, stack, position.
- **Events**: hurt (damage, attacker name), death (death message), respawn, killed (NPCs the player damaged),
  pickup, tile_broken (near the player while it uses an item), placed, crafted, boss_awoke (the game announces this in
  chat), dawn, dusk. All are things the player sees on screen or in chat.
- **Player/world**: own state (as on the HUD plus position), recipes (as the crafting menu and the Guide show), the
  world size and spawn point, layer names and biome flags (visible from backgrounds/music).
- Test-only ops `truth_tiles`/`truth_npcs` exist only when the game is launched with `TERRABOT_TEST=1`; the proxy
  refuses them otherwise; the audit flags any run with test mode on.

## Leakage tests
`tools/terrabot/live_tests.py` (in-game, test mode): every known cell equals ground truth; < 40 % of a 200×200
window at spawn is known; 0 known cells more than 40 rows below the player while ground truth has > 1000 solid
cells there; `find_tiles` returns no unrevealed ore (ground truth > 20 ore cells in range); `npcs` is a subset of
ground truth, never reports far off-screen NPCs and has exactly the whitelisted fields.

## Game conditions
Normal difficulty (Classic), normal enemy spawns and contact damage, unseen random small worlds generated per run
set (`tools/make_world_fixtures.py`, fresh seeds), fresh starter character, no keepInventory, no Peaceful mode.
Programs run while the game runs in real time.
