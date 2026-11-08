// Small SVG chart kit: horizontal bars with CIs and seed dots, scatter (with
// an optional Pareto frontier and log x), line/step charts, and HTML heatmaps.
// Charts redraw on container resize and theme change. Colours are CSS
// variables, so light/dark themes need no redraw logic of their own.
// Sample (placeholder) marks are drawn hollow with a dashed outline.
import { el, withTip, esc } from "./common.js";

const NS = "http://www.w3.org/2000/svg";
export function s(tag, attrs = {}, ...kids) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null && v !== false) n.setAttribute(k, v);
  for (const k of kids.flat()) if (k != null && k !== false) n.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return n;
}

/* Mount a chart: draw(width) returns an <svg>. Redraws when the width changes. */
export function mount(container, draw, { label } = {}) {
  const fig = container.classList?.contains("chart") ? container : container.appendChild(el("div", { class: "chart" }));
  let last = 0;
  const render = () => {
    const w = Math.max(280, Math.floor(fig.clientWidth || 600));
    if (w === last && fig.firstChild) return;
    last = w;
    const svg = draw(w);
    if (!svg.getAttribute("role")) svg.setAttribute("role", "group");
    if (label) svg.setAttribute("aria-label", label);
    fig.replaceChildren(svg);
  };
  render();
  fig._ro?.disconnect();
  fig._ro = new ResizeObserver(() => render());
  fig._ro.observe(fig);
  return { el: fig, redraw: () => { last = 0; render(); } };
}

