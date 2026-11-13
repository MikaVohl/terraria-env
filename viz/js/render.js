// Draws an Env from wasm linear memory with the real Terraria art, following
// the frozen v7 pixel frontend's draw_world / draw_light / draw_mobs /
// draw_player. Camera in tile units; scale = screen px per tile.
import { T } from "./terraria.js";

const SURFACE_MAX = 38, DIRT_DEPTH = 8, DARK_THRESHOLD = 2, BG_INSET = 2;
const OBJ = new Set([T.CAMPFIRE, T.WORKBENCH, T.FURNACE, T.ANVIL, T.PLATFORM, T.ROPE, T.CHEST, T.CHEST_OPEN, T.CRYSTAL]);

function hash2(x, y, salt) { // px_render.c hash2, uint32
  let h = (Math.imul(x, 0x9e3779b1) ^ Math.imul(y, 0x85ebca77) ^ Math.imul(salt, 0xc2b2ae3d)) >>> 0;
  h ^= h >>> 15; h = Math.imul(h, 0x2545f491) >>> 0;
  h ^= h >>> 13; h = Math.imul(h, 0x27d4eb2f) >>> 0;
  return (h ^ (h >>> 16)) >>> 0;
}
const skyRows = Array.from({ length: 200 }, (_, y) => {
  const t = Math.min(256, Math.floor((y * 256) / (SURFACE_MAX + 8)));
  const m = (a, b) => a + Math.trunc(((b - a) * t) / 256);
  return `rgb(${m(0x3e, 0xae)},${m(0x74, 0xda)},${m(0xc6, 0xf4)})`;
});

export class WorldRenderer {
  constructor(core, art) {
    this.c = core; this.art = art;
    this.lightCanvas = document.createElement("canvas");
    this.lightCtx = this.lightCanvas.getContext("2d");
  }

