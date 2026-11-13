// The lab: one replayed episode with the Environment on the left, the Agent
// on the right and the observation / action / reward exchange between them.
import { $, el, fitCanvas, clamp, fmt } from "./ui.js";
import { MemMap } from "./csim.js";

export class Lab {
  constructor(S) {
    this.S = S; this.core = S.core2; this.replay = S.replay;
    this.renderer = S.renderer2;
    this.k = -1; this.tr = null; this.diff = null;
    this.mem = new MemMap(this.core.L);
    this.buildExchange();
  }

  /* State at step k plus the decision taken from it. */
  at(k) {
    const R = this.replay;
    k = R.seek(k);
    if (k !== this.k) {
      const e = R.view, core = this.core;
      const prev = R.prevBytes;
      this.diff = null;
      if (prev) {
        const now = e.bytes(), d = [];
        for (let i = 0; i < now.length; i++) if (now[i] !== prev[i]) d.push(i);
        this.diff = d;
      }
      if (!R.done || k < R.length) {
        R.extend(0);
        const op = e.observe(); e.mask();
        this.action = k < R.length ? R.actions[k] : 0;
        this.tr = core.trace(op, e.maskPtr, this.action);
      }
      this.obs = e.obs(); this.maskArr = e.mask();
      this.k = k;
    }
    return k;
  }

