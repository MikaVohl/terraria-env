// node tools/viz_policy_check.mjs <policy.bin> <obs-rows.bin> <n>
// Prints [logits(83), value] per Obs row as one flat JSON array, computed by
// viz/terraria.wasm. Called by tools/viz_export_policy.py.
import { readFileSync } from "node:fs";

const [blobPath, obsPath, nStr] = process.argv.slice(2);
const f = Math.fround;
const { instance } = await WebAssembly.instantiate(readFileSync(new URL("../viz/terraria.wasm", import.meta.url)), {
  env: { sinf: (x) => f(Math.sin(x)), cosf: (x) => f(Math.cos(x)), logf: (x) => f(Math.log(x)) },
});
const w = instance.exports;
const half = new Uint16Array(readFileSync(blobPath).buffer.slice(0));
const lay = new Int32Array(w.memory.buffer, w.w_malloc(512), 128);
w.w_layout(lay.byteOffset);
const OBS = lay[1], ACTS = lay[41], n = Number(nStr);
const wp = w.w_malloc(half.length * 4);
const dst = new Float32Array(w.memory.buffer, wp, half.length);
for (let i = 0; i < half.length; i++) {
  const h = half[i], s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 31, m = h & 1023;
  dst[i] = e === 0 ? s * m * 2 ** -24 : e === 31 ? (m ? NaN : s * Infinity) : s * (1 + m / 1024) * 2 ** (e - 15);
}
if (w.w_policy_init(wp, 128, 32) !== half.length) throw new Error("blob size mismatch");
const rows = readFileSync(obsPath);
const op = w.w_malloc(OBS * n), lp = w.w_malloc(ACTS * 4 * n), vp = w.w_malloc(4 * n);
new Uint8Array(w.memory.buffer, op, OBS * n).set(rows);
w.w_policy_forward(op, n, lp, vp);
const L = new Float32Array(w.memory.buffer, lp, ACTS * n), V = new Float32Array(w.memory.buffer, vp, n), out = [];
for (let i = 0; i < n; i++) { for (let a = 0; a < ACTS; a++) out.push(L[i * ACTS + a]); out.push(V[i]); }
console.log(JSON.stringify(out));
