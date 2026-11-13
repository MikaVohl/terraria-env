// Zoom: inside the policy network. Real activations (forward) and the real
// gradient of log π(aₜ|oₜ) (backward) from viz/wasm/policy.c, plus PPO's
// clipped objective.
import { $, el, fitCanvas, clamp, diverge, icon, fmt } from "./ui.js";
import { drawPlayerIcon } from "./terraria.js";

/* Offsets of each tensor in the exported blob (same order as policy.c). */
export function weightViews(F, H = 128, C = 32, cells = 99, s0 = 92, R = 20, other = 43) {
  let p = 0; const take = (n) => { const v = F.subarray(p, p + n); p += n; return v; };
  const W = {};
  W.W0 = take(C * 29); W.b0 = take(C); W.W1 = take(C * C); W.b1 = take(C);
  W.Wg0 = take(H * (cells * C + s0)); W.bg0 = take(H); W.Wg1 = take(H * H); W.bg1 = take(H);
  W.Wc = take(64 * 9 * C); W.bc = take(64); W.Wa = take(other * H); W.ba = take(other);
  W.Wt0 = take(64 * (H + 66)); W.bt0 = take(64); W.Wt1 = take(128); W.bt1 = take(2); W.Wv = take(H); W.bv = take(1);
  return W;
}

export class NetZoom {
  constructor(S, lab) {
    this.S = S; this.lab = lab;
    const root = $("#zoom-net");
    this.canvas = el("canvas", { style: { width: "100%", flex: "1 1 auto", minHeight: 0 } });
    this.ppo = el("canvas", { style: { width: "420px", height: "200px" } });
    this.ppoInfo = el("div", { class: "legend", style: { flex: 1 } });
    this.ppoRow = el("div", { class: "row sub" }, this.ppo, this.ppoInfo);
    root.append(el("h3", { class: "c-agent" }, "AGENT · \"targets\" actor-critic, 472,718 parameters"), this.canvas, this.ppoRow);
    this.cacheK = -1;
  }

  edges() { // strongest contributions |w_ij · a_j| between layers, for this step
    const lab = this.lab, tr = lab.tr, W = this.S.W2, H = 128, gin = tr.gin, n = gin.length;
    const top = (count, rows, cols, w, a, d) => {
      const out = [];
      for (let i = 0; i < rows; i++) for (let j = 0; j < cols; j++) {
        const c = w[i * cols + j] * a[j];
        out.push([Math.abs(c), i, j, c, w[i * cols + j] * d[i] * a[j]]);
      }
      return out.sort((x, y) => y[0] - x[0]).slice(0, count);
    };
    // backward deltas at the pre-activations
    const d2 = tr.g.map((g, i) => tr.dG[i] * (1 - g * g)), d1 = tr.g1.map((g, i) => tr.dG1[i] * (1 - g * g));
    this.e12 = top(260, H, H, W.Wg1, tr.g1, d2);
    // input->h1 is 3260x128: prefilter by activation magnitude
    const idx = [...gin.keys()].filter((j) => Math.abs(gin[j]) > 0.05);
    const sub = idx.map((j) => gin[j]);
    const out = [];
    for (let i = 0; i < H; i++) for (let q = 0; q < idx.length; q++) {
      const j = idx[q], c = W.Wg0[i * n + j] * sub[q], m = Math.abs(c);
      if (m > 0.08) out.push([m, i, j, c, W.Wg0[i * n + j] * d1[i] * sub[q]]);
    }
    out.sort((x, y) => y[0] - x[0]);
    // keep both sources visible: strongest from cell codes and from the status vector
    const cellsN = gin.length - 92;
    this.e01 = [...out.filter((e) => e[2] < cellsN).slice(0, 200), ...out.filter((e) => e[2] >= cellsN).slice(0, 90)];
  }