/* ---- scales and ticks ---- */
export function linear([d0, d1], [r0, r1]) {
  const f = (x) => r0 + ((x - d0) / (d1 - d0 || 1)) * (r1 - r0);
  f.domain = [d0, d1]; f.ticks = (n = 5) => niceTicks(d0, d1, n); return f;
}
export function log10([d0, d1], [r0, r1]) {
  const a = Math.log10(d0), b = Math.log10(d1);
  const f = (x) => r0 + ((Math.log10(Math.max(x, 1e-12)) - a) / (b - a || 1)) * (r1 - r0);
  f.domain = [d0, d1];
  f.ticks = () => { const t = []; for (let e = Math.floor(a); e <= Math.ceil(b); e++) if (10 ** e >= d0 * 0.999 && 10 ** e <= d1 * 1.001) t.push(10 ** e); return t; };
  return f;
}
export function niceTicks(a, b, n = 5) {
  const span = b - a, step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0)), r = step0 / mag;
  const step = (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * mag;
  const out = []; for (let v = Math.ceil(a / step) * step; v <= b + step * 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}
const color = (c) => (c && c.startsWith("--") ? `var(${c})` : c || "var(--fg)");

function markAttrs(color0, sample, filled = true) {
  return sample
    ? { style: `fill:${color(color0)};fill-opacity:.12;stroke:${color(color0)};stroke-dasharray:3 2;stroke-width:1.4` }
    : { style: `fill:${filled ? color(color0) : "var(--panel)"};stroke:${color(color0)};stroke-width:1.4` };
}

/* ---- horizontal bars ----
   rows: [{label, sub, icon(url), value, lo, hi, dots: [numbers], color, sample, tip}]
   opts: {domain:[a,b], xLabel, fmt, ref (vertical reference line value), refLabel, rowH} */
export function bars(container, rows, opts = {}) {
  const fmtv = opts.fmt || ((v) => v.toFixed(2));
  return mount(container, (W) => {
    const narrow = W < 560;
    const labelW = opts.labelW ?? (narrow ? Math.min(150, W * 0.38) : Math.min(300, W * 0.36));
    const rowH = opts.rowH || 26, top = 8, bottom = 38, valW = narrow ? 44 : 60;
    const H = top + rows.length * rowH + bottom;
    const lo = opts.domain?.[0] ?? Math.min(0, ...rows.flatMap((r) => [r.lo ?? r.value, ...(r.dots || [])]));
    const hi = opts.domain?.[1] ?? Math.max(...rows.flatMap((r) => [r.hi ?? r.value, ...(r.dots || [])])) * 1.05;
    const x = (opts.log ? log10 : linear)([lo, hi], [labelW + 8, W - valW]);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    const grid = s("g", { class: "grid" });
    for (const t of x.ticks(narrow ? 4 : 6)) {
      grid.append(s("line", { x1: x(t), x2: x(t), y1: top, y2: H - bottom + 4 }));
      svg.append(s("text", { class: "tick", x: x(t), y: H - bottom + 18, "text-anchor": "middle" }, opts.tickFmt ? opts.tickFmt(t) : t));
    }
    svg.prepend(grid);
    if (opts.xLabel) svg.append(s("text", { class: "lbl muted", x: (labelW + W - valW) / 2, y: H - 4, "text-anchor": "middle" }, opts.xLabel));
    rows.forEach((r, i) => {
      const y = top + i * rowH, cy = y + rowH / 2;
      const g = s("g", { tabindex: 0, role: "listitem", "aria-label": `${r.label}: ${r.value == null ? "no data" : fmtv(r.value)}${r.sample ? " (sample data)" : ""}` });
      let lx = labelW;
      const tl = s("text", { x: lx, y: cy + 4, "text-anchor": "end", style: r.sample ? "font-style:italic;fill:var(--muted)" : null }, truncate(r.label, narrow ? 22 : 46));
      g.append(tl);
      if (r.icon) g.append(s("image", { href: r.icon, x: labelW - (narrow ? 22 : 24) - textW(truncate(r.label, narrow ? 22 : 46)), y: cy - 9, width: 18, height: 18, style: "image-rendering:pixelated" }));
      if (r.value != null) {
        const x0 = x(opts.log ? lo : Math.max(lo, 0)), x1 = x(r.value), st = markAttrs(r.color || "--rl", r.sample).style;
        g.append(s("rect", { x: Math.min(x0, x1), y: y + 5, width: Math.max(1, Math.abs(x1 - x0)), height: rowH - 10, rx: 2, style: st + (r.sample ? "" : ";fill-opacity:.85") }));
        if (r.lo != null && r.hi != null) {
          g.append(s("line", { x1: x(r.lo), x2: x(r.hi), y1: cy, y2: cy, style: "stroke:var(--fg);stroke-width:1.5" }),
            s("line", { x1: x(r.lo), x2: x(r.lo), y1: cy - 5, y2: cy + 5, style: "stroke:var(--fg);stroke-width:1.5" }),
            s("line", { x1: x(r.hi), x2: x(r.hi), y1: cy - 5, y2: cy + 5, style: "stroke:var(--fg);stroke-width:1.5" }));
        }
        for (const d of r.dots || []) g.append(s("circle", { cx: x(d), cy, r: 2.6, style: "fill:var(--panel);stroke:var(--fg);stroke-width:1" }));
        g.append(s("text", { x: W - valW + 6, y: cy + 4, class: "num" }, fmtv(r.value)));
      } else {
        g.append(s("text", { x: labelW + 12, y: cy + 4, class: "lbl muted" }, r.missing || "no data"));
      }
      const tipHtml = r.tip || `<b>${esc(r.label)}</b><br>${r.value == null ? "no data" : fmtv(r.value)}${r.lo != null ? ` [${fmtv(r.lo)}, ${fmtv(r.hi)}]` : ""}${r.dots?.length ? `<br>seeds: ${r.dots.map(fmtv).join(", ")}` : ""}${r.sample ? "<br><i>sample data</i>" : ""}`;
      hover(g, tipHtml);
      svg.append(g);
    });
    if (opts.ref != null) {
      svg.append(s("line", { x1: x(opts.ref), x2: x(opts.ref), y1: top - 4, y2: H - bottom + 4, style: "stroke:var(--accent);stroke-width:1.5;stroke-dasharray:4 3" }));
      if (opts.refLabel) svg.append(s("text", { x: x(opts.ref) + 4, y: top + 6, class: "lbl", style: "fill:var(--accent);font-size:11px" }, opts.refLabel));
    }
    svg.setAttribute("role", "list");
    return svg;
  }, { label: opts.label });
}

/* ---- scatter ----
   points: [{x, y, ylo, yhi, label, color, shape, sample, tip, href}]
   opts: {xLog, xDomain, yDomain, xLabel, yLabel, xFmt, yFmt, frontier: bool, height, labels: bool} */
export function scatter(container, points, opts = {}) {
  return mount(container, (W) => {
    const H = opts.height || Math.max(260, Math.min(420, W * 0.55));
    const m = { l: 52, r: 16, t: 14, b: 44 };
    const xs = points.map((p) => p.x).filter((v) => v != null), ys = points.flatMap((p) => [p.y, p.ylo, p.yhi]).filter((v) => v != null);
    const xd = opts.xDomain || (opts.xLog ? [10 ** Math.floor(Math.log10(Math.min(...xs))), 10 ** Math.ceil(Math.log10(Math.max(...xs)))] : padDomain(xs));
    const yd = opts.yDomain || padDomain(ys);
    const x = (opts.xLog ? log10 : linear)(xd, [m.l, W - m.r]);
    const y = linear(yd, [H - m.b, m.t]);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    axes(svg, x, y, W, H, m, opts);
    if (opts.frontier) {
      // upper-left Pareto frontier: lowest x for each new best y (non-sample points only)
      const real = points.filter((p) => !p.sample && p.x != null && p.y != null).sort((a, b) => a.x - b.x || b.y - a.y);
      const f = []; let best = -Infinity;
      for (const p of real) if (p.y > best) { f.push(p); best = p.y; }
      if (f.length > 1) {
        let d = `M${x(f[0].x)},${y(f[0].y)}`;
        for (let i = 1; i < f.length; i++) d += `H${x(f[i].x)}V${y(f[i].y)}`;
        d += `H${W - m.r}`;
        svg.append(s("path", { d, style: "fill:none;stroke:var(--muted);stroke-width:1.2;stroke-dasharray:5 4" }));
      }
    }
    const placed = [];
    const free = (bx, by, bw) => !placed.some((b) => bx < b.x + b.w && bx + bw > b.x && by - 11 < b.y && by > b.y - 11);
    for (const p of points) {
      if (p.x == null || p.y == null) continue;
      const g = s("g", { tabindex: 0, "aria-label": `${p.label}: ${opts.yFmt ? opts.yFmt(p.y) : p.y}${p.sample ? " (sample data)" : ""}` });
      if (p.ylo != null) g.append(s("line", { x1: x(p.x), x2: x(p.x), y1: y(p.ylo), y2: y(p.yhi), style: `stroke:${color(p.color)};stroke-width:1.5;opacity:.8` }));
      g.append(shape(p.shape, x(p.x), y(p.y), p.r || 5.5, markAttrs(p.color, p.sample, p.filled !== false)));
      if (opts.labels && p.short && W >= 520) {
        const bw = p.short.length * 6.2, px0 = x(p.x), py0 = y(p.y);
        const cands = [[px0 + 8, py0 - 7], [px0 + 8, py0 + 14], [px0 - 8 - bw, py0 - 7], [px0 - 8 - bw, py0 + 14]];
        const spot = cands.find(([cx, cy]) => cx > m.l && cx + bw < W && free(cx, cy, bw));
        if (spot) {
          placed.push({ x: spot[0], y: spot[1], w: bw });
          g.append(s("text", { x: spot[0], y: spot[1], style: `font-size:11px;fill:${p.sample ? "var(--muted)" : "var(--fg)"}` }, p.short));
        }
      }
      hover(g, p.tip || `<b>${esc(p.label)}</b>`);
      if (p.href) g.addEventListener("click", () => { location.href = p.href; });
      svg.append(g);
    }
    return svg;
  }, { label: opts.label });
}

/* ---- lines ----
   series: [{label, color, points: [[x, y]], dash, width, sample, step, band: [[x, lo, hi]]}] */
export function lines(container, series, opts = {}) {
  return mount(container, (W) => {
    const H = opts.height || Math.max(240, Math.min(380, W * 0.5));
    const m = { l: 52, r: opts.rightPad ?? 16, t: 14, b: 44 };
    const all = series.flatMap((sr) => sr.points);
    const xd = opts.xDomain || [Math.min(...all.map((p) => p[0])), Math.max(...all.map((p) => p[0]))];
    const yd = opts.yDomain || padDomain(all.map((p) => p[1]));
    const x = (opts.xLog ? log10 : linear)(xd, [m.l, W - m.r]);
    const y = linear(yd, [H - m.b, m.t]);
    const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H });
    axes(svg, x, y, W, H, m, opts);
    for (const sr of series) {
      if (sr.band) {
        let d = sr.band.map((p, i) => `${i ? "L" : "M"}${x(p[0])},${y(p[2])}`).join("");
        d += [...sr.band].reverse().map((p) => `L${x(p[0])},${y(p[1])}`).join("") + "Z";
        svg.append(s("path", { d, style: `fill:${color(sr.color)};opacity:.13` }));
      }
      const pts = sr.points.filter((p) => p[1] != null);
      if (!pts.length) continue;
      let d = `M${x(pts[0][0])},${y(pts[0][1])}`;
      for (let i = 1; i < pts.length; i++) d += sr.step ? `H${x(pts[i][0])}V${y(pts[i][1])}` : `L${x(pts[i][0])},${y(pts[i][1])}`;
      const dash = sr.sample ? "6 4" : sr.dash || null;
      const path = s("path", { d, style: `fill:none;stroke:${color(sr.color)};stroke-width:${sr.width || 2};${dash ? `stroke-dasharray:${dash};` : ""}opacity:${sr.opacity ?? 1}` });
      const g = s("g", { tabindex: sr.label && !sr.quiet ? 0 : null, "aria-label": sr.label ? `${sr.label}${sr.sample ? " (sample data)" : ""}` : null });
      g.append(path);
      // fat invisible hit area for hover
      if (sr.label && !sr.quiet) {
        g.append(s("path", { d, style: "fill:none;stroke:transparent;stroke-width:10" }));
        const last = pts[pts.length - 1];
        hover(g, sr.tip || `<b>${esc(sr.label)}</b><br>last: ${opts.yFmt ? opts.yFmt(last[1]) : last[1].toFixed(2)}${sr.sample ? "<br><i>sample data</i>" : ""}`);
        if (opts.endLabels && W > 560) svg.append(s("text", { x: x(last[0]) + 6, y: y(last[1]) + 4, style: `font-size:11px;fill:${color(sr.color)}` }, sr.short || sr.label));
      }
      svg.append(g);
    }
    if (opts.vlines) for (const v of opts.vlines) {
      svg.append(s("line", { x1: x(v.x), x2: x(v.x), y1: m.t, y2: H - m.b, style: "stroke:var(--accent);stroke-dasharray:4 3" }),
        s("text", { x: x(v.x) + 4, y: m.t + 10, style: "font-size:11px;fill:var(--accent)" }, v.label));
    }
    if (opts.hlines) for (const v of opts.hlines) {
      svg.append(s("line", { x1: m.l, x2: W - m.r, y1: y(v.y), y2: y(v.y), style: "stroke:var(--muted);stroke-dasharray:4 3" }),
        s("text", { x: m.l + 4, y: y(v.y) - 4, style: "font-size:11px;fill:var(--muted)" }, v.label));
    }
    return svg;
  }, { label: opts.label });
}