  /* view = {x, y, scale, w, h}: x/y top-left in tiles (fractional), w/h canvas px.
     opts.player = {x, y} interpolated feet-left cell; opts.walking; opts.time (s) */
  draw(g, env, view, opts = {}) {
    const K = this.c.L, W = K.WORLD_W, H = K.WORLD_H, s = view.scale, art = this.art, q = s / 16;
    const m = this.c.u8(), tiles = env.p + K.TILES, light = env.p + K.LIGHT, part = env.p + K.OBJECT_PART;
    const x0 = Math.floor(view.x), y0 = Math.floor(view.y);
    const nx = Math.ceil(view.w / s) + 2, ny = Math.ceil(view.h / s) + 2;
    const ox = -(view.x - x0) * s, oy = -(view.y - y0) * s;
    const solid = this.c.solid, time = opts.time ?? 0;
    const tileAt = (x, y) => (x < 0 || y < 0 || x >= W || y >= H ? T.BEDROCK : m[tiles + y * W + x]);
    const surface = (x) => env.surface(x);
    const skyAt = (x, y) => y <= surface(x);
    const skyNeighbour = (x, y) => x >= 0 && y >= 0 && x < W && y < H && m[tiles + y * W + x] === T.AIR && skyAt(x, y);
    g.imageSmoothingEnabled = false;
    // Trees: a trunk top (log with no log above) wears one of Terraria's whole
    // tree-top sprites; the leaf cells it covers are not drawn one by one.
    const tops = [], canopy = new Set();
    for (let y = Math.max(1, y0 - 2); y < Math.min(H, y0 + ny + 6); y++) for (let x = Math.max(0, x0 - 3); x < Math.min(W, x0 + nx + 3); x++) {
      if (m[tiles + y * W + x] !== T.LOG || m[tiles + (y - 1) * W + x] === T.LOG) continue;
      const big = tileAt(x - 2, y - 1) === T.LEAVES || tileAt(x + 2, y - 1) === T.LEAVES;
      tops.push({ x, y, big });
      for (let dy = -2; dy <= 0; dy++) for (let dx = -2; dx <= 2; dx++) if (tileAt(x + dx, y + dy) === T.LEAVES) canopy.add((y + dy) * W + x + dx);
    }
    const S = s + 0.5; // overdraw a hair so fractional scales leave no seams
    for (let j = 0; j < ny; j++) {
      const y = y0 + j, sy = oy + j * s;
      for (let i = 0; i < nx; i++) {
        const x = x0 + i, sx = ox + i * s;
        if (x < 0 || x >= W || y < 0 || y >= H) { g.fillStyle = "#07070b"; g.fillRect(sx, sy, S, S); continue; }
        const t = m[tiles + y * W + x];
        // backdrop: sky above the static skyline, else the dirt or stone wall
        if (skyAt(x, y)) { g.fillStyle = skyRows[Math.min(199, y)]; g.fillRect(sx, sy, S, S); }
        else {
          const wall = y <= surface(x) + DIRT_DEPTH ? art.wallDirt : art.wallStone;
          let l = 0, r = 0, u = 0;
          if (solid[t]) { if (skyNeighbour(x - 1, y)) l = BG_INSET; if (skyNeighbour(x + 1, y)) r = BG_INSET; if (skyNeighbour(x, y - 1)) u = BG_INSET; }
          if (l || r || u) { g.fillStyle = skyRows[Math.min(199, y)]; g.fillRect(sx, sy, S, S); g.drawImage(wall, l, u, 16 - l - r, 16 - u, sx + l * q, sy + u * q, (16 - l - r) * q + 0.5, (16 - u) * q + 0.5); }
          else g.drawImage(wall, 0, 0, 16, 16, sx, sy, S, S);
        }
        if (t === T.AIR) continue;
        if (OBJ.has(t)) {
          const o = art.objects[t], p = m[part + y * W + x];
          const img = o.frames[Math.floor(time * 10) % o.frames.length];
          g.drawImage(img, (p % o.w) * 16, Math.floor(p / o.w) * 16, 16, 16, sx, sy, S, S);
          continue;
        }
        if (t === T.LEAVES && canopy.has(y * W + x)) continue;
        const a = art.tiles[t];
        if (!a) continue;
        const v = hash2(x, y, 0x5eed) % a.nvar;
        let mask = 0;
        if (a.masked) {
          if (solid[tileAt(x, y - 1)]) mask |= 1; if (solid[tileAt(x, y + 1)]) mask |= 2;
          if (solid[tileAt(x - 1, y)]) mask |= 4; if (solid[tileAt(x + 1, y)]) mask |= 8;
        }
        g.drawImage(a.img, v * 16, mask * 16, 16, 16, sx, sy, S, S);
        if (t === T.LEAVES) { // canopy depth, faked per cell as in px_render.c
          const k = (200 + (hash2(x, y, 0xf0a) % 56)) / 255;
          g.fillStyle = `rgba(0,0,0,${1 - k})`; g.fillRect(sx, sy, S, S);
        }
      }
    }
    for (const tp of tops) {
      const k = (tp.big ? 1 : 0.72) * q, img = art.treeTops[hash2(tp.x, tp.y, 0x7ee) % 3];
      g.drawImage(img, (tp.x + 0.5 - view.x) * s - 40 * k, (tp.y + 1 - view.y) * s - 4 * q - 80 * k, 80 * k, 80 * k);
    }
    this.drawMobs(g, env, view, time);
    this.drawPlayer(g, env, view, opts);
    if (opts.light !== false) this.drawLight(g, env, view, { x0, y0, nx, ny, ox, oy });
  }

  drawMobs(g, env, view, time) {
    const K = this.c.L, s = view.scale, q = s / 16, art = this.art, m = this.c.u8();
    for (const mob of env.mobs()) {
      if (mob.x < 0 || mob.y < 0 || mob.x >= K.WORLD_W || mob.y >= K.WORLD_H) continue;
      if (m[env.p + K.LIGHT + mob.y * K.WORLD_W + mob.x] < DARK_THRESHOLD) continue;
      const sl = mob.kind === 1, a = sl ? art.slime : art.bat;
      const f = Math.floor((mob.phase * a.n) / 8);
      const cx = (mob.x - view.x) * s + 8 * q, by = (mob.y + 1 - view.y) * s;
      const w = a.w * q, h = a.h * q;
      g.save();
      g.translate(cx, by - h);
      if (mob.dir < 0) g.scale(-1, 1);
      if (sl) { g.drawImage(a.a, 0, f * a.h, a.w, a.h, -w / 2, 0, w, h); g.drawImage(a.b, 0, f * a.h, a.w, a.h, -w / 2, 0, w, h); }
      else g.drawImage(a.img, 0, f * a.h, a.w, a.h, -w / 2, 0, w, h);
      g.restore();
      g.fillStyle = "#14131a"; g.fillRect(cx - 8 * q, by - h - 3 * q, 16 * q, 2 * q);
      g.fillStyle = "#d65b4b"; g.fillRect(cx - 8 * q, by - h - 3 * q, (16 * q * mob.hp) / (sl ? 25 : 16), 2 * q);
    }
  }

