// Small DOM / canvas helpers shared by the chapters.

export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];
export function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(e.style, v);
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const k of kids.flat()) if (k != null) e.append(k.nodeType ? k : document.createTextNode(String(k)));
  return e;
}
/* A canvas holding a copy of an icon at its native resolution (CSS sizes it). */
export function iconCanvas(img) {
  const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
  const g = c.getContext("2d"); g.imageSmoothingEnabled = false; g.drawImage(img, 0, 0); return c;
}
export function htmlH3(cls, html) { const h = document.createElement("h3"); h.className = cls; h.innerHTML = html; return h; }
export const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export const lerp = (a, b, t) => a + (b - a) * t;
export const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
export const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
export const fmt = (n, d = 0) => n.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d });
export function human(n) {
  if (n >= 1e9) return (n / 1e9).toFixed(n >= 1e10 ? 0 : 1) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + "k";
  return String(Math.round(n));
}
export const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/* Canvas sized to its CSS box at device pixel ratio; returns a 2D context in CSS px. */
export function fitCanvas(c) {
  const r = c.getBoundingClientRect(), d = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.round(r.width * d)), h = Math.max(1, Math.round(r.height * d));
  if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
  const g = c.getContext("2d");
  g.setTransform(d, 0, 0, d, 0, 0);
  g.imageSmoothingEnabled = false;
  return { g, w: r.width, h: r.height };
}

/* Rolling line chart. series: [{values, color, label}] */
export function lineChart(g, x, y, w, h, series, opts = {}) {
  g.save();
  g.strokeStyle = "rgba(255,255,255,0.08)"; g.lineWidth = 1;
  g.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
  let lo = opts.min ?? Infinity, hi = opts.max ?? -Infinity;
  if (opts.min == null || opts.max == null) for (const s of series) for (const v of s.values) {
    if (opts.min == null) lo = Math.min(lo, v);
    if (opts.max == null) hi = Math.max(hi, v);
  }
  if (!isFinite(lo)) { lo = 0; hi = 1; }
  if (hi - lo < 1e-6) { hi = lo + 1; }
  const n = opts.n ?? Math.max(...series.map((s) => s.values.length), 2);
  for (const s of series) {
    g.strokeStyle = s.color; g.lineWidth = s.width ?? 1.5; g.beginPath();
    s.values.forEach((v, i) => {
      const px = x + (i / (n - 1)) * w, py = y + h - ((v - lo) / (hi - lo)) * h;
      i ? g.lineTo(px, py) : g.moveTo(px, py);
    });
    g.stroke();
  }
  if (opts.label) {
    g.fillStyle = "#8b8b94"; g.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
    g.fillText(opts.label, x + 6, y + 13);
  }
  if (opts.right) {
    g.fillStyle = series[0]?.color ?? "#fff"; g.textAlign = "right"; g.font = "11px ui-monospace, SFMono-Regular, Menlo, monospace";
    g.fillText(opts.right, x + w - 6, y + 13); g.textAlign = "left";
  }
  g.restore();
  return { lo, hi };
}

/* Diverging colour for signed values in [-1, 1]: blue (negative) .. coral (positive). */
export function diverge(v, a = 1) {
  const t = clamp(Math.abs(v));
  return v >= 0 ? `rgba(239,123,95,${(0.08 + 0.92 * t) * a})` : `rgba(106,168,255,${(0.08 + 0.92 * t) * a})`;
}
export function heat(v, a = 1) { // 0..1, dark -> amber -> white
  const t = clamp(v);
  const r = Math.round(40 + 215 * Math.min(1, t * 1.6)), g = Math.round(30 + 200 * t * t), b = Math.round(40 + 150 * Math.max(0, t - 0.6) * 2.5);
  return `rgba(${r},${g},${b},${a})`;
}

/* Draw a 16x16 icon canvas pixel-perfect at (x, y) with size s. */
export function icon(g, img, x, y, s, alpha = 1) {
  g.save(); g.globalAlpha = alpha; g.imageSmoothingEnabled = false; g.drawImage(img, x, y, s, s); g.restore();
}