function axes(svg, x, y, W, H, m, opts) {
  const grid = s("g", { class: "grid" });
  const xt = opts.xTicks || x.ticks(W < 500 ? 4 : 7), yt = opts.yTicks || y.ticks(5);
  for (const t of yt) {
    grid.append(s("line", { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t) }));
    svg.append(s("text", { class: "tick", x: m.l - 6, y: y(t) + 4, "text-anchor": "end" }, opts.yFmt ? opts.yFmt(t) : t));
  }
  for (const t of xt) {
    grid.append(s("line", { x1: x(t), x2: x(t), y1: m.t, y2: H - m.b }));
    svg.append(s("text", { class: "tick", x: x(t), y: H - m.b + 16, "text-anchor": "middle" }, opts.xFmt ? opts.xFmt(t) : t));
  }
  svg.prepend(grid);
  svg.append(s("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, style: "stroke:var(--muted)" }));
  if (opts.xLabel) svg.append(s("text", { class: "lbl muted", x: (m.l + W - m.r) / 2, y: H - 6, "text-anchor": "middle" }, opts.xLabel));
  if (opts.yLabel) svg.append(s("text", { class: "lbl muted", x: 12, y: (m.t + H - m.b) / 2, "text-anchor": "middle", transform: `rotate(-90 12 ${(m.t + H - m.b) / 2})` }, opts.yLabel));
}

function shape(kind, cx, cy, r, attrs) {
  if (kind === "square") return s("rect", { x: cx - r * 0.9, y: cy - r * 0.9, width: r * 1.8, height: r * 1.8, ...attrs });
  if (kind === "diamond") return s("path", { d: `M${cx},${cy - r * 1.25}L${cx + r * 1.25},${cy}L${cx},${cy + r * 1.25}L${cx - r * 1.25},${cy}Z`, ...attrs });
  if (kind === "triangle") return s("path", { d: `M${cx},${cy - r * 1.2}L${cx + r * 1.15},${cy + r * 0.9}L${cx - r * 1.15},${cy + r * 0.9}Z`, ...attrs });
  return s("circle", { cx, cy, r, ...attrs });
}

function padDomain(v) {
  const a = Math.min(...v), b = Math.max(...v), p = (b - a || Math.abs(a) || 1) * 0.08;
  return [a - p, b + p];
}
function truncate(t, n) { return t.length > n ? `${t.slice(0, n - 1)}...` : t; }
function textW(t) { return t.length * 6.3; }
function hover(g, html) {
  g.style.cursor = "default";
  withTip(g, html);
  g.addEventListener("focus", () => g.setAttribute("opacity", ".75"));
  g.addEventListener("blur", () => g.removeAttribute("opacity"));
}

/* ---- legend ---- */
export function legend(items) {
  return el("div", { class: "legend" }, items.map((it) => el("span", {},
    el("i", { class: it.line ? (it.dash ? "dash" : "line") : null, style: it.dash ? { borderColor: color(it.color) } : { background: color(it.color), ...(it.sample ? { background: "transparent", border: `1px dashed ${color(it.color)}` } : {}) } }),
    it.label)));
}

/* ---- heatmap as an HTML table ----
   rows: [{label, sample, cells: [value|null], title}], cols: [{label, icon(Node), title}]
   opts: {fmt(v), scale(v) -> 0..1, max} */
export function heatmap(rows, cols, opts = {}) {
  const fmtv = opts.fmt || ((v) => `${Math.round(100 * v)}`);
  const scale = opts.scale || ((v) => v);
  const t = el("table", { class: "heat" });
  t.append(el("thead", {}, el("tr", {}, el("th", { class: "rowh", scope: "col" }, opts.corner || ""),
    cols.map((c) => el("th", { scope: "col", title: c.title || c.label }, c.icon || "", el("span", { class: "visually-hidden" }, c.label))))));
  const tb = el("tbody", {});
  for (const r of rows) {
    if (r.group) { tb.append(el("tr", { class: "tier-row" }, el("th", { colspan: cols.length + 1 }, r.group))); continue; }
    tb.append(el("tr", { class: r.sample ? "is-sample" : null },
      el("th", { class: "rowh", scope: "row", title: r.title || r.label }, r.label),
      r.cells.map((v, j) => {
        if (v == null) return el("td", { class: "na", title: `${r.label} / ${cols[j].label}: n/a` }, opts.naText ?? "");
        const k = Math.max(0, Math.min(1, scale(v)));
        const bg = `color-mix(in srgb, var(--heat1) ${Math.round(k * 100)}%, var(--heat0))`;
        const fg = k > 0.55 ? "var(--bg)" : "var(--fg)";
        return el("td", { style: { background: bg, color: fg, ...(r.sample ? { outline: "1px dashed var(--muted)", outlineOffset: "-2px" } : {}) }, title: `${r.label} / ${cols[j].label}: ${fmtv(v)}${r.sample ? " (sample data)" : ""}` }, fmtv(v));
      })));
  }
  t.append(tb);
  return el("div", { class: "table-wrap" }, t);
}
