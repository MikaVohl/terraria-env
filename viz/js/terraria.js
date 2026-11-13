// Real Terraria art, loaded at page start from the local install through the
// gitignored viz/textures symlink (make -C viz textures). Nothing is copied
// into the repository. Sheets, crops, tints and frame tables follow the frozen
// v7 pixel frontend (experiments/v7-reward-20261017.sGYPqq/variants/v7/src/
// px_render.c) so the browser and terraria-px draw the same world the same way.
// Loading is all or nothing: a missing sheet is an error naming the file.

export const T = {
  AIR: 0, DIRT: 1, GRASS: 2, STONE: 3, LOG: 4, WOOD: 5, LEAVES: 6, COPPER: 7, IRON: 8, GOLD: 9, TORCH: 10,
  CAMPFIRE: 11, WORKBENCH: 12, FURNACE: 13, ANVIL: 14, BEDROCK: 15, SILVER: 16, PLATFORM: 17, ROPE: 18,
  CHEST: 19, CHEST_OPEN: 20, CRYSTAL: 21, MUSHROOM: 22,
};

/* Frame (col, row) in an 18px-stride block sheet for each 4-neighbour solidity
   mask, three variants each. Bit 0 up, 1 down, 2 left, 3 right (1 = solid). */
const FRAME_TAB = [
  [[9, 3], [10, 3], [11, 3]], [[6, 3], [7, 3], [8, 3]], [[6, 0], [7, 0], [8, 0]], [[5, 0], [5, 1], [5, 2]],
  [[12, 0], [12, 1], [12, 2]], [[1, 4], [3, 4], [5, 4]], [[1, 3], [3, 3], [5, 3]], [[4, 0], [4, 1], [4, 2]],
  [[9, 0], [9, 1], [9, 2]], [[0, 4], [2, 4], [4, 4]], [[0, 3], [2, 3], [4, 3]], [[0, 0], [0, 1], [0, 2]],
  [[6, 4], [7, 4], [8, 4]], [[1, 2], [2, 2], [3, 2]], [[1, 0], [2, 0], [3, 0]], [[1, 1], [2, 1], [3, 1]],
];
const GRIDS = { [T.DIRT]: "Tiles_0", [T.STONE]: "Tiles_1", [T.GRASS]: "Tiles_2", [T.WOOD]: "Tiles_30",
  [T.COPPER]: "Tiles_7", [T.IRON]: "Tiles_6", [T.GOLD]: "Tiles_8", [T.SILVER]: "Tiles_9", [T.BEDROCK]: "Tiles_25" };
/* [tile, sheet, x0, y0, cols, rows, animation frames, frame pitch] at native scale */
const OBJECTS = [
  [T.CAMPFIRE, "Tiles_215", 0, 0, 3, 2, 8, 36], [T.PLATFORM, "Tiles_19", 0, 0, 1, 1],
  [T.ROPE, "Tiles_213", 0, 0, 1, 1], [T.CHEST, "Tiles_21", 0, 0, 2, 2], [T.CHEST_OPEN, "Tiles_21", 0, 76, 2, 2],
  [T.CRYSTAL, "Tiles_12", 0, 0, 2, 2], [T.ANVIL, "Tiles_16", 0, 0, 2, 1], [T.WORKBENCH, "Tiles_18", 0, 0, 2, 1],
  [T.FURNACE, "Tiles_17", 0, 0, 3, 2, 12, 38],
];
const TORCH_SRC = [[3, 2, 16, 16]];
const TRUNK_SRC = [[0, 0, 20, 20], [0, 22, 20, 20], [0, 44, 20, 20]];
const LEAF_SRC = [[14, 22, 16, 16], [30, 22, 16, 16], [46, 22, 16, 16], [30, 38, 16, 16]];

/* Terraria's default character: greyscale masks tinted and stacked back to front. */
const PL = { FW: 40, FH: 56, FRAMES: 20, JUMP: 5, WALK0: 6, WALKN: 14, OX: -4, OY: -8 };
const PC = { SKIN: [255, 125, 90], HAIR: [215, 90, 55], EYE: [255, 255, 255], PUPIL: [105, 90, 75],
  SHIRT: [175, 165, 140], UNDER: [160, 180, 215], PANTS: [255, 230, 175], SHOES: [160, 105, 60] };
