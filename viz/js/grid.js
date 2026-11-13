// Chapters "Scale" and "Training": hundreds of worlds stepped by Web Workers,
// aggregate statistics, and the real training log (viz/data/run.json).
import { $, el, fitCanvas, lineChart, human, fmt, icon } from "./ui.js";

export const GRID = { cols: 16, rows: 16, cellW: 32, cellH: 18 };

export class Grid {
  constructor(S) {
    this.S = S;
    this.count = GRID.cols * GRID.rows;
    this.nWorkers = Math.max(2, Math.min(8, (navigator.hardwareConcurrency || 4) - 2));
    this.image = new ImageData(GRID.cols * GRID.cellW, GRID.rows * GRID.cellH);
    this.canvas = document.createElement("canvas");
    this.canvas.width = this.image.width; this.canvas.height = this.image.height;
    this.ctx = this.canvas.getContext("2d");
    this.workers = []; this.stats = []; this.current = new Array(this.count).fill(0);
    this.started = false; this.running = false; this.samples = [];
    $("#g-envs").textContent = this.count; $("#s-envs").textContent = this.count;
    $("#s-workers").textContent = this.nWorkers; $("#grid-workers").textContent = `· ${this.nWorkers} workers`;
  }

  start() {
    if (this.started) return;
    this.started = true;
    const per = Math.ceil(GRID.rows / this.nWorkers);
    for (let w = 0, row = 0; w < this.nWorkers && row < GRID.rows; w++, row += per) {
      const rows = Math.min(per, GRID.rows - row);
      const worker = new Worker(new URL("./grid.worker.js", import.meta.url), { type: "module" });
      const slot = { worker, row, rows, ready: false };
      worker.onmessage = (ev) => this.onMessage(slot, ev.data);
      worker.postMessage({ type: "init", count: rows * GRID.cols, cols: GRID.cols, cellW: GRID.cellW, cellH: GRID.cellH, palette: this.S.art.tileRGB, seed: 1_000_000 + row * GRID.cols * 1000 });
      this.workers.push(slot);
    }
  }

  onMessage(slot, m) {
    if (m.type === "ready") {
      slot.ready = true; this.sendPolicy(slot);
      slot.worker.postMessage({ type: "speed", stepsPerTick: this.max ? 16 : 2, delayMs: this.max ? 0 : 50 });
      if (this.running) slot.worker.postMessage({ type: "run" });
    } else if (m.type === "frame") {
      const off = slot.row * GRID.cellH * this.image.width * 4;
      this.image.data.set(m.pixels, off);
      this.stats[this.workers.indexOf(slot)] = m.stats;
      m.current.forEach((c, i) => { this.current[slot.row * GRID.cols + i] = c; });
      this.dirty = true;
    }
  }

  sendPolicy(slot) {
    const ck = this.S.policy;
    slot.worker.postMessage({ type: "policy", blob: this.S.blobs[ck.steps].slice(0), hidden: ck.hidden, cellWidth: ck.cell_width });
  }
  policyChanged() { this.stats = []; this.samples = []; for (const s of this.workers) if (s.ready) this.sendPolicy(s); }

  setPace(max) {
    this.max = max;
    for (const s of this.workers) s.worker.postMessage({ type: "speed", stepsPerTick: max ? 16 : 2, delayMs: max ? 0 : 50 });
  }

  setRunning(on) {
    if (on) this.start();
    if (on === this.running) return;
    this.running = on;
    for (const s of this.workers) if (s.ready) s.worker.postMessage({ type: on ? "run" : "pause" });
  }

  totals() {
    const t = { steps: 0, episodes: 0, achSum: 0, deaths: 0, achHits: new Array(32).fill(0), hist: new Array(33).fill(0) };
    for (const s of this.stats) if (s) {
      t.steps += s.steps; t.episodes += s.episodes; t.achSum += s.achSum; t.deaths += s.deaths;
      s.achHits.forEach((v, i) => (t.achHits[i] += v)); s.hist.forEach((v, i) => (t.hist[i] += v));
    }
    return t;
  }

