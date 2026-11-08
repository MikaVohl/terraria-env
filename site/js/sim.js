// The real simulator and policy in the page, reused from viz/ through the
// site/viz symlink: viz/terraria.wasm (v8 core, default knobs, byte-identical
// to frozen v7), viz's Terraria-art renderer, and the 2.1B-step eg15 policy
// (viz/data/policy-2147483648.bin). Nothing here re-implements the game.
import { loadWasm } from "../viz/js/wasm.js";
import { loadArt } from "../viz/js/terraria.js";
import { WorldRenderer } from "../viz/js/render.js";
import { fitCanvas } from "../viz/js/ui.js";

export { fitCanvas };
let booted = null;

/* One wasm instance, the art and (optionally) the policy, shared by everything on a page. */
export function boot() {
  if (!booted) booted = (async () => {
    const [core, art, run] = await Promise.all([loadWasm(), loadArt(), fetch("viz/data/run.json").then((r) => r.json())]);
    const best = run.checkpoints[run.checkpoints.length - 1];
    const blob = await (await fetch(`viz/data/${best.file}`)).arrayBuffer();
    core.loadPolicy(blob, best.hidden, best.cell_width);
    const K = core.L;
    const S = { core, art, run, policy: best, renderer: new WorldRenderer(core, art), K };
    S.logits = core.malloc(4 * K.ACT_COUNT);
    S.values = core.malloc(4);
    return S;
  })();
  return booted;
}

/* xorshift32 sampler, as in viz/js/play.js */
export function rng(seed) {
  let x = seed >>> 0 || 0x9e3779b9;
  return () => { x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; x >>>= 0; return x / 4294967296; };
}

/* Sample an action from the policy's masked softmax. */
export function policyAction(S, env, rand) {
  const K = S.K, A = K.ACT_COUNT;
  const op = env.observe();
  const mask = env.mask();
  S.core.forward(op, 1, S.logits, S.values);
  const lg = new Float32Array(S.core.w.memory.buffer, S.logits, A);
  let mx = -Infinity;
  for (let i = 0; i < A; i++) if (mask[i] && lg[i] > mx) mx = lg[i];
  let z = 0;
  const p = new Float64Array(A);
  for (let i = 0; i < A; i++) if (mask[i]) { p[i] = Math.exp(lg[i] - mx); z += p[i]; }
  let r = rand() * z, a = 0;
  for (let i = 0; i < A; i++) { if (!mask[i]) continue; a = i; r -= p[i]; if (r <= 0) break; }
  return a;
}

export const achBits = (mask, n = 32) => { const out = []; for (let b = 0; b < n; b++) if ((mask >>> b) & 1) out.push(b); return out; };

/* An episode recorded once (actions + periodic Env snapshots), then replayed
   from any step. Used for policy episodes and for LLM action tapes. */
export class Episode {
  constructor(S, seed, actions = [], every = 25) {
    this.S = S; this.seed = seed; this.actions = actions; this.every = every;
    this.env = S.core.env(); this.env.reset(seed);
    this.snaps = new Map();
    this.unlocks = []; // {bit, step}
    this.cur = 0;
  }
  snapshot() { const b = new Uint8Array(this.S.K.ENV_BYTES); this.env.save(b); this.snaps.set(this.cur, b); }
  /* Play the given actions (or the policy) to the end, recording. Yields to the UI every chunk. */
  async record({ policy = false, rand = rng(0x2545f491), chunk = 300 } = {}) {
    const env = this.env;
    env.reset(this.seed); this.cur = 0; this.snaps.clear(); this.unlocks = []; this.snapshot();
    const out = [];
    let last = 0;
    while (!env.done && (policy || this.cur < this.actions.length)) {
      const a = policy ? policyAction(this.S, env, rand) : this.actions[this.cur];
      env.step(a); out.push(a); this.cur++;
      const ach = env.achievements;
      if (ach !== last) { for (const b of achBits((ach & ~last) >>> 0)) this.unlocks.push({ bit: b, step: this.cur }); last = ach; }
      if (this.cur % this.every === 0) this.snapshot();
      if (this.cur % chunk === 0) await new Promise((r) => setTimeout(r, 0));
    }
    this.actions = out;
    this.final = { steps: env.steps, achievements: env.achievements >>> 0, health: env.health, ret: env.epReturn, done: env.done };
    this.length = out.length;
    return this;
  }
  /* Restore the state after `step` actions. */
  seek(step) {
    step = Math.max(0, Math.min(step, this.length));
    let base = Math.floor(step / this.every) * this.every;
    while (!this.snaps.has(base)) base -= this.every;
    this.env.load(this.snaps.get(base));
    for (let i = base; i < step; i++) this.env.step(this.actions[i]);
    this.cur = step;
    return this.env;
  }
  stepOnce() { if (this.cur < this.length) { this.prev = { x: this.env.px, y: this.env.py }; this.env.step(this.actions[this.cur++]); } return this.env; }
}

/* Draw an env into a canvas with a camera centred on the player. tiles = tiles visible vertically. */
export function draw(S, canvas, env, { tiles = 14, player, time = 0, light = true, walking = false } = {}) {
  const { g, w, h } = fitCanvas(canvas);
  const scale = Math.max(4, h / tiles);
  const p = player || { x: env.px, y: env.py };
  const vw = w / scale, vh = h / scale, K = S.K;
  let x = p.x + 1 - vw / 2, y = p.y - 1 - vh / 2;
  x = vw < K.WORLD_W ? Math.max(0, Math.min(K.WORLD_W - vw, x)) : (K.WORLD_W - vw) / 2;
  y = vh < K.WORLD_H ? Math.max(0, Math.min(K.WORLD_H - vh, y)) : (K.WORLD_H - vh) / 2;
  g.fillStyle = "#121214"; g.fillRect(0, 0, w, h);
  S.renderer.draw(g, env, { x, y, scale, w, h }, { player: p, time, light, walking });
}

/* Whole-world render (map view of a seed), lit everywhere. */
export function drawWorld(S, canvas, env, { light = false } = {}) {
  const K = S.K, { g, w, h } = fitCanvas(canvas);
  const scale = Math.min(w / K.WORLD_W, h / K.WORLD_H);
  g.fillStyle = "#121214"; g.fillRect(0, 0, w, h);
  S.renderer.draw(g, env, { x: 0, y: 0, scale, w, h }, { light });
}

export function achName(S, bit) { return S.core.achNames[bit]; }

/* Parse a terraria-lite action tape (text: header lines, "actions N", one action per line). */
export function parseTape(text) {
  const lines = text.split(/\r?\n/);
  const head = {};
  let i = 0;
  for (; i < lines.length; i++) {
    const l = lines[i].trim();
    if (!l || l.startsWith("#")) continue;
    const [k, ...rest] = l.split(" ");
    head[k] = rest.join(" ");
    if (k === "actions") { i++; break; }
  }
  const actions = [];
  for (; i < lines.length; i++) { const l = lines[i].trim(); if (l) actions.push(+l); }
  return { environment: head.environment ? +head.environment : null, seed: +head.seed, maxSteps: +(head.max_steps || 3000), label: head.label || "", count: +head.actions, actions };
}

/* Run something only while its element is on screen and the tab is visible. */
export function whileVisible(node, onChange) {
  let vis = false;
  const io = new IntersectionObserver((es) => { vis = es[0].isIntersecting; onChange(vis && !document.hidden); }, { threshold: 0.05 });
  io.observe(node);
  document.addEventListener("visibilitychange", () => onChange(vis && !document.hidden));
}
