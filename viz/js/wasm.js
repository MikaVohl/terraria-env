// Thin wrapper over viz/terraria.wasm: the v8-default simulator (byte-identical
// to frozen v7) and the trained policy. Field offsets come from w_layout(), so
// nothing here hardcodes the C struct layout. Usable from the page and from
// Workers (no DOM access).

const f = Math.fround;
const L = [
  "ENV_BYTES", "OBS_BYTES", "TILES", "LIGHT", "OBJECT_PART", "PX", "PY", "FACING", "JUMP_LEFT", "FALL", "HEALTH",
  "MAX_HEALTH", "TOOL_TIER", "INV", "SELECTED", "WEAPON", "ARMOR", "MOBS", "MOB_BYTES", "CHESTS", "CHEST_COUNT", "ACH",
  "RNG", "SEED", "STEPS", "MAX_STEPS", "REWARD", "RETURN", "TERMINATED", "TRUNCATED", "MSG", "OBS_TILE", "OBS_LIGHT",
  "OBS_STATUS", "WORLD_W", "WORLD_H", "VIEW_W", "VIEW_H", "TILE_COUNT", "ITEM_COUNT", "ACH_COUNT", "ACT_COUNT",
  "RECIPE_COUNT", "REACH_COUNT", "OBS_STATUS_LEN", "OBS_SEL0", "OBS_INV0", "OBS_ACH0", "OBS_ENTITY0", "MINE_FIRST",
  "PLACE_FIRST", "SELECT_FIRST", "PLACEABLE_COUNT", "LIGHT_MAX", "DARK", "ENV_VERSION", "RECIPE_FIRST", "SKY_CUTOFF",
  "SURFACE", "MINING_TREE", "TERRAIN_LIGHT", "ATTACK_CD", "MINE_CD", "AIR_JUMP", "DROP_TICKS",
];
const TRACE = ["cell_h", "cells", "g1", "g", "ctx", "tz", "other", "logits", "value", "probs", "logp", "entropy",
  "d_logits", "d_g", "d_g1", "d_ctx", "d_tz", "d_cells", "d_status", "saliency", "gin"];

export async function loadWasm(url = new URL("../terraria.wasm", import.meta.url)) {
  const bytes = await (await fetch(url)).arrayBuffer();
  const { instance } = await WebAssembly.instantiate(bytes, {
    env: { sinf: (x) => f(Math.sin(x)), cosf: (x) => f(Math.cos(x)), logf: (x) => f(Math.log(x)) },
  });
  return new Core(instance.exports);
}

export function halfToFloat(half, out) {
  for (let i = 0; i < half.length; i++) {
    const h = half[i], s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 31, m = h & 1023;
    out[i] = e === 0 ? s * m * 2 ** -24 : e === 31 ? (m ? NaN : s * Infinity) : s * (1 + m / 1024) * 2 ** (e - 15);
  }
  return out;
}