  drawPlayer(g, env, view, opts) {
    const K = this.c.L, s = view.scale, q = s / 16, art = this.art, PL = art.PL;
    const p = opts.player ?? { x: env.px, y: env.py };
    const airborne = env.i32(K.JUMP_LEFT) > 0 || env.i32(K.FALL) > 0;
    const f = airborne ? PL.JUMP : opts.walking ? PL.WALK0 + (Math.floor((opts.time ?? 0) * 18) % PL.WALKN) : 0;
    const bx = (p.x - view.x) * s, by = (p.y + 1 - 3 - view.y) * s;
    const atlas = art.player[Math.max(0, Math.min(2, env.armor))];
    g.drawImage(atlas, f * PL.FW, env.facing < 0 ? PL.FH : 0, PL.FW, PL.FH, bx + PL.OX * q, by + PL.OY * q, PL.FW * q, PL.FH * q);
    // held tool or weapon while it is cooling down (display only)
    const hx = bx + s + env.facing * 12 * q - 10 * q, hy = by + 1.5 * s - 10 * q;
    let held = null;
    if (env.i32(K.ATTACK_CD)) held = art.items[[23, 24, 25, 26, 28, 27][env.weapon] ?? 23];
    else if (env.i32(K.MINE_CD)) held = env.u8at(K.MINING_TREE) ? art.axe : art.picks[Math.max(0, env.toolTier - 1)];
    if (held) g.drawImage(held, hx, hy, 20 * q, 20 * q);
  }

  /* Warm multiplicative light, bilinear across tiles (draw_light). For display
     only, light also bleeds a few tiles into solid ground, so the surface is
     not a black wall; observations use the simulator's own light. */
  drawLight(g, env, view, { x0, y0, nx, ny, ox, oy }) {
    const K = this.c.L, W = K.WORLD_W, H = K.WORLD_H, s = view.scale, m = this.c.u8(), light = env.p + K.LIGHT, LM = K.LIGHT_MAX;
    const M = 4, bw = nx + 2 * M, bh = ny + 2 * M;
    let L = this.lbuf;
    if (!L || L.length !== bw * bh) L = this.lbuf = new Float32Array(bw * bh);
    for (let j = 0; j < bh; j++) for (let i = 0; i < bw; i++) {
      const x = x0 + i - M, y = y0 + j - M;
      L[j * bw + i] = x < 0 || y < 0 || x >= W || y >= H ? 0 : m[light + y * W + x];
    }
    for (let pass = 0; pass < M; pass++) for (let j = 1; j < bh - 1; j++) for (let i = 1; i < bw - 1; i++) {
      const k = j * bw + i, b = Math.max(L[k - 1], L[k + 1], L[k - bw], L[k + bw]) - 3.2;
      if (b > L[k]) L[k] = b;
    }
    const lc = this.lightCanvas, lg = this.lightCtx;
    if (lc.width !== nx || lc.height !== ny) { lc.width = nx; lc.height = ny; }
    const img = lg.createImageData(nx, ny), d = img.data;
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const t = (L[(j + M) * bw + i + M] - (DARK_THRESHOLD - 1)) / (LM - (DARK_THRESHOLD - 1));
      const b = t <= 0 ? 0 : t >= 1 ? 1 : Math.pow(t, 0.72), k = (j * nx + i) * 4;
      d[k] = 255 * b; d[k + 1] = 255 * b * (0.7 + 0.3 * b); d[k + 2] = 255 * b * (0.46 + 0.54 * b); d[k + 3] = 255;
    }
    lg.putImageData(img, 0, 0);
    g.save();
    g.globalCompositeOperation = "multiply"; g.imageSmoothingEnabled = true;
    g.drawImage(lc, 0, 0, nx, ny, ox, oy, nx * s, ny * s);
    g.restore();
  }
}