  draw(phase) { // phase: 0..1 forward, 1..2 backward, 2..3 PPO
    const S = this.S, lab = this.lab, tr = lab.tr, core = S.core2, K = core.L;
    if (!tr) return;
    if (this.cacheK !== lab.k) { this.edges(); this.cacheK = lab.k; }
    this.ppoRow.classList.toggle("on", phase >= 2);
    this.canvas.style.maxHeight = phase >= 2 ? "calc(100% - 250px)" : "";
    const fwd = clamp(phase), bwd = clamp(phase - 1);
    const { g, w, h } = fitCanvas(this.canvas);
    g.clearRect(0, 0, w, h);
    const VW = K.VIEW_W, VH = K.VIEW_H, H = 128, top = 40, bottom = h - 24, span = bottom - top, mid = top + span / 2;
    // 7 stages left to right; vis(i) fades stage i in during the forward sweep, back(i) during backward
    const vis = (i) => clamp(fwd * 7 - i), back = (i) => clamp(bwd * 7 - (6 - i));
    // input and cell codes share the first column (stacked), so the grids can be large
    const cs = Math.max(7, Math.min(22, (w - 560) / VW, (span - 90) / (2 * VH)));
    const X = [8, 8]; X[2] = X[0] + VW * cs + 44; X[3] = X[2] + 64 + 70; X[4] = X[3] + 90;
    X[5] = X[4] + 70; X[6] = X[5] + 140;
    const ow = Math.max(40, w - X[6] - 8);
    g.font = "10px ui-monospace, Menlo, monospace";
    const label = (i, t, sub, x = X[i]) => { g.globalAlpha = Math.max(0.3, vis(i)); g.fillStyle = "#e9e6e1"; g.fillText(t, x, 12); g.fillStyle = "#8b8b94"; g.fillText(sub, x, 25); g.globalAlpha = 1; };
    label(0, "input oₜ", "11×9 cells"); label(2, "concat", "3,168 + 92 status");
    label(3, "h₁ tanh", "128"); label(4, "h₂ tanh", "128"); label(5, "3 heads", "actor·scorer·critic"); label(6, "π(a|s)", "83 actions");
    const o = lab.obs, gy0 = top + 6, gy1 = gy0 + VH * cs + 54;
    const sal = tr.saliency, smx = Math.max(...sal) || 1;
    // 0: input window (tile art, darkness as the agent sees it)
    for (let k = 0; k < 99; k++) {
      const x = X[0] + (k % VW) * cs, y = gy0 + Math.floor(k / VW) * cs, t = o.tile[k];
      g.globalAlpha = Math.max(0.35, vis(0));
      if (t && t < K.TILE_COUNT) g.drawImage(S.art.tileIcon(t), x, y, cs, cs); else { g.fillStyle = t ? "#050507" : "#1c2a44"; g.fillRect(x, y, cs, cs); }
      g.globalAlpha = 1;
      if (back(0) > 0) { g.fillStyle = `rgba(239,123,95,${0.9 * back(0) * Math.sqrt(sal[k] / smx)})`; g.fillRect(x, y, cs, cs); }
    }
    drawPlayerIcon(g, S.art, X[0] + (VW >> 1) * cs, gy0 + ((VH >> 1) - 2) * cs, cs, 0.85 * Math.max(0.35, vis(0)));
    g.fillStyle = back(0) > 0.3 ? "#ef7b5f" : "#8b8b94";
    g.fillText(back(0) > 0.3 ? "‖∂ log π(aₜ) / ∂ cell‖: what mattered" : "+ status vector (92)", X[0], gy0 + VH * cs + 16);
    // 1: per-cell codes, 32 values as 4x8 micro-pixels
    let cmax = 1e-6; for (const v of tr.cells) cmax = Math.max(cmax, v);
    let dmax = 1e-9; for (const v of tr.dCells) dmax = Math.max(dmax, Math.abs(v));
    for (let k = 0; k < 99; k++) {
      const x = X[1] + (k % VW) * cs, y = gy1 + Math.floor(k / VW) * cs;
      for (let c = 0; c < 32; c++) {
        const v = tr.cells[k * 32 + c], d = tr.dCells[k * 32 + c];
        g.fillStyle = back(1) > 0 ? diverge(d / dmax, back(1)) : `rgba(195,155,255,${Math.sqrt(v / cmax) * vis(1)})`;
        g.fillRect(x + (c % 4) * ((cs - 1) / 4), y + Math.floor(c / 4) * ((cs - 1) / 8), (cs - 1) / 4, (cs - 1) / 8);
      }
    }
    g.globalAlpha = Math.max(0.3, vis(1)); g.fillStyle = "#e9e6e1"; g.fillText("↓ cell MLP, shared by all 99 cells: 29 → 32 → 32", X[1], gy1 - 8); g.globalAlpha = 1;
    if (vis(2) > 0) { // codes and status flow into the concat column
      g.strokeStyle = `rgba(195,155,255,${0.3 * vis(2)})`; g.setLineDash([3, 3]);
      g.beginPath(); g.moveTo(X[1] + VW * cs + 4, gy1 + (VH * cs) / 2); g.lineTo(X[2] - 4, top + span * 0.36); g.stroke(); g.setLineDash([]);
    }
    // 2: concat column: one row per cell (32 values), then the status block
    const cellsN = 99 * 32, rowH = (span * 0.72) / 99, sy0 = top + 6, sh = span * 0.22, sTop = sy0 + 99 * rowH + 10;
    const ginPos = (j) => (j < cellsN ? [X[2] + (j % 32) * 2, sy0 + Math.floor(j / 32) * rowH + rowH / 2]
      : [X[2] + ((j - cellsN) % 4) * 16, sTop + Math.floor((j - cellsN) / 4) * (sh / 23) + sh / 46]);
    for (let j = 0; j < tr.gin.length; j++) {
      const v = tr.gin[j], [x, y] = ginPos(j), statusPart = j >= cellsN;
      const bv = back(2) > 0 ? (statusPart ? tr.dStatus[j - cellsN] : tr.dCells[j]) : 0;
      if (back(2) > 0) g.fillStyle = diverge(statusPart ? Math.tanh(bv * 3) : bv / dmax, back(2));
      else g.fillStyle = statusPart ? `rgba(106,168,255,${(0.08 + 0.92 * clamp(Math.abs(v))) * Math.max(0.2, vis(2))})` : `rgba(195,155,255,${Math.sqrt(v / cmax) * Math.max(0.15, vis(2))})`;
      if (statusPart) g.fillRect(x, y - sh / 46 + 0.5, 15, sh / 23 - 1); else g.fillRect(x, y - rowH / 2, 2, Math.max(1, rowH - 0.3));
    }
    g.fillStyle = "#8b8b94"; g.fillText("status", X[2], sTop - 3);
    // 3,4: hidden units, two columns of 64
    const unit = (i, layer) => [X[layer] + 10 + (i % 2) * 14, top + 8 + Math.floor(i / 2) * ((span - 16) / 64)];
    const ea = (f) => 0.55 * f;
    if (vis(3) > 0 || back(3) > 0) for (const [, i, j, c, dg] of this.e01) {
      const [x0, y0] = ginPos(j), [x1, y1] = unit(i, 3);
      g.strokeStyle = back(3) > 0 ? diverge(Math.tanh(dg * 50), ea(back(3))) : diverge(Math.tanh(c * 3), ea(vis(3)));
      g.beginPath(); g.moveTo(x0 + (j < cellsN ? 2 : 15), y0); g.lineTo(x1, y1); g.stroke();
    }
    if (vis(4) > 0 || back(4) > 0) for (const [, i, j, c, dg] of this.e12) {
      const [x0, y0] = unit(j, 3), [x1, y1] = unit(i, 4);
      g.strokeStyle = back(4) > 0 ? diverge(Math.tanh(dg * 10), ea(back(4))) : diverge(Math.tanh(c * 3), ea(vis(4)));
      g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
    }
    const dot = (x, y, v, d, li) => {
      g.fillStyle = back(li) > 0 ? diverge(Math.tanh(d * 5)) : diverge(v, Math.max(0.12, vis(li)));
      g.beginPath(); g.arc(x, y, 4, 0, 7); g.fill();
    };
    for (let i = 0; i < H; i++) { const [x, y] = unit(i, 3); dot(x, y, tr.g1[i], tr.dG1[i], 3); }
    for (let i = 0; i < H; i++) { const [x, y] = unit(i, 4); dot(x, y, tr.g[i], tr.dG[i], 4); }
    // 5: heads
    const hx = X[5], va = Math.max(0.15, vis(5));
    const fan = (y1) => { if (vis(5) <= 0) return; g.strokeStyle = `rgba(195,155,255,${0.25 * vis(5)})`; g.beginPath(); g.moveTo(X[4] + 28, mid); g.lineTo(hx - 4, y1); g.stroke(); };
    const aH = span * 0.42;
    fan(top + aH / 2);
    for (let i = 0; i < 43; i++) {
      const y = top + i * (aH / 43), a = i < 4 ? i : i + 40;
      g.fillStyle = back(5) > 0 ? diverge(Math.tanh(tr.dLogits[a] * 3), back(5)) : diverge(Math.tanh(tr.other[i] / 4), va);
      g.fillRect(hx, y, 12, Math.max(2, aH / 43 - 1.5));
    }
    g.fillStyle = "#8b8b94"; g.fillText("actor", hx + 16, top + 10); g.fillText("43 logits", hx + 16, top + 22);
    const rs = 16, ry = top + aH + 26;
    fan(ry + 2.5 * rs);
    drawPlayerIcon(g, S.art, hx + rs, ry + rs, rs, va);
    core.reach.forEach((r, i) => {
      const x = hx + (r.dx + 1) * rs, y = ry + (r.dy + 3) * rs;
      const pm = tr.probs[K.MINE_FIRST + i], pp = tr.probs[K.PLACE_FIRST + i];
      const dm = tr.dLogits[K.MINE_FIRST + i], dp = tr.dLogits[K.PLACE_FIRST + i];
      g.fillStyle = back(5) > 0 ? diverge(Math.tanh((dm + dp) * 3), back(5)) : `rgba(255,216,74,${(0.12 + 0.88 * Math.sqrt(Math.max(pm, pp))) * va})`;
      g.fillRect(x + 1, y + 1, rs - 2, rs - 2);
    });
    g.fillStyle = "#8b8b94"; g.fillText("target scorer", hx + 4 * rs + 6, ry + 10); g.fillText("20 cells × 2", hx + 4 * rs + 6, ry + 22);
    g.fillText("+ 3×3 context", hx + 4 * rs + 6, ry + 34);
    const vy = ry + 5 * rs + 30;
    fan(vy);
    g.globalAlpha = va; g.fillStyle = "#c39bff"; g.font = "12px ui-monospace, Menlo, monospace";
    g.fillText(`critic V(s) = ${tr.value.toFixed(2)}`, hx, vy + 4); g.globalAlpha = 1; g.font = "10px ui-monospace, Menlo, monospace";
    // 6: output distribution
    const ph = span / 83;
    for (let a = 0; a < 83; a++) {
      const y = top + a * ph, p = tr.probs[a], bk = back(6) > 0;
      g.fillStyle = bk ? diverge(tr.dLogits[a], back(6)) : a === lab.action ? "#ef7b5f" : lab.maskArr[a] ? "#5a5a68" : "#26262d";
      g.globalAlpha = bk ? 1 : Math.max(0.15, vis(6));
      g.fillRect(X[6], y, Math.max(1, ow * (bk ? Math.abs(tr.dLogits[a]) : Math.sqrt(p))), Math.max(1, ph - 1));
      g.globalAlpha = 1;
    }
    if (vis(6) > 0.5) { const y = top + lab.action * ph; g.fillStyle = "#ef7b5f"; g.fillText(`← aₜ: ${core.actionNames[lab.action]}`, X[6] + 4, Math.max(top + 10, y - 3)); }
    if (back(6) > 0) { g.fillStyle = "#e9e6e1"; g.fillText("∂ log π(aₜ)/∂ logitₐ = 1[a = aₜ] − π(a)", Math.max(X[6], w - 250), top - 4); }
    // sweep
    const sweep = bwd > 0 ? X[0] + (1 - bwd) * (w - X[0]) : X[0] + fwd * (w - X[0]);
    if ((fwd > 0 && fwd < 1) || (bwd > 0 && bwd < 1)) {
      const gr = g.createLinearGradient(sweep - 50, 0, sweep + 50, 0), c = bwd > 0 ? "106,168,255" : "195,155,255";
      gr.addColorStop(0, `rgba(${c},0)`); gr.addColorStop(0.5, `rgba(${c},.16)`); gr.addColorStop(1, `rgba(${c},0)`);
      g.fillStyle = gr; g.fillRect(sweep - 50, top - 8, 100, span + 16);
    }
    g.fillStyle = "#8b8b94"; g.textAlign = "right";
    g.fillText(bwd > 0 ? "backward: ∇ log π(aₜ|oₜ) · coral = push up, blue = push down" : "forward: activations · violet = positive, blue = negative", w - 8, h - 4);
    g.textAlign = "left";
    if (phase >= 2) this.drawPPO();
  }