  /* Draw the grid into world canvas g; returns the screen rect of a cell. */
  draw(g, W, H, alpha = 1, highlight = -1) {
    if (this.dirty) { this.ctx.putImageData(this.image, 0, 0); this.dirty = false; }
    const r = this.layout(W, H);
    g.save(); g.globalAlpha = alpha; g.imageSmoothingEnabled = false;
    g.fillStyle = "#0b0b0d"; g.fillRect(r.x - 4, r.y - 4, r.w + 8, r.h + 8);
    // draw cell by cell with gutters
    for (let i = 0; i < this.count; i++) {
      const c = this.cellRect(r, i);
      g.drawImage(this.canvas, (i % GRID.cols) * GRID.cellW, Math.floor(i / GRID.cols) * GRID.cellH, GRID.cellW, GRID.cellH, c.x, c.y, c.w, c.h);
      const a = this.current[i];
      if (a > 0) { g.fillStyle = `rgba(243,198,60,${Math.min(1, a / 28)})`; g.fillRect(c.x, c.y + c.h - 2, (c.w * a) / 32, 2); }
    }
    if (highlight >= 0) {
      const c = this.cellRect(r, highlight);
      g.strokeStyle = "#ef7b5f"; g.lineWidth = 2; g.strokeRect(c.x - 2, c.y - 2, c.w + 4, c.h + 4);
    }
    g.restore();
    return r;
  }
  layout(W, H) {
    const left = 450, right = 24, top = 24, bottom = 24;
    const aw = Math.max(200, W - left - right), ah = H - top - bottom;
    const aspect = (GRID.cols * GRID.cellW) / (GRID.rows * GRID.cellH);
    let w = aw, h = w / aspect; if (h > ah) { h = ah; w = h * aspect; }
    return { x: left + (aw - w) / 2, y: top + (ah - h) / 2, w, h };
  }
  cellRect(r, i) {
    const gap = 2, cw = r.w / GRID.cols, ch = r.h / GRID.rows;
    return { x: r.x + (i % GRID.cols) * cw + gap / 2, y: r.y + Math.floor(i / GRID.cols) * ch + gap / 2, w: cw - gap, h: ch - gap };
  }

  panel(now) {
    const t = this.totals();
    this.samples.push({ t: now, steps: t.steps });
    while (this.samples.length > 2 && now - this.samples[0].t > 2000) this.samples.shift();
    const a = this.samples[0], b = this.samples[this.samples.length - 1];
    const sps = b.t > a.t ? ((b.steps - a.steps) * 1000) / (b.t - a.t) : 0;
    $("#g-sps").textContent = human(sps); $("#g-steps").textContent = human(t.steps);
    $("#g-eps").textContent = fmt(t.episodes); $("#g-ach").textContent = t.episodes ? (t.achSum / t.episodes).toFixed(2) : "–";
    const S = this.S;
    {
      const { g, w, h } = fitCanvas($("#g-hist"));
      g.clearRect(0, 0, w, h);
      // live: current achievements across all worlds; finished episodes as outline
      const live = new Array(33).fill(0); this.current.forEach((c) => live[c]++);
      const mx = Math.max(1, ...live);
      const fin = Math.max(1, ...t.hist);
      g.font = "10px ui-monospace, Menlo, monospace"; g.fillStyle = "#8b8b94";
      g.fillText("achievements so far, per world (bars) · finished episodes (line)", 0, 10);
      const bw = w / 33;
      live.forEach((v, i) => { g.fillStyle = "#6fd39b"; g.fillRect(i * bw + 1, h - 12 - ((h - 26) * v) / mx, bw - 2, ((h - 26) * v) / mx); });
      g.strokeStyle = "#f3c63c"; g.beginPath();
      t.hist.forEach((v, i) => { const x = i * bw + bw / 2, y = h - 12 - ((h - 26) * v) / fin; i ? g.lineTo(x, y) : g.moveTo(x, y); });
      g.stroke();
      g.fillStyle = "#8b8b94"; [0, 8, 16, 24, 32].forEach((k) => g.fillText(k, k * bw + 1, h - 1));
    }
    {
      const { g, w, h } = fitCanvas($("#g-achbars"));
      g.clearRect(0, 0, w, h);
      g.font = "10px ui-monospace, Menlo, monospace"; g.fillStyle = "#8b8b94";
      g.fillText("share of finished episodes earning each achievement", 0, 10);
      const bw = w / 32;
      for (let i = 0; i < 32; i++) {
        const f = t.episodes ? t.achHits[i] / t.episodes : 0, bh = (h - 34) * f;
        g.fillStyle = f > 0.5 ? "#f3c63c" : f > 0 ? "#b58a2a" : "#2a2a32";
        g.fillRect(i * bw + 2, h - 18 - bh, bw - 4, Math.max(1, bh));
        icon(g, S.achIcons[i], i * bw + (bw - 14) / 2, h - 15, 14, f > 0 ? 1 : 0.35);
      }
    }
  }
}