export class Core {
  constructor(w) {
    this.w = w;
    const lp = w.w_malloc(4 * 128);
    const n = w.w_layout(lp);
    const lay = new Int32Array(w.memory.buffer, lp, n);
    this.L = Object.fromEntries(L.map((k, i) => [k, lay[i]]));
    const K = this.L;
    this.str = (p) => { const m = this.u8(); let e = p; while (m[e]) e++; return new TextDecoder().decode(m.subarray(p, e)); };
    this.tileNames = Array.from({ length: K.TILE_COUNT + 1 }, (_, t) => this.str(w.w_tile_name(t)));
    this.itemNames = Array.from({ length: K.ITEM_COUNT }, (_, i) => this.str(w.w_item_name(i)));
    this.achNames = Array.from({ length: K.ACH_COUNT }, (_, i) => this.str(w.w_ach_name(i)));
    this.actionNames = Array.from({ length: K.ACT_COUNT }, (_, a) => this.str(w.w_action_name(a)));
    this.reach = Array.from({ length: K.REACH_COUNT }, (_, i) => ({ dx: w.w_reach_dx(i), dy: w.w_reach_dy(i), name: this.str(w.w_reach_name(i)) }));
    this.placeables = Array.from({ length: K.PLACEABLE_COUNT }, (_, i) => w.w_placeable_item(i));
    this.recipes = Array.from({ length: K.RECIPE_COUNT }, (_, r) => ({
      name: this.str(w.w_recipe_name(r)), out: w.w_recipe_out(r), outQty: w.w_recipe_out_qty(r),
      station: w.w_recipe_station(r), ach: w.w_recipe_ach(r), action: K.RECIPE_FIRST + r,
      inputs: Array.from({ length: w.w_recipe_inputs(r) }, (_, j) => ({ item: w.w_recipe_in_item(r, j), qty: w.w_recipe_in_qty(r, j) })),
    }));
    this.objW = Array.from({ length: K.TILE_COUNT }, (_, t) => w.w_tile_object_w(t));
    this.objH = Array.from({ length: K.TILE_COUNT }, (_, t) => w.w_tile_object_h(t));
    this.solid = Array.from({ length: K.TILE_COUNT }, (_, t) => !!w.w_tile_solid(t));
    const tl = w.w_malloc(4 * 32), tn = w.w_trace_layout(tl);
    const toff = new Int32Array(w.memory.buffer, tl, tn);
    this.traceOff = Object.fromEntries(TRACE.map((k, i) => [k, toff[i]]));
  }
  u8() { return new Uint8Array(this.w.memory.buffer); }
  dv() { return new DataView(this.w.memory.buffer); }
  malloc(n) { return this.w.w_malloc(n); }
  env(maxSteps = 0) { return new Env(this, this.w.w_create(maxSteps)); }

  /* ---- policy ---- */
  loadPolicy(halfBuffer, hidden = 128, cellWidth = 32) {
    const half = new Uint16Array(halfBuffer);
    if (!this.policyPtr) this.policyPtr = this.w.w_malloc(half.length * 4);
    halfToFloat(half, new Float32Array(this.w.memory.buffer, this.policyPtr, half.length));
    const used = this.w.w_policy_init(this.policyPtr, hidden, cellWidth);
    if (used !== half.length) throw new Error(`policy blob: expected ${used} floats, got ${half.length}`);
    this.hidden = hidden; this.cellWidth = cellWidth;
  }
  /* obsPtr: n contiguous Obs rows */
  forward(obsPtr, n, logitsPtr, valuesPtr) { this.w.w_policy_forward(obsPtr, n, logitsPtr, valuesPtr); }
  trace(obsPtr, maskPtr, action) {
    const logp = this.w.w_policy_trace(obsPtr, maskPtr, action);
    const base = this.w.w_trace_ptr() >> 2, F = new Float32Array(this.w.memory.buffer), o = this.traceOff;
    const H = this.hidden, C = this.cellWidth, K = this.L, cells = K.VIEW_W * K.VIEW_H, R = K.REACH_COUNT, A = K.ACT_COUNT;
    const v = (k, n) => F.slice(base + o[k], base + o[k] + n);
    return {
      logp, cellH: v("cell_h", cells * C), cells: v("cells", cells * C), g1: v("g1", H), g: v("g", H),
      ctx: v("ctx", R * 64), tz: v("tz", R * 64), other: v("other", A - 2 * R), logits: v("logits", A), value: F[base + o.value],
      probs: v("probs", A), entropy: F[base + o.entropy], dLogits: v("d_logits", A), dG: v("d_g", H),
      dG1: v("d_g1", H), dCtx: v("d_ctx", R * 64), dTz: v("d_tz", R * 64), dCells: v("d_cells", cells * C),
      dStatus: v("d_status", K.OBS_ENTITY0), saliency: v("saliency", cells), gin: v("gin", cells * C + K.OBS_ENTITY0),
    };
  }
}