const ANIM = -1, HAIRS = -2;
const PLAYER_LAYERS = [
  ["Player_0_10", PC.SKIN, ANIM], ["Player_0_11", PC.PANTS, ANIM], ["Player_0_12", PC.SHOES, ANIM],
  ["Player_0_3", PC.SKIN, 0], ["Player_0_6", PC.SHIRT, 0], ["Player_0_7", PC.SKIN, 7], ["Player_0_8", PC.UNDER, 7],
  ["Player_0_4", PC.SHIRT, 7], ["Player_0_5", PC.SKIN, 7], ["Player_0_0", PC.SKIN, ANIM], ["Player_0_1", PC.EYE, ANIM],
  ["Player_0_2", PC.PUPIL, ANIM], ["Player_Hair_1", PC.HAIR, HAIRS],
];
const ARMOR = ["Armor/Armor_32", "Armor/Armor_2"];   // wood breastplate, iron chainmail
const ITEM_IDS = [9, 3, 2, 12, 11, 13, 20, 22, 19, 8, 966, 36, 33, 35, 14, 21, 23, 94, 965, 5, 28, 29, 53,
  3507, 24, 3508, 4, 3520, 3514, 728, 81, 1, 3521];   // ITEM_TERRARIA_ID in tiles.h
const PICK_IDS = [3509, 1, 3521], AXE_ID = 3506;
/* Achievement icon: an item index, or a named special. */
const ACH_ICON = [0, 1, 2, 11, 12, 13, 9, 17, 3, 4, 14, 5, 6, 7, 15, 8, 16, "bat", "chest", 24, 26, 29, 30, 20, 21,
  22, "deep", "surface", "explore", 18, 31, 32];

/* ---- pixel plumbing ---- */

class Sheet {
  constructor(img) {
    const [c, g] = canvas(img.width, img.height);
    g.drawImage(img, 0, 0);
    this.w = img.width; this.h = img.height; this.d = g.getImageData(0, 0, img.width, img.height).data;
  }
  at(x, y) { // [r, g, b, a], transparent outside
    if (x < 0 || y < 0 || x >= this.w || y >= this.h) return [0, 0, 0, 0];
    const i = (y * this.w + x) * 4, d = this.d;
    return [d[i], d[i + 1], d[i + 2], d[i + 3]];
  }
}
function canvas(w, h) {
  const c = typeof OffscreenCanvas !== "undefined" ? new OffscreenCanvas(w, h) : Object.assign(document.createElement("canvas"), { width: w, height: h });
  const g = c.getContext("2d"); g.imageSmoothingEnabled = false;
  return [c, g];
}
function fromPixels(w, h, px) { // px: Uint8ClampedArray RGBA
  const [c, g] = canvas(w, h); g.putImageData(new ImageData(px, w, h), 0, 0); return c;
}
/* Copy a rect of a sheet (sx, sy, w, h) into a new canvas. */
function crop(s, sx, sy, w, h) {
  const px = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) px.set(s.at(sx + x, sy + y), (y * w + x) * 4);
  return fromPixels(w, h, px);
}
/* Area-average (premultiplied) a source rect into a dw x dh image placed in an
   ow x oh canvas at (dx, dy): px_render.c blit_box. */
