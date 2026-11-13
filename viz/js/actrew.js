// Zooms: the action distribution (83 actions, masked) and the reward/return.
import { $, el, htmlH3, fitCanvas, icon, clamp, fmt, lineChart } from "./ui.js";
import { drawPlayerIcon } from "./terraria.js";

const GROUPS = [
  { name: "move", from: 0, to: 4, c: "#e9e6e1" }, { name: "mine ×20", from: 4, to: 24, c: "#ffd84a" },
  { name: "place ×20", from: 24, to: 44, c: "#6aa8ff" }, { name: "next", from: 44, to: 45, c: "#c39bff" },
  { name: "craft ×19", from: 45, to: 64, c: "#6fd39b" }, { name: "use", from: 64, to: 73, c: "#ef7b5f" },
  { name: "select ×10", from: 73, to: 83, c: "#c39bff" },
];

export class ActZoom {
  constructor(S, lab) {
    this.S = S; this.lab = lab;
    const root = $("#zoom-act");
    this.bars = el("canvas", { style: { width: "100%", height: "300px" } });
    this.reach = el("canvas", { style: { width: "300px", height: "340px" } });
    this.info = el("div", { class: "legend", style: { flex: 1 } });
    root.append(htmlH3("c-act", "ACTION a<sub>t</sub> ~ π(·|o<sub>t</sub>) · 83 discrete actions"), this.bars,
      el("div", { class: "row" }, el("div", {}, el("div", { class: "cap" }, "spatial head: P(mine) ▲ / P(place) ▼ per reach cell"), this.reach), this.info));
  }

  draw() {
    const S = this.S, lab = this.lab, tr = lab.tr, core = S.core2, K = core.L, mask = lab.maskArr, a = lab.action;
    if (!tr) return;
    { // 83 bars
      const { g, w, h } = fitCanvas(this.bars);
      g.clearRect(0, 0, w, h);
      const n = K.ACT_COUNT, bw = (w - 10) / n, base = h - 60, top = 30;
      for (const gr of GROUPS) {
        g.fillStyle = "rgba(255,255,255,.03)"; g.fillRect(5 + gr.from * bw, top - 22, (gr.to - gr.from) * bw - 2, base - top + 22);
        g.fillStyle = gr.c; g.font = "10px ui-monospace, Menlo, monospace";
        if ((gr.to - gr.from) * bw > 44) g.fillText(gr.name, 7 + gr.from * bw, top - 10);
      }
      for (let i = 0; i < n; i++) {
        const x = 5 + i * bw, p = tr.probs[i], gr = GROUPS.find((q) => i >= q.from && i < q.to);
        if (!mask[i]) { // hatched: illegal
          g.strokeStyle = "rgba(255,255,255,.08)"; g.beginPath();
          for (let y = top; y < base; y += 6) { g.moveTo(x, y + 4); g.lineTo(x + bw - 1, y); }
          g.stroke();
        } else {
          const bh = Math.sqrt(p) * (base - top);
          g.fillStyle = gr.c; g.globalAlpha = i === a ? 1 : 0.75; g.fillRect(x + 0.5, base - bh, bw - 1.5, Math.max(1, bh)); g.globalAlpha = 1;
        }
        // icons
        let img = null;
        if (i >= K.RECIPE_FIRST && i < K.RECIPE_FIRST + K.RECIPE_COUNT) img = S.items[core.recipes[i - K.RECIPE_FIRST].out];
        else if (i >= K.SELECT_FIRST) img = S.items[core.placeables[i - K.SELECT_FIRST]];
        if (img) icon(g, img, x + (bw - Math.min(14, bw)) / 2, base + 4, Math.min(14, bw), mask[i] ? 1 : 0.3);
        if (i === a) {
          g.strokeStyle = "#fff"; g.lineWidth = 2; g.beginPath(); g.arc(x + bw / 2, base + 30, 6, 0, 7); g.stroke();
          g.fillStyle = "#fff"; g.textAlign = i > n / 2 ? "right" : "left";
          g.fillText(`sampled: ${core.actionNames[i]}  (p = ${(p * 100).toFixed(1)}%)`, x + bw / 2 + (i > n / 2 ? -12 : 12), base + 34); g.textAlign = "left";
        }
      }
      g.fillStyle = "#8b8b94"; g.fillText("bar height ∝ √π(a|s) · hatched = masked (illegal right now)", 5, h - 4);
    }
    { // reach grid around the body: dx -1..2, dy -3..1
      const { g, w, h } = fitCanvas(this.reach), cs = Math.min(w / 4, (h - 10) / 5);
      g.clearRect(0, 0, w, h);
      const o = lab.obs, cx = K.VIEW_W >> 1, cy = K.VIEW_H >> 1;
      for (let dy = -3; dy <= 1; dy++) for (let dx = -1; dx <= 2; dx++) {
        const x = (dx + 1) * cs, y = (dy + 3) * cs, k = (cy + dy) * K.VIEW_W + cx + dx, t = o.tile[k];
        if (t && t < K.TILE_COUNT) g.drawImage(S.art.tileIcon(t), x, y, cs, cs);
        else { g.fillStyle = t ? "#050507" : "#1c2a44"; g.fillRect(x, y, cs, cs); }
      }
      drawPlayerIcon(g, S.art, cs, cs, cs, 0.85);
      core.reach.forEach((r, i) => {
        const x = (r.dx + 1) * cs, y = (r.dy + 3) * cs;
        const pm = tr.probs[K.MINE_FIRST + i], pp = tr.probs[K.PLACE_FIRST + i];
        const mm = mask[K.MINE_FIRST + i], mp = mask[K.PLACE_FIRST + i];
        g.fillStyle = mm ? `rgba(255,216,74,${0.15 + 0.85 * Math.sqrt(pm)})` : "rgba(0,0,0,.45)";
        g.beginPath(); g.moveTo(x, y); g.lineTo(x + cs, y); g.lineTo(x, y + cs); g.fill();
        g.fillStyle = mp ? `rgba(106,168,255,${0.15 + 0.85 * Math.sqrt(pp)})` : "rgba(0,0,0,.45)";
        g.beginPath(); g.moveTo(x + cs, y); g.lineTo(x + cs, y + cs); g.lineTo(x, y + cs); g.fill();
        g.strokeStyle = "rgba(255,255,255,.12)"; g.strokeRect(x, y, cs, cs);
        if (a === K.MINE_FIRST + i || a === K.PLACE_FIRST + i) { g.strokeStyle = "#fff"; g.lineWidth = 3; g.strokeRect(x + 1.5, y + 1.5, cs - 3, cs - 3); g.lineWidth = 1; }
      });
    }
    const legal = mask.reduce((s, v) => s + v, 0);
    const top = [...tr.probs.keys()].sort((x, y) => tr.probs[y] - tr.probs[x]).slice(0, 5);
    this.info.innerHTML =
      `<p><b>${legal}</b> of 83 actions are legal at this step; the other ${83 - legal} get logit −∞ and probability exactly 0.</p>` +
      `<p>entropy H(π) = <b>${tr.entropy.toFixed(2)}</b> nats (uniform over the legal set would be ${Math.log(legal).toFixed(2)})</p>` +
      `<p>sampled <b class="c-act">${core.actionNames[a]}</b> with log π(a|s) = <b>${tr.logp.toFixed(2)}</b></p>` +
      `<p class="muted">top 5: ${top.map((i) => `${core.actionNames[i]} ${(tr.probs[i] * 100).toFixed(0)}%`).join(" · ")}</p>` +
      `<p class="muted">Each reach cell is scored by one shared 2-layer head from [global features h₂ | its 3×3 neighbourhood | its offset], so "mine the ore to my right" and "mine the ore below me" share what they learn.</p>`;
  }
}

