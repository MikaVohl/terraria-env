// One Web Worker = one wasm instance stepping a slice of the parallel grid:
// its own envs, its own copy of the policy, native-style autoreset with
// consecutive seeds. Renders each env's neighbourhood into an RGBA strip
// (one pixel per tile) and posts it with running statistics.
import { loadWasm } from "./wasm.js";

let core, envs = [], obsRows, logits, values, maskBuf, nextSeed, cols, cellW, cellH, rows, running = false;
let palette, px, stepsPerTick = 2, policyReady = false, rngState = 1, stats, delayMs = 50;
const SKY = [110, 160, 235];

function rand() { // xorshift32, per worker: action sampling only
  rngState ^= rngState << 13; rngState >>>= 0; rngState ^= rngState >>> 17; rngState ^= rngState << 5; rngState >>>= 0;
  return rngState / 4294967296;
}

function freshStats() {
  return { steps: 0, episodes: 0, achSum: 0, deaths: 0, achHits: new Array(32).fill(0), hist: new Array(33).fill(0), returns: 0 };
}

self.onmessage = async (ev) => {
  const m = ev.data;
  if (m.type === "init") {
    core = await loadWasm(new URL("../terraria.wasm", import.meta.url));
    const K = core.L;
    ({ cols, cellW, cellH, palette } = m);
    rows = Math.ceil(m.count / cols);
    nextSeed = m.seed; rngState = (m.seed * 2654435761) >>> 0 || 1;
    for (let i = 0; i < m.count; i++) envs.push(core.env(0).reset(nextSeed++));
    obsRows = core.malloc(K.OBS_BYTES * m.count);
    logits = core.malloc(4 * K.ACT_COUNT * m.count);
    values = core.malloc(4 * m.count);
    maskBuf = core.malloc(K.ACT_COUNT);
    px = new Uint8ClampedArray(cols * cellW * rows * cellH * 4);
    stats = freshStats();
    self.postMessage({ type: "ready" });
  } else if (m.type === "policy") {
    core.loadPolicy(m.blob, m.hidden, m.cellWidth); policyReady = true;
    for (const e of envs) e.reset(nextSeed++);
    stats = freshStats();
  } else if (m.type === "run") {
    if (!running) { running = true; loop(); }
  } else if (m.type === "pause") running = false;
  else if (m.type === "speed") { stepsPerTick = m.stepsPerTick; delayMs = m.delayMs; }
};

function stepAll() {
  const K = core.L, A = K.ACT_COUNT, n = envs.length, mem = () => core.u8();
  for (let i = 0; i < n; i++) core.w.w_obs(envs[i].p, obsRows + i * K.OBS_BYTES);
  core.forward(obsRows, n, logits, values);
  const L = new Float32Array(core.w.memory.buffer, logits, A * n);
  for (let i = 0; i < n; i++) {
    const e = envs[i];
    core.w.w_mask(e.p, maskBuf);
    const mk = mem().subarray(maskBuf, maskBuf + A);
    let mx = -1e30;
    for (let a = 0; a < A; a++) if (mk[a] && L[i * A + a] > mx) mx = L[i * A + a];
    let z = 0; const p = new Float64Array(A);
    for (let a = 0; a < A; a++) if (mk[a]) { p[a] = Math.exp(L[i * A + a] - mx); z += p[a]; }
    let r = rand() * z, act = 0;
    for (let a = 0; a < A; a++) { if (!mk[a]) continue; r -= p[a]; act = a; if (r <= 0) break; }
    e.step(act);
    stats.steps++;
    if (e.done) {
      const ach = e.achievements; let c = 0;
      for (let b = 0; b < 32; b++) if ((ach >>> b) & 1) { c++; stats.achHits[b]++; }
      stats.episodes++; stats.achSum += c; stats.hist[c]++; stats.returns += e.epReturn;
      if (e.terminated) stats.deaths++;
      e.reset(nextSeed++);
    }
  }
}

function paint() {
  const K = core.L, W = K.WORLD_W, H = K.WORLD_H, m = core.u8(), stride = cols * cellW;
  const cur = [];
  envs.forEach((e, i) => {
    const cx = (i % cols) * cellW, cy = Math.floor(i / cols) * cellH;
    const pxl = e.px, pyl = e.py, x0 = pxl + 1 - (cellW >> 1), y0 = pyl - 1 - (cellH >> 1);
    const tiles = e.p + K.TILES, light = e.p + K.LIGHT;
    for (let j = 0; j < cellH; j++) for (let k = 0; k < cellW; k++) {
      const x = x0 + k, y = y0 + j, o = ((cy + j) * stride + cx + k) * 4;
      let r, g, b;
      if (x < 0 || y < 0 || x >= W || y >= H) { r = g = b = 18; }
      else {
        const t = m[tiles + y * W + x], l = m[light + y * W + x] / 15, under = y > e.surface(x) + 1;
        const c = t === 0 ? (under ? [60, 44, 34] : SKY) : palette[t];
        const k2 = t === 0 ? Math.pow(l, 1.4) : 0.28 + 0.72 * Math.pow(l, 1.4); // display: terrain stays visible
        r = c[0] * k2; g = c[1] * k2; b = c[2] * k2;
      }
      px[o] = r; px[o + 1] = g; px[o + 2] = b; px[o + 3] = 255;
    }
    // player: 2x3 bright pixels
    for (let j = 0; j < 3; j++) for (let k = 0; k < 2; k++) {
      const x = pxl + k - x0, y = pyl - j - y0;
      if (x < 0 || y < 0 || x >= cellW || y >= cellH) continue;
      const o = ((cy + y) * stride + cx + x) * 4;
      px[o] = 255; px[o + 1] = j === 2 ? 200 : 240; px[o + 2] = j === 2 ? 150 : 230;
    }
    cur.push(popcount(e.achievements));
  });
  return cur;
}
const popcount = (v) => { let c = 0; while (v) { c += v & 1; v >>>= 1; } return c; };

async function loop() {
  while (running) {
    const t0 = performance.now();
    if (policyReady) for (let s = 0; s < stepsPerTick; s++) stepAll();
    const current = paint();
    const out = px.slice();
    self.postMessage({ type: "frame", pixels: out, stats, current, ms: performance.now() - t0 }, [out.buffer]);
    await new Promise((r) => setTimeout(r, Math.max(0, delayMs - (performance.now() - t0))));
  }
}