function boxFit(s, sx, sy, sw, sh, ow, oh, dx, dy, dw, dh) {
  const px = new Uint8ClampedArray(ow * oh * 4);
  for (let oy = 0; oy < dh; oy++) for (let ox = 0; ox < dw; ox++) {
    let x0 = sx + Math.floor((ox * sw) / dw), x1 = sx + Math.floor(((ox + 1) * sw) / dw);
    let y0 = sy + Math.floor((oy * sh) / dh), y1 = sy + Math.floor(((oy + 1) * sh) / dh);
    if (x1 <= x0) x1 = x0 + 1; if (y1 <= y0) y1 = y0 + 1;
    let r = 0, g = 0, b = 0, a = 0, n = 0;
    for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { const c = s.at(x, y); r += c[0] * c[3]; g += c[1] * c[3]; b += c[2] * c[3]; a += c[3]; n++; }
    if (a) px.set([r / a, g / a, b / a, a / n], ((dy + oy) * ow + dx + ox) * 4);
  }
  return fromPixels(ow, oh, px);
}
/* 16x16 fit of a crop, bottom-aligned or centred (load_fitted). */
function fit16(s, [sx, sy, sw, sh], bottom) {
  const dw = sw >= sh ? 16 : Math.max(1, Math.floor((sw * 16) / sh)), dh = sh >= sw ? 16 : Math.max(1, Math.floor((sh * 16) / sw));
  return boxFit(s, sx, sy, sw, sh, 16, 16, (16 - dw) >> 1, bottom ? 16 - dh : (16 - dh) >> 1, dw, dh);
}
/* A cols x rows block of 16x16 frames on an 18px stride, gutters dropped. */
function gather(s, x0, y0, cols, rows) {
  const w = cols * 16, h = rows * 16, px = new Uint8ClampedArray(w * h * 4);
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++)
    px.set(s.at(x0 + c * 18 + x, y0 + r * 18 + y), ((r * 16 + y) * w + c * 16 + x) * 4);
  return fromPixels(w, h, px);
}
/* Native item art centred in a square canvas, so it scales without distortion. */
function square(img) {
  const n = Math.max(img.width, img.height), [c, g] = canvas(n, n);
  g.drawImage(img, (n - img.width) >> 1, (n - img.height) >> 1); return c;
}
/* Multiply RGB by tint/255 and alpha by a/255 (SDL colour + alpha mod). */
function tinted(img, [r, g, b], a) {
  const [c, x] = canvas(img.width, img.height); x.drawImage(img, 0, 0);
  const id = x.getImageData(0, 0, img.width, img.height), d = id.data;
  for (let i = 0; i < d.length; i += 4) { d[i] = (d[i] * r) / 255; d[i + 1] = (d[i + 1] * g) / 255; d[i + 2] = (d[i + 2] * b) / 255; d[i + 3] = (d[i + 3] * a) / 255; }
  x.putImageData(id, 0, 0); return c;
}
const over = (dst, i, r, g, b, a) => { // straight-alpha source-over into RGBA array
  const ia = (dst[i + 3] * (255 - a)) / 255, oa = a + ia;
  if (!oa) return;
  dst[i] = (r * a + dst[i] * ia) / oa; dst[i + 1] = (g * a + dst[i + 1] * ia) / oa; dst[i + 2] = (b * a + dst[i + 2] * ia) / oa; dst[i + 3] = oa;
};

/* ---- loading ---- */