export class RewZoom {
  constructor(S, lab) {
    this.S = S; this.lab = lab; this.gamma = 0.999;
    const root = $("#zoom-rew");
    this.timeline = el("canvas", { style: { width: "100%", height: "150px" } });
    this.value = el("canvas", { style: { width: "100%", height: "200px" } });
    this.disc = el("canvas", { style: { width: "360px", height: "170px" } });
    this.info = el("div", { class: "legend", style: { flex: 1 } });
    const pick = el("div", { class: "ckpt-pick" }, ...[0.9, 0.99, 0.999, 1].map((gm) => el("button", { class: gm === 0.999 ? "on" : "", onclick: (e) => { this.gamma = gm; [...pick.children].forEach((b) => b.classList.toggle("on", b === e.target)); } }, `γ = ${gm}`)));
    root.append(htmlH3("c-rew", "REWARD r<sub>t+1</sub> · +1 per new achievement, −1 for dying"), this.timeline, this.value,
      el("div", { class: "row" }, el("div", {}, el("div", { class: "cap", style: { textTransform: "none" } }, "how much a reward k steps ahead is worth today: γ^k"), pick, this.disc), this.info));
  }

  draw() {
    const S = this.S, lab = this.lab, R = lab.replay, k = lab.k, core = S.core2, n = 3000;
    const X = (t, w) => 40 + (t / n) * (w - 50);
    { // reward timeline with achievement icons
      const { g, w, h } = fitCanvas(this.timeline);
      g.clearRect(0, 0, w, h);
      g.strokeStyle = "rgba(255,255,255,.1)"; g.beginPath(); g.moveTo(40, h - 30); g.lineTo(w - 10, h - 30); g.stroke();
      let ret = 0; g.strokeStyle = "#f3c63c"; g.beginPath();
      let prev = 0;
      for (let t = 0; t < R.length; t++) {
        ret += R.rewards[t]; const y = h - 30 - (ret / 32) * (h - 50);
        t ? g.lineTo(X(t, w), y) : g.moveTo(X(t, w), y);
        const got = R.ach[t] & ~prev; prev = R.ach[t];
        if (got) for (let b = 0; b < 32; b++) if ((got >>> b) & 1) icon(g, S.achIcons[b], X(t, w) - 7, h - 48 - ((b % 3) * 12), 14, t <= k ? 1 : 0.3);
        if (R.rewards[t] < 0) { g.fillStyle = "#ff6060"; g.fillRect(X(t, w) - 1, h - 30, 3, 10); }
      }
      g.stroke();
      g.fillStyle = "#8b8b94"; g.font = "10px ui-monospace, Menlo, monospace";
      g.fillText("return so far (sum of rewards) · icons = the step each achievement paid +1", 40, 10);
      g.fillStyle = "#fff"; g.fillRect(X(k, w), 14, 1.5, h - 40);
      [0, 1000, 2000, 3000].forEach((t) => g.fillText(t, X(t, w) - 8, h - 2));
    }
    const G = R.returns(this.gamma);
    { // V(s) vs realised discounted return
      const { g, w, h } = fitCanvas(this.value);
      g.clearRect(0, 0, w, h);
      const mx = Math.max(4, ...R.values, ...G) * 1.05, Y = (v) => h - 20 - (v / mx) * (h - 34);
      g.strokeStyle = "rgba(255,255,255,.07)"; g.fillStyle = "#8b8b94"; g.font = "10px ui-monospace, Menlo, monospace";
      for (let v = 0; v <= mx; v += Math.ceil(mx / 4)) { g.beginPath(); g.moveTo(40, Y(v)); g.lineTo(w - 10, Y(v)); g.stroke(); g.fillText(v, 18, Y(v) + 3); }
      const line = (arr, c) => { g.strokeStyle = c; g.lineWidth = 1.5; g.beginPath(); for (let t = 0; t < R.length; t++) t ? g.lineTo(X(t, w), Y(arr[t])) : g.moveTo(X(t, w), Y(arr[t])); g.stroke(); };
      line(G, "rgba(255,255,255,.85)"); line(R.values, "#ef7b5f");
      g.fillStyle = "#fff"; g.fillRect(X(k, w), 14, 1.5, h - 34);
      g.fillStyle = "#ef7b5f"; g.fillText("V(sₜ): critic's prediction", 44, 12);
      g.fillStyle = "#fff"; g.fillText(`Gₜ = Σ γᵏ rₜ₊ₖ₊₁ (γ = ${this.gamma}): what actually followed`, 230, 12);
      if (!R.done) { g.fillStyle = "#8b8b94"; g.fillText(`recording episode… ${R.length} / 3000`, w - 190, h - 4); }
    }
    { // discount weights
      const { g, w, h } = fitCanvas(this.disc);
      g.clearRect(0, 0, w, h);
      const N = 3000, Y = (v) => h - 20 - v * (h - 44);
      g.strokeStyle = "#f3c63c"; g.lineWidth = 2; g.beginPath();
      for (let i = 0; i <= N; i += 10) { const x = 30 + (i / N) * (w - 40); i ? g.lineTo(x, Y(Math.pow(this.gamma, i))) : g.moveTo(x, Y(1)); }
      g.stroke();
      g.fillStyle = "#8b8b94"; g.font = "10px ui-monospace, Menlo, monospace";
      g.fillText("1", 14, Y(1) + 3); g.fillText("0", 14, Y(0) + 3);
      [0, 1000, 2000, 3000].forEach((t) => g.fillText(t, 30 + (t / N) * (w - 40) - 8, h - 4));
      const half = this.gamma < 1 ? Math.log(0.5) / Math.log(this.gamma) : Infinity;
      g.fillStyle = "#e9e6e1"; g.fillText(this.gamma < 1 ? `half-life ≈ ${fmt(half)} steps · horizon 1/(1−γ) = ${fmt(1 / (1 - this.gamma))}` : "γ = 1: no discount, every future reward counts fully", 30, 12);
    }
    const A = R.advantages(0.999, 0.99);
    const r = k < R.length ? R.rewards[k] : 0, v = k < R.length ? R.values[k] : 0;
    this.info.innerHTML =
      `<p>step <b>${k}</b>: reward <b class="c-rew">${r > 0 ? "+" : ""}${r}</b>, return so far <b>${R.view.epReturn.toFixed(0)}</b></p>` +
      `<p>critic V(sₜ) = <b class="c-act">${v.toFixed(2)}</b> vs realised Gₜ = <b>${(G[k] ?? 0).toFixed(2)}</b></p>` +
      `<p>advantage Âₜ (GAE, γ .999, λ .99) = <b style="color:${(A[k] ?? 0) >= 0 ? "#6fd39b" : "#6aa8ff"}">${(A[k] ?? 0).toFixed(3)}</b>: ${(A[k] ?? 0) >= 0 ? "things went better than the critic expected, so PPO makes the action more likely" : "worse than expected, so PPO makes the action less likely"}.</p>` +
      `<p class="muted">Training also added recipe-progress shaping (potential-based, coefficient 3) on top of these rewards. What is shown and scored here is the environment's own reward.</p>`;
  }
}