export function drawTraining(S) {
  const run = S.run, curve = run.curve;
  $("#train-src").textContent = `${run.architecture} · ${fmt(run.parameters)} params · γ ${run.config.gamma} · ${run.config.envs} envs`;
  {
    const { g, w, h } = fitCanvas($("#train-curve"));
    g.clearRect(0, 0, w, h);
    const xs = curve.map((r) => r.steps), ys = curve.map((r) => r.mean_achievements);
    const maxX = xs[xs.length - 1], X = (s) => 40 + (s / maxX) * (w - 50), Y = (v) => h - 22 - (v / 32) * (h - 36);
    g.strokeStyle = "rgba(255,255,255,.07)"; g.fillStyle = "#8b8b94"; g.font = "10px ui-monospace, Menlo, monospace";
    for (const v of [0, 8, 16, 24, 32]) { g.beginPath(); g.moveTo(40, Y(v)); g.lineTo(w - 10, Y(v)); g.stroke(); g.fillText(v, 14, Y(v) + 3); }
    for (const s of [0, 0.5e9, 1e9, 1.5e9, 2e9]) g.fillText(s ? `${s / 1e9}B` : "0", X(s) - 6, h - 6);
    // scripted ceiling
    g.setLineDash([4, 4]); g.strokeStyle = "#6fd39b"; g.beginPath(); g.moveTo(40, Y(31.97)); g.lineTo(w - 10, Y(31.97)); g.stroke(); g.setLineDash([]);
    g.fillStyle = "#6fd39b"; g.fillText("scripted player 31.97", w - 150, Y(31.97) - 5);
    g.strokeStyle = "#ef7b5f"; g.lineWidth = 2; g.beginPath();
    xs.forEach((x, i) => (i ? g.lineTo(X(x), Y(ys[i])) : g.moveTo(X(x), Y(ys[i])))); g.stroke();
    for (const ck of run.checkpoints) {
      const v = ck.mean_achievements;
      if (v == null) continue;
      g.fillStyle = ck.steps === S.policy.steps ? "#ffd84a" : "#ef7b5f";
      g.beginPath(); g.arc(X(ck.steps), Y(v), ck.steps === S.policy.steps ? 5 : 3, 0, 7); g.fill();
    }
    g.fillStyle = "#e9e6e1"; g.fillText("validation achievements (mean of 128 held-out worlds)", 44, 12);
  }
  {
    const { g, w, h } = fitCanvas($("#train-ach"));
    g.clearRect(0, 0, w, h);
    const names = S.core.achNames, rowH = (h - 14) / 16, colW = w / 2;
    g.font = "10px ui-monospace, Menlo, monospace";
    g.fillStyle = "#8b8b94"; g.fillText("share of validation episodes earning each achievement, over training", 0, 10);
    names.forEach((n, i) => {
      const cx = Math.floor(i / 16) * colW, cy = 14 + (i % 16) * rowH;
      icon(g, S.achIcons[i], cx, cy + 1, rowH - 2);
      g.fillStyle = "#c9c6c1"; g.fillText(n.slice(0, 22), cx + rowH + 2, cy + rowH * 0.7);
      const sx = cx + 150, sw = colW - 160;
      curve.forEach((r, k) => {
        const f = (r.hits[n] ?? 0) / 128;
        g.fillStyle = f === 0 ? "#1f1f25" : `rgba(243,198,60,${0.15 + 0.85 * f})`;
        g.fillRect(sx + (k * sw) / curve.length, cy + 2, sw / curve.length - 1, rowH - 4);
      });
    });
  }
  const last = curve[curve.length - 1];
  $("#train-stats").replaceChildren(
    ...[["2.1B", "env steps"], [fmt(run.config.sps), "steps / s"], [(last.elapsed / 3600).toFixed(1) + " h", "wall clock"], [last.mean_achievements.toFixed(2), "final / 32"]]
      .map(([b, s]) => el("div", {}, el("b", {}, b), el("span", {}, s))));
}
