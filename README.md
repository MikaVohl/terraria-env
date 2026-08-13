# terraria-lite

A small deterministic Terraria, in C. Built as an RL benchmark in the style of
[Craftax](https://craftaxenv.github.io/), with a terminal frontend and a pixel
frontend for humans.

![Game Screenshot](game.png)

## Build

```sh
make              # terraria-lite (terminal) + selftest
make terraria-px  # pixel frontend, needs SDL2 (brew install sdl2)
make check        # invariants + scripted expert over 20 seeds
```

## Play — pixel frontend

```sh
./terraria-px --seed 9
```

Mouse drives everything. **Left click mines, right click places** — aim is
forgiving, whichever of the ten cells around you is *nearest* the cursor gets
picked, so you never have to land on it exactly. Click a recipe in the side
panel to craft it, or an inventory slot to select it. `a`/`d` walk, `w` or space
jumps, `e` cycles the placeable, `r` new world.

**A Terraria install is required.** The pixel frontend loads its tile art, item
icons and player sprite from it at runtime — nothing is copied into this repo
and nothing is shipped. The default Steam location is found automatically;
`--textures DIR` points at an `ExtractedTextures` folder elsewhere. The terminal
frontend needs none of this.

`--scale N` sets the pixel zoom (default 2; 3 needs a large display).

## Play — terminal

```sh
./terraria-lite --seed 9
```

The world ticks on a clock, so falls and jumps play out on their own. Standing
still costs nothing.

```
--seed N       world seed (default 1)
--steps N      episode step limit (default 3000)
--tick-ms N    frame length in ms (default 80)
--lockstep     one tick per keypress instead of on a clock
```

## Terminal controls

```
a d   walk            w  jump         s  wait
e     cycle placeable r  new world    q  quit
```

You are **two tiles tall**. Ten cells surround your body, and every one can be
mined or built into — **lower case mines, shift places**:

```
        dx=-1   dx=0   dx=+1
  dy=-2   y/Y    u/U    i/I     above the head
  dy=-1   h/H   [head]  k/K
  dy= 0   n/N   [feet]  m/M
  dy=+1   ,/<    ./>    //?     below the feet
```

Three that matter:

- `.` mine straight down — a controlled descent, no fall damage.
- `<` or `?` place into a down-diagonal — bridges a chasm without losing altitude.
- `>` place under your own feet — pillars upward.

Crafting is `1`-`9`, `0`, `-`. The station must be within 3 tiles.

```
1 workbench   anywhere     7 iron bar    furnace
2 furnace     workbench    8 anvil       workbench
3 stone pick  workbench    9 iron pick   anvil
4 copper bar  furnace      0 gold bar    furnace
5 copper pick workbench    - lantern     anvil
6 torch x5    workbench
```

## The game

Tools gate ores, darkness gates depth. Chop wood, build a bench, work down
through stone → copper → iron → gold, and light your way as you go. 24
achievements; the reward is one point each.

```
wood ──▶ workbench ──▶ furnace ──▶ stone pick ──▶ copper ──▶ copper pick
                                                     └──▶ torch
copper pick ──▶ iron ──▶ iron bar ──▶ anvil ──▶ iron pick ──▶ gold ──▶ lantern
```

## Layout

```
include/   frozen contract: tiles.h (taxonomy), env.h (state, actions, recipes)
src/       worldgen.c light.c sim.c   the core: no globals, no malloc, no rand
           keymap.h frontend.h        shared by both frontends
           render.c main.c            terminal frontend
           px_render.c px_main.c      SDL pixel frontend
tools/     selftest.c                 invariants + scripted expert
```