export class Env {
  constructor(core, ptr) {
    this.c = core; this.p = ptr;
    const K = core.L;
    this.obsPtr = core.malloc(K.OBS_BYTES);
    this.maskPtr = core.malloc(K.ACT_COUNT);
  }
  reset(seed) { this.c.w.w_reset(this.p, seed >>> 0, Math.floor(seed / 2 ** 32)); return this; }
  step(a) { this.c.w.w_step(this.p, a); return this; }
  save(buf) { // buf: Uint8Array of ENV_BYTES
    buf.set(this.c.u8().subarray(this.p, this.p + this.c.L.ENV_BYTES)); return buf;
  }
  load(buf) { this.c.u8().set(buf, this.p); return this; }
  bytes() { return this.c.u8().subarray(this.p, this.p + this.c.L.ENV_BYTES); }
  observe() { this.c.w.w_obs(this.p, this.obsPtr); return this.obsPtr; }
  mask() { this.c.w.w_mask(this.p, this.maskPtr); return this.c.u8().slice(this.maskPtr, this.maskPtr + this.c.L.ACT_COUNT); }
  obs() { // decoded view of the last observe()
    const K = this.c.L, n = K.VIEW_W * K.VIEW_H, m = this.c.u8();
    return {
      tile: m.slice(this.obsPtr + K.OBS_TILE, this.obsPtr + K.OBS_TILE + n),
      light: m.slice(this.obsPtr + K.OBS_LIGHT, this.obsPtr + K.OBS_LIGHT + n),
      status: new Float32Array(m.buffer.slice(this.obsPtr + K.OBS_STATUS, this.obsPtr + K.OBS_STATUS + 4 * K.OBS_STATUS_LEN)),
    };
  }
  i32(off) { return this.c.dv().getInt32(this.p + off, true); }
  u8at(off) { return this.c.u8()[this.p + off]; }
  get px() { return this.i32(this.c.L.PX); }
  get py() { return this.i32(this.c.L.PY); }
  get facing() { return this.i32(this.c.L.FACING); }
  get health() { return this.i32(this.c.L.HEALTH); }
  get maxHealth() { return this.i32(this.c.L.MAX_HEALTH); }
  get steps() { return this.i32(this.c.L.STEPS); }
  get maxSteps() { return this.i32(this.c.L.MAX_STEPS); }
  get achievements() { return this.c.dv().getUint32(this.p + this.c.L.ACH, true); }
  get reward() { return this.c.dv().getFloat32(this.p + this.c.L.REWARD, true); }
  get epReturn() { return this.c.dv().getFloat32(this.p + this.c.L.RETURN, true); }
  get terminated() { return !!this.u8at(this.c.L.TERMINATED); }
  get truncated() { return !!this.u8at(this.c.L.TRUNCATED); }
  get done() { return this.terminated || this.truncated; }
  get selected() { return this.u8at(this.c.L.SELECTED); }
  get toolTier() { return this.u8at(this.c.L.TOOL_TIER); }
  get weapon() { return this.i32(this.c.L.WEAPON); }
  get armor() { return this.i32(this.c.L.ARMOR); }
  get seed() { return Number(this.c.dv().getBigUint64(this.p + this.c.L.SEED, true)); }
  get rng() { return this.c.dv().getBigUint64(this.p + this.c.L.RNG, true); }
  get msg() { return this.c.str(this.p + this.c.L.MSG); }
  inv(i) { return this.c.dv().getInt16(this.p + this.c.L.INV + 2 * i, true); }
  tile(x, y) {
    const K = this.c.L;
    if (x < 0 || y < 0 || x >= K.WORLD_W || y >= K.WORLD_H) return 15; // bedrock
    return this.c.u8()[this.p + K.TILES + y * K.WORLD_W + x];
  }
  surface(x) { return this.i32(this.c.L.SURFACE + 4 * x); }
  mobs() {
    const K = this.c.L, d = this.c.dv(), out = [];
    for (let i = 0; i < 8; i++) {
      const b = this.p + K.MOBS + i * K.MOB_BYTES, kind = this.c.u8()[b + 24];
      if (kind) out.push({ x: d.getInt32(b, true), y: d.getInt32(b + 4, true), hp: d.getInt32(b + 8, true),
        phase: d.getInt32(b + 12, true), dir: d.getInt32(b + 20, true), kind });
    }
    return out;
  }
}