  drawPPO() {
    const R = this.lab.replay, k = this.lab.k, A = R.advantages(0.999, 0.99)[k] ?? 0;
    const { g, w, h } = fitCanvas(this.ppo);
    g.clearRect(0, 0, w, h);
    const X = (r) => 30 + (r / 2) * (w - 40), Y = (v) => h / 2 - v * (h / 2 - 20);
    g.fillStyle = "rgba(111,211,155,.08)"; g.fillRect(X(0.8), 10, X(1.2) - X(0.8), h - 30);
    g.strokeStyle = "rgba(255,255,255,.15)"; g.beginPath(); g.moveTo(30, Y(0)); g.lineTo(w - 10, Y(0)); g.moveTo(X(1), 10); g.lineTo(X(1), h - 20); g.stroke();
    const curve = (a, c) => {
      g.strokeStyle = c; g.lineWidth = 2; g.beginPath();
      for (let i = 0; i <= 200; i++) { const r = (i / 200) * 2, v = Math.min(r * a, clamp(r, 0.8, 1.2) * a); i ? g.lineTo(X(r), Y(v / 1.4)) : g.moveTo(X(r), Y(v / 1.4)); }
      g.stroke();
    };
    curve(1, "rgba(111,211,155,.9)"); curve(-1, "rgba(106,168,255,.9)");
    g.fillStyle = "#8b8b94"; g.font = "10px ui-monospace, Menlo, monospace";
    g.fillText("L_clip(r) = min(r·Â, clip(r, 0.8, 1.2)·Â)", 30, 12);
    g.fillText("r = π_new(a|s) / π_old(a|s)", w - 170, h - 4);
    g.fillStyle = "#6fd39b"; g.fillText("Â > 0", X(1.65), Y(1.2 / 1.4) - 4); g.fillStyle = "#6aa8ff"; g.fillText("Â < 0", X(1.65), Y(-1.2 / 1.4) + 12);
    ["0", "1", "2"].forEach((t, i) => { g.fillStyle = "#8b8b94"; g.fillText(t, X(i) - 3, h - 4); });
    const tr = this.lab.tr;
    this.ppoInfo.innerHTML =
      `<p>This step: π(aₜ|oₜ) = <b>${(Math.exp(tr.logp) * 100).toFixed(1)}%</b>, advantage Âₜ = <b style="color:${A >= 0 ? "#6fd39b" : "#6aa8ff"}">${A.toFixed(3)}</b>.</p>` +
      `<p>The update follows Âₜ · ∇ log π(aₜ|oₜ), the backward pass above scaled by the advantage, until the ratio r leaves [0.8, 1.2]. Past that point the clipped term is flat and stops pulling.</p>` +
      `<p class="muted">Per update: 1,024 envs × 128 steps = 131,072 samples → 16 minibatches × 4 epochs = 64 Adam steps (lr 3e-4, annealed), plus value loss (×0.5) and an entropy bonus (×0.03). Repeated 16,384 times.</p>`;
  }
}
