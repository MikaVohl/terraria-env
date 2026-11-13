// Wasm half of tools/viz_parity.py: same worlds, same action rule, same digest.
// Usage: node tools/viz_parity.mjs viz/terraria.wasm   -> prints the sha256 hex
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";

const f = Math.fround;
const bytes = readFileSync(process.argv[2] ?? "viz/terraria.wasm");
const { instance } = await WebAssembly.instantiate(bytes, {
  env: { sinf: (x) => f(Math.sin(x)), cosf: (x) => f(Math.cos(x)), logf: (x) => f(Math.log(x)) },
});
const w = instance.exports;
const lay = new Int32Array(w.memory.buffer, w.w_malloc(4 * 128), 128);
w.w_layout(lay.byteOffset);
const ENV = lay[0], OBS = lay[1], ACTS = lay[41];
const h = createHash("sha256");
const env = w.w_create(0), obs = w.w_malloc(OBS), mask = w.w_malloc(ACTS);
const mem = () => new Uint8Array(w.memory.buffer);
const digest = () => {
  w.w_obs(env, obs); w.w_mask(env, mask);
  const m = mem();
  h.update(m.subarray(env, env + ENV)); h.update(m.subarray(obs, obs + OBS)); h.update(m.subarray(mask, mask + ACTS));
};
const reset = (s) => w.w_reset(env, s >>> 0, Math.floor(s / 2 ** 32));
for (let s = 0; s < 64; s++) { reset(s); digest(); }
for (let s = 23000001; s < 23000017; s++) { reset(s); digest(); }
// Legal action chosen by a 32-bit LCG (Numerical Recipes), replicated in Python.
let x = 12345;
for (let ep = 0; ep < 4; ep++) {
  reset(500 + ep);
  for (let t = 0; t < 3000; t++) {
    w.w_mask(env, mask);
    const m = mem().subarray(mask, mask + ACTS), legal = [];
    for (let a = 0; a < ACTS; a++) if (m[a]) legal.push(a);
    x = (Math.imul(x, 1664525) + 1013904223) >>> 0;
    w.w_step(env, legal[x % legal.length]);
    digest();
    const v = new DataView(w.memory.buffer);
    if (v.getUint8(env + lay[28]) || v.getUint8(env + lay[29])) break;
  }
}
console.log(h.digest("hex"));