export async function loadArt(base = new URL("../textures/", import.meta.url)) {
  const names = new Set([...Object.values(GRIDS), ...OBJECTS.map((o) => o[1]), "Tiles_4", "Tiles_5", "Tree_Tops_0",
    "NPC_1", "NPC_49", ...PLAYER_LAYERS.map((l) => l[0]), ...ARMOR,
    ...[...ITEM_IDS, ...PICK_IDS, AXE_ID].map((id) => `Item_${id}`)]);
  const sheets = {};
  await Promise.all([...names].map(async (n) => {
    const r = await fetch(new URL(`${n}.png`, base));
    if (!r.ok) throw new Error(`textures: cannot read textures/${n}.png. Run "make -C viz textures" (needs a local Terraria install's ExtractedTextures).`);
    sheets[n] = new Sheet(await createImageBitmap(await r.blob()));
  }));
  const S = (n) => sheets[n];
  const art = { T, PL, tiles: {}, objects: {}, items: [], picks: [], ach: [] };

  // blocks: 3 variants x 16 masks, 48 x 256 atlas (load_grid)
  for (const [t, name] of Object.entries(GRIDS)) {
    const s = S(name), px = new Uint8ClampedArray(48 * 256 * 4);
    for (let m = 0; m < 16; m++) for (let v = 0; v < 3; v++) {
      const fx = FRAME_TAB[m][v][0] * 18, fy = FRAME_TAB[m][v][1] * 18;
      for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) px.set(s.at(fx + x, fy + y), ((m * 16 + y) * 48 + v * 16 + x) * 4);
    }
    art.tiles[t] = { img: fromPixels(48, 256, px), nvar: 3, masked: true };
  }
  const strip = (s, srcs, bottom) => {
    const [c, g] = canvas(16 * srcs.length, 16);
    srcs.forEach((r, v) => g.drawImage(fit16(s, r, bottom), v * 16, 0));
    return { img: c, nvar: srcs.length, masked: false };
  };
  art.tiles[T.LOG] = strip(S("Tiles_5"), TRUNK_SRC, false);
  art.tiles[T.LEAVES] = strip(S("Tree_Tops_0"), LEAF_SRC, false);
  art.treeTops = [0, 1, 2].map((v) => crop(S("Tree_Tops_0"), v * 82, 0, 80, 80));
  art.tiles[T.TORCH] = strip(S("Tiles_4"), TORCH_SRC, false);
  const mush = S("Item_5"); art.tiles[T.MUSHROOM] = strip(mush, [[0, 0, mush.w, mush.h]], true);
  for (const [t, name, x0, y0, cols, rows, frames = 1, pitch = 0] of OBJECTS) {
    const s = S(name), fr = [];
    for (let f = 0; f < frames; f++) { if (y0 + f * pitch + rows * 18 - 2 > s.h) break; fr.push(gather(s, x0, y0 + f * pitch, cols, rows)); }
    art.objects[t] = { frames: fr, w: cols, h: rows };
  }
  // cave walls: the buried frame of the block sheet, darkened toward blue (backdrop())
  const wall = (s) => {
    const px = new Uint8ClampedArray(16 * 16 * 4);
    for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
      const [r, g, b] = s.at(18 + x, 18 + y), d = (v) => Math.floor((v * 38) / 100);
      const mix = (a, c) => a + Math.trunc(((c - a) * 60) / 256);
      px.set([mix(d(r), 0x10), mix(d(g), 0x18), mix(d(b), 0x28), 255], (y * 16 + x) * 4);
    }
    return fromPixels(16, 16, px);
  };
  art.wallDirt = wall(S("Tiles_0")); art.wallStone = wall(S("Tiles_1"));

  // items: native art in a square canvas
  art.items = ITEM_IDS.map((id) => square(crop(S(`Item_${id}`), 0, 0, S(`Item_${id}`).w, S(`Item_${id}`).h)));
  art.picks = PICK_IDS.map((id) => square(crop(S(`Item_${id}`), 0, 0, S(`Item_${id}`).w, S(`Item_${id}`).h)));
  art.axe = square(crop(S(`Item_${AXE_ID}`), 0, 0, S(`Item_${AXE_ID}`).w, S(`Item_${AXE_ID}`).h));

  // player: 20 frames x (right, mirrored left), per armour (load_player)
  art.player = [0, 1, 2].map((armor) => {
    const W = PL.FRAMES * PL.FW, px = new Uint8ClampedArray(W * 2 * PL.FH * 4);
    const frame = new Uint8ClampedArray(PL.FW * PL.FH * 4);
    for (let f = 0; f < PL.FRAMES; f++) {
      frame.fill(0);
      for (const [name, tint, col] of PLAYER_LAYERS) {
        const s = S(name), sx = col >= 0 ? col * PL.FW : 0;
        const sy = col === HAIRS ? (f >= PL.WALK0 ? f - PL.WALK0 : 0) * PL.FH : col === ANIM ? f * PL.FH : 0;
        for (let y = 0; y < PL.FH; y++) for (let x = 0; x < PL.FW; x++) {
          const m = s.at(sx + x, sy + y);
          if (m[3]) over(frame, (y * PL.FW + x) * 4, (m[0] * tint[0]) / 255, (m[0] * tint[1]) / 255, (m[0] * tint[2]) / 255, m[3]);
        }
      }
      if (armor) for (const col of [0, 7]) {
        const s = S(ARMOR[armor - 1]);
        for (let y = 0; y < PL.FH; y++) for (let x = 0; x < PL.FW; x++) { const c = s.at(col * PL.FW + x, y); if (c[3]) over(frame, (y * PL.FW + x) * 4, ...c); }
      }
      for (let y = 0; y < PL.FH; y++) for (let x = 0; x < PL.FW; x++) {
        const src = frame.subarray((y * PL.FW + x) * 4, (y * PL.FW + x) * 4 + 4);
        px.set(src, (y * W + f * PL.FW + x) * 4);
        if (x > 0) px.set(src, ((PL.FH + y) * W + f * PL.FW + PL.FW - x) * 4);
      }
    }
    return fromPixels(W, 2 * PL.FH, px);
  });
  // mobs: Blue Slime (NPC_1, 2 frames of 32x26) and Cave Bat (NPC_49, 5 frames of 44x32)
  const slime = crop(S("NPC_1"), 0, 0, S("NPC_1").w, S("NPC_1").h);
  art.slime = { a: tinted(slime, [80, 80, 80], 80), b: tinted(slime, [0, 80, 255], 100), w: 32, h: 26, n: 2 };
  art.bat = { img: crop(S("NPC_49"), 0, 0, S("NPC_49").w, S("NPC_49").h), w: 44, h: 32, n: 5 };

  // icons used outside the world view
  art.tileIcon = iconCache((t) => {
    if (art.objects[t]) return square(art.objects[t].frames[0]);
    const a = art.tiles[t], [c, g] = canvas(16, 16);
    g.drawImage(a.img, 0, a.masked ? 15 * 16 : 0, 16, 16, 0, 0, 16, 16); return c;
  });
  const [bc, bg] = canvas(PL.FW, PL.FH); bg.drawImage(art.player[0], 0, 0, PL.FW, PL.FH, 0, 0, PL.FW, PL.FH);
  art.playerIcon = bc;                     // drawn over a 2x3 body box with drawPlayerIcon
  art.slimeIcon = square(mobFrame(art.slime, 0)); art.batIcon = square(cropCanvas(art.bat.img, 0, 0, 44, 32));
  art.ach = ACH_ICON.map((k) => (typeof k === "number" ? art.items[k] : special(k, art)));
  art.tileRGB = Array.from({ length: 24 }, (_, t) => (t === 0 || t === 23 ? [0, 0, 0] : average(art.tileIcon(t))));
  return art;
}

