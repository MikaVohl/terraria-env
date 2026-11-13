// Zoom: inside the environment. The live Env struct, one pixel per byte, with
// the bytes the last env_step changed; the RNG; an in-tab throughput benchmark.
import { $, el, fitCanvas, fmt, human } from "./ui.js";

/* Env bytes as an image, one pixel per byte, coloured by field; bytes the
   last step changed flash white and fade. */
export class MemMap {
  constructor(K) {
    const wh = K.WORLD_W * K.WORLD_H;
    this.K = K;
    this.regions = [
      ["tiles[96][128]", K.TILES, wh, [151, 107, 75]], ["light[96][128]", K.LIGHT, wh, [243, 198, 60]],
      ["terrain_light", K.TERRAIN_LIGHT, wh, [180, 150, 60]], ["object_part", K.OBJECT_PART, wh, [111, 211, 155]],
      ["sky_cutoff, surface", K.SKY_CUTOFF, K.PX - K.SKY_CUTOFF, [106, 168, 255]],
      ["player: pos, jump, fall, hp", K.PX, K.TOOL_TIER - K.PX, [239, 123, 95]],
      ["tool, inventory[33], selected", K.TOOL_TIER, K.MAX_HEALTH - K.TOOL_TIER, [195, 155, 255]],
      ["cooldowns, flags", K.MAX_HEALTH, K.MOBS - K.MAX_HEALTH, [239, 123, 95]],
      ["mobs[8], chests[10]", K.MOBS, K.ACH - K.MOBS, [255, 100, 120]],
      ["achievements", K.ACH, 4, [255, 216, 74]], ["rng (PCG32)", K.RNG, 8, [255, 255, 255]], ["seed", K.SEED, 8, [200, 200, 200]],
      ["steps, reward, return…", K.STEPS, K.MSG - K.STEPS, [111, 211, 155]], ["msg[64]", K.MSG, K.ENV_BYTES - K.MSG, [150, 150, 160]],
    ];
    this.heat = new Float32Array(K.ENV_BYTES);
    this.img = new ImageData(256, Math.ceil(K.ENV_BYTES / 256));
    this.off = new OffscreenCanvas(this.img.width, this.img.height);
    this.lastK = -1;
  }
  draw(canvas, bytes, diff, k) {
    const K = this.K, d = this.img.data;
    if (k !== this.lastK) { for (const i of diff ?? []) this.heat[i] = 1; this.lastK = k; }
    for (const [, start, len, c] of this.regions) for (let i = start; i < start + len; i++) {
      const v = bytes[i] / 255, hv = this.heat[i], j = i * 4;
      const b = 0.18 + 0.82 * Math.min(1, v * (i < K.PX ? 6 : 1.5));
      d[j] = c[0] * b * (1 - hv) + 255 * hv; d[j + 1] = c[1] * b * (1 - hv) + 255 * hv; d[j + 2] = c[2] * b * (1 - hv) + 255 * hv; d[j + 3] = 255;
      this.heat[i] *= 0.9;
    }
    this.off.getContext("2d").putImageData(this.img, 0, 0);
    const { g, w, h } = fitCanvas(canvas);
    g.clearRect(0, 0, w, h);
    const s = Math.min(w / this.img.width, h / this.img.height);
    g.imageSmoothingEnabled = false; g.drawImage(this.off, (w - this.img.width * s) / 2, 0, this.img.width * s, this.img.height * s);
  }
  changedBy(diff) {
    const m = new Map();
    for (const i of diff ?? []) { const r = this.regions.find(([, s, l]) => i >= s && i < s + l); if (r) m.set(r[0], (m.get(r[0]) ?? 0) + 1); }
    return m;
  }
}

export class SimZoom {
  constructor(S, lab) {
    this.S = S; this.lab = lab; const K = S.core2.L;
    const root = $("#zoom-sim");
    this.map = el("canvas", { style: { width: "440px", height: "344px", imageRendering: "pixelated" } });
    this.fields = el("div", { class: "legend", style: { flex: 1, minWidth: "260px" } });
    this.bench = el("div", { class: "legend sub" });
    root.append(el("h3", { class: "c-env" }, `ENVIRONMENT · struct Env, ${fmt(K.ENV_BYTES)} bytes, read live from wasm memory`),
      el("div", { class: "row" }, el("div", {}, el("div", { class: "cap" }, "one pixel per byte · 256 bytes per row · each row of tiles[] is two world rows: the terrain is visible"), this.map), this.fields), this.bench);
    this.mem = new MemMap(K);
    this.benchDone = false;
  }

  draw(sub) {
    const S = this.S, lab = this.lab, K = S.core2.L, e = lab.replay.view, bytes = e.bytes();
    this.bench.classList.toggle("on", sub >= 2);
    this.mem.draw(this.map, bytes, lab.diff, lab.k);
    const changed = this.mem.changedBy(lab.diff);
    const rng = e.rng.toString(16).padStart(16, "0");
    this.fields.innerHTML =
      `<p><span class="c-env">env_step</span>(e, <b>${lab.action}</b>) <span class="muted">// ${S.core2.actionNames[lab.action]}</span></p>` +
      this.mem.regions.map(([n, s, l, c]) => `<div style="display:flex;gap:6px;align-items:center"><span style="width:10px;height:10px;background:rgb(${c})"></span>${n} <span class="muted">@${s}, ${fmt(l)} B</span>${changed.get(n) ? ` <b style="color:#fff">${changed.get(n)} changed</b>` : ""}</div>`).join("") +
      `<p style="margin-top:12px">e-&gt;rng = <b>0x${rng}</b></p>` +
      `<p class="muted">PCG32: state ← state × 6364136223846793005 + 1442695040888963407; output = rotr(((s ⊕ s≫18) ≫ 27), s≫59). One stream per Env, no globals, no rand().</p>` +
      `<p>last step changed <b>${(lab.diff ?? []).length}</b> of ${fmt(K.ENV_BYTES)} bytes.</p>`;
    if (sub >= 2 && !this.benchDone) { this.benchDone = true; this.runBench(); }
  }

  async runBench() {
    const core = this.S.core2, K = core.L, env = core.env(0).reset(777);
    let steps = 0, rng = 12345; const t0 = performance.now();
    this.bench.innerHTML = "<p>benchmarking…</p>";
    while (performance.now() - t0 < 1500) {
      const t1 = performance.now();
      while (performance.now() - t1 < 40) {
        for (let i = 0; i < 64; i++) {
          core.w.w_mask(env.p, env.maskPtr);
          const m = core.u8().subarray(env.maskPtr, env.maskPtr + K.ACT_COUNT);
          let n = 0; for (let a = 0; a < K.ACT_COUNT; a++) n += m[a];
          rng = (Math.imul(rng, 1664525) + 1013904223) >>> 0;
          let pick = rng % n, a = 0; for (; a < K.ACT_COUNT; a++) if (m[a] && pick-- === 0) break;
          core.w.w_step(env.p, a); steps++;
          if (env.done) env.reset(778 + steps);
        }
      }
      await new Promise((r) => requestAnimationFrame(r));
    }
    const sps = (steps * 1000) / (performance.now() - t0);
    this.bench.innerHTML =
      `<p><b class="c-env">${human(sps)}</b> simulator steps per second on one thread of this tab (WebAssembly, random legal actions, mask included).</p>` +
      `<p class="muted">The training run collected about 296k steps/s with the policy in the loop, using 12 native CPU threads for the simulator and the GPU for the network. Speed decides how many experiments fit in a day, and the simulator was designed for it: no allocation, no pointers, snapshots by memcpy.</p>`;
  }
}