  buildExchange() {
    const svg = $("#exchange"), NS = "http://www.w3.org/2000/svg";
    const mk = (t, a) => { const n = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a)) n.setAttribute(k, v); svg.append(n); return n; };
    const defs = document.createElementNS(NS, "defs"); svg.append(defs);
    defs.innerHTML = ["obs:#6aa8ff", "act:#ef7b5f", "rew:#f3c63c"].map((s) => { const [id, c] = s.split(":"); return `<marker id="m-${id}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="${c}"/></marker>`; }).join("");
    const lane = (y, dir, c, id, label) => {
      const x0 = dir > 0 ? 6 : 154, x1 = dir > 0 ? 154 : 6;
      mk("line", { x1: x0, y1: y, x2: x1, y2: y, stroke: c, "stroke-width": 2, "stroke-opacity": 0.5, "marker-end": `url(#m-${id})` });
      const t = mk("text", { x: 80, y: y - 12, "text-anchor": "middle", fill: c, "font-size": 11, "font-family": "ui-monospace, Menlo, monospace" });
      const [main, sub] = label.split("_");
      t.textContent = main;
      if (sub) { const ts = document.createElementNS(NS, "tspan"); ts.setAttribute("baseline-shift", "sub"); ts.setAttribute("font-size", 8); ts.textContent = sub; t.append(ts); }
      const v = mk("text", { x: 80, y: y + 22, "text-anchor": "middle", fill: "#e9e6e1", "font-size": 10, "font-family": "ui-monospace, Menlo, monospace" });
      const dot = mk("circle", { cx: x0, cy: y, r: 6, fill: c });
      return { v, dot, x0, x1 };
    };
    this.lanes = {
      obs: lane(110, 1, "#6aa8ff", "obs", "observation o_t"),
      act: lane(210, -1, "#ef7b5f", "act", "action a_t"),
      rew: lane(310, 1, "#f3c63c", "rew", "reward r_t+1"),
    };
  }

  drawExchange(frac) {
    const K = this.core.L, R = this.replay, k = this.k;
    const ph = [[0, 0.34], [0.33, 0.67], [0.66, 1]];
    ["obs", "act", "rew"].forEach((n, i) => {
      const L = this.lanes[n], t = clamp((frac - ph[i][0]) / (ph[i][1] - ph[i][0]));
      L.dot.setAttribute("cx", L.x0 + (L.x1 - L.x0) * t);
      L.dot.setAttribute("opacity", t > 0 && t < 1 ? 1 : 0.15);
    });
    this.lanes.obs.v.textContent = `${fmt(K.VIEW_W * K.VIEW_H * (K.TILE_COUNT + 1) + K.VIEW_W * K.VIEW_H + K.OBS_STATUS_LEN)} floats`;
    const a = this.action ?? 0;
    this.lanes.act.v.textContent = `${a} · ${this.core.actionNames[a]}`;
    const r = k < R.length ? R.rewards[k] : 0;
    this.lanes.rew.v.textContent = r ? (r > 0 ? `+${r}` : `${r}`) : "0";
    this.lanes.rew.v.setAttribute("fill", r > 0 ? "#f3c63c" : r < 0 ? "#ff6060" : "#8b8b94");
  }

  head() {
    const e = this.replay.view, R = this.replay;
    let n = 0; for (let b = e.achievements; b; b >>>= 1) n += b & 1;
    $("#lab-head").innerHTML = `<span>seed <b>${R.seed}</b></span><span>step <b>${this.k}</b> / 3000</span><span>achievements <b>${n}</b> / 32</span><span>return <b>${e.epReturn.toFixed(0)}</b></span><span>health <b>${e.health}</b></span><span>depth <b>${e.py}</b></span><span class="muted">${e.msg}</span>`;
  }

  /* Mini world on the env side; obs window outlined; target of the next action marked. */
  drawWorld(canvas, opts = {}) {
    const { g, w, h } = fitCanvas(canvas);
    const e = this.replay.view, K = this.core.L;
    const s = opts.scale ?? Math.max(8, Math.floor(Math.min(w / 30, h / 18)));
    const view = { x: e.px + 1 - w / s / 2, y: e.py - 1 - h / s / 2, scale: s, w, h };
    this.renderer.draw(g, e, view, { time: performance.now() / 1000 });
    const ox = (e.px - (K.VIEW_W >> 1) - view.x) * s, oy = (e.py - (K.VIEW_H >> 1) - view.y) * s;
    if (opts.window !== false) {
      g.setLineDash([6, 4]); g.strokeStyle = "#6aa8ff"; g.lineWidth = 2;
      g.strokeRect(ox, oy, K.VIEW_W * s, K.VIEW_H * s); g.setLineDash([]);
    }
    if (opts.saliency && this.tr) {
      const sal = this.tr.saliency, mx = Math.max(...sal) || 1;
      for (let i = 0; i < sal.length; i++) {
        const x = ox + (i % K.VIEW_W) * s, y = oy + Math.floor(i / K.VIEW_W) * s, v = sal[i] / mx;
        g.fillStyle = `rgba(239,123,95,${0.75 * v * opts.saliency})`; g.fillRect(x, y, s, s);
      }
    }
    const a = this.action ?? 0;
    if (a >= K.MINE_FIRST && a < K.PLACE_FIRST + K.REACH_COUNT) {
      const r = this.core.reach[(a - K.MINE_FIRST) % K.REACH_COUNT];
      g.strokeStyle = a < K.PLACE_FIRST ? "#ffd84a" : "#6aa8ff"; g.lineWidth = 3;
      g.strokeRect((e.px + r.dx - view.x) * s + 1.5, (e.py + r.dy - view.y) * s + 1.5, s - 3, s - 3);
    }
    return { view, ox, oy, s };
  }

  envMachine() {
    const e = this.replay.view, d = this.diff;
    const rng = e.rng.toString(16).padStart(16, "0");
    $("#lab-env-machine").innerHTML =
      `<div><span class="c-env">env_step</span>(e, <b>${this.action ?? 0}</b>) → ${d ? d.length : 0} of ${fmt(this.core.L.ENV_BYTES)} bytes changed</div>` +
      `<div>e-&gt;rng = 0x${rng}  ·  e-&gt;steps = ${e.steps}</div>`;
    this.mem.draw($("#lab-mem"), e.bytes(), d, this.k);
  }

  /* Agent side: compact network glyph and the top of π. */
  drawAgentMini(frac = 0) {
    const tr = this.tr; if (!tr) return;
    const core = this.core, K = core.L;
    {
      const { g, w, h } = fitCanvas($("#lab-net-mini"));
      g.clearRect(0, 0, w, h);
      g.font = "10px ui-monospace, Menlo, monospace";
      const act = (v, a = 1) => (v >= 0 ? `rgba(195,155,255,${Math.min(1, Math.abs(v)) * a})` : `rgba(106,168,255,${Math.min(1, Math.abs(v)) * a})`);
      const cs = Math.max(4, Math.min(12, (w - 80) / 44, (h - 60) / 16));
      const cells = avgCells(tr.cells, 99, 32);
      const blocks = [
        { cols: K.VIEW_W, rows: K.VIEW_H, v: cells, label: "99 cell codes" },
        { cols: 8, rows: 16, v: tr.g1, label: "h₁ (128)" },
        { cols: 8, rows: 16, v: tr.g, label: "h₂ (128)" },
        { cols: 6, rows: 14, v: tr.probs, label: "π (83)", probs: true },
      ];
      const total = blocks.reduce((a, b) => a + b.cols * cs, 0), gap = (w - total) / (blocks.length + 1);
      let x = gap;
      const cy = h / 2 - 6, rects = [];
      for (const b of blocks) {
        const bw = b.cols * cs, bh = b.rows * cs, y = cy - bh / 2;
        for (let i = 0; i < b.cols * b.rows; i++) {
          if (i >= b.v.length) break;
          const v = b.v[i];
          g.fillStyle = b.probs ? `rgba(239,123,95,${Math.min(1, 0.06 + v * 3)})` : act(v);
          g.fillRect(x + (i % b.cols) * cs, y + Math.floor(i / b.cols) * cs, cs - 1, cs - 1);
        }
        g.fillStyle = "#8b8b94"; g.textAlign = "center"; g.fillText(b.label, x + bw / 2, y + bh + 14); g.textAlign = "left";
        rects.push({ x, y, w: bw, h: bh }); x += bw + gap;
      }
      // flow: a pulse travels left to right once per step
      for (let i = 0; i < rects.length - 1; i++) {
        const a = rects[i], b = rects[i + 1], x0 = a.x + a.w + 4, x1 = b.x - 4;
        g.strokeStyle = "rgba(195,155,255,.25)"; g.beginPath(); g.moveTo(x0, cy); g.lineTo(x1, cy); g.stroke();
        const t = clamp(frac * 3 - i);
        if (t > 0 && t < 1) { g.fillStyle = "#c39bff"; g.beginPath(); g.arc(x0 + (x1 - x0) * t, cy, 3, 0, 7); g.fill(); }
      }
      g.fillStyle = "#e9e6e1"; g.font = "11px ui-monospace, Menlo, monospace";
      g.fillText(`V(s) = ${tr.value.toFixed(2)}   H(π) = ${tr.entropy.toFixed(2)}   log π(aₜ) = ${tr.logp.toFixed(2)}`, 4, 12);
    }
    {
      const { g, w, h } = fitCanvas($("#lab-probs-mini"));
      g.clearRect(0, 0, w, h);
      const top = [...tr.probs.keys()].sort((a, b) => tr.probs[b] - tr.probs[a]).slice(0, 8);
      g.font = "11px ui-monospace, Menlo, monospace";
      top.forEach((a, i) => {
        const y = 4 + i * 19, p = tr.probs[a];
        g.fillStyle = a === this.action ? "#ef7b5f" : "#33333d"; g.fillRect(150, y, (w - 190) * p, 13);
        g.fillStyle = a === this.action ? "#ef7b5f" : "#e9e6e1"; g.fillText(core.actionNames[a].slice(0, 20), 0, y + 11);
        g.fillStyle = "#8b8b94"; g.fillText((p * 100).toFixed(0) + "%", w - 36, y + 11);
      });
    }
  }
}

/* Per-cell activation strength (L2 norm of its 32-dim code), scaled to [0, 1]. */
export function avgCells(cells, n, c) {
  const out = new Float32Array(n);
  let mx = 1e-6;
  for (let i = 0; i < n; i++) { let s = 0; for (let j = 0; j < c; j++) s += cells[i * c + j] ** 2; out[i] = Math.sqrt(s); mx = Math.max(mx, out[i]); }
  for (let i = 0; i < n; i++) out[i] /= mx;
  return out;
}