function iconCache(make) { const m = new Map(); return (t) => { if (!m.has(t)) m.set(t, make(t)); return m.get(t); }; }
function cropCanvas(img, x, y, w, h) { const [c, g] = canvas(w, h); g.drawImage(img, x, y, w, h, 0, 0, w, h); return c; }
function mobFrame(sl, f) { const [c, g] = canvas(sl.w, sl.h); g.drawImage(sl.a, 0, f * sl.h, sl.w, sl.h, 0, 0, sl.w, sl.h); g.drawImage(sl.b, 0, f * sl.h, sl.w, sl.h, 0, 0, sl.w, sl.h); return c; }
function average(img) {
  const d = img.getContext("2d").getImageData(0, 0, img.width, img.height).data; let r = 0, g = 0, b = 0, n = 0;
  for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 128) { r += d[i]; g += d[i + 1]; b += d[i + 2]; n++; }
  return n ? [r / n, g / n, b / n] : [0, 0, 0];
}
/* Achievements with no item of their own: small UI glyphs, not game art. */
function special(k, art) {
  if (k === "bat") return art.batIcon;
  if (k === "chest") return art.tileIcon(T.CHEST);
  const [c, g] = canvas(16, 16), P = (x, y, w, h, col) => { g.fillStyle = col; g.fillRect(x, y, w, h); };
  if (k === "deep") { P(7, 1, 2, 10, "#cfd8e8"); for (let j = 0; j < 4; j++) P(4 + j, 9 + j, 8 - 2 * j, 1, "#cfd8e8"); P(2, 14, 12, 2, "#808287"); }
  else if (k === "surface") { P(7, 5, 2, 10, "#9cf09c"); for (let j = 0; j < 4; j++) P(4 + j, 7 - j, 8 - 2 * j, 1, "#9cf09c"); P(1, 1, 3, 3, "#ffd84a"); }
  else { P(1, 7, 14, 2, "#cfd8e8"); P(1, 5, 2, 6, "#cfd8e8"); P(13, 5, 2, 6, "#cfd8e8"); }
  return c;
}

/* Draw the standing player into a 2x3-cell body box at (x, y) with cell size cs. */
export function drawPlayerIcon(g, art, x, y, cs, alpha = 1) {
  const k = cs / 16;
  g.save(); g.globalAlpha = alpha; g.imageSmoothingEnabled = false;
  g.drawImage(art.playerIcon, x + PL.OX * k, y + PL.OY * k, PL.FW * k, PL.FH * k);
  g.restore();
}
